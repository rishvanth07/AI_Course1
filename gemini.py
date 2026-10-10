"""Gemini lesson plans for a new course."""

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from questions import available_languages, clean

ROOT = Path(__file__).resolve().parent
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "overview": {"type": "STRING"},
        "lessons": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "minutes": {"type": "INTEGER"},
                    "sections": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "label": {"type": "STRING"},
                                "text": {"type": "STRING"},
                            },
                            "required": ["label", "text"],
                        },
                    },
                    "quiz": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "prompt": {"type": "STRING"},
                                "choices": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "answer": {"type": "INTEGER"},
                            },
                            "required": ["prompt", "choices", "answer"],
                        },
                    },
                },
                "required": ["title", "minutes", "sections", "quiz"],
            },
        },
    },
    "required": ["overview", "lessons"],
}

def _items(properties: dict, required: list[str]) -> dict:
    return {"type": "ARRAY", "items": {"type": "OBJECT", "properties": properties, "required": required}}


_TEXT = {"type": "STRING"}
_TEXTS = {"type": "ARRAY", "items": {"type": "STRING"}}
_NUMBERS = {"type": "ARRAY", "items": {"type": "INTEGER"}}

ASSESSMENT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "single": _items({"prompt": _TEXT, "choices": _TEXTS, "answer": {"type": "INTEGER"}}, ["prompt", "choices", "answer"]),
        "truefalse": _items({"statement": _TEXT, "true": {"type": "BOOLEAN"}}, ["statement", "true"]),
        "multi": _items({"prompt": _TEXT, "choices": _TEXTS, "answers": _NUMBERS}, ["prompt", "choices", "answers"]),
        "fill": _items({"sentence": _TEXT, "answers": _TEXTS}, ["sentence", "answers"]),
        "match": _items(
            {
                "prompt": _TEXT,
                "pairs": _items({"term": _TEXT, "meaning": _TEXT}, ["term", "meaning"]),
            },
            ["prompt", "pairs"],
        ),
        "code": _items(
            {
                "prompt": _TEXT,
                "language": {"type": "STRING", "enum": ["python", "javascript", "sql"]},
                "setup": _TEXT,
                "starter": _TEXT,
                "solution": _TEXT,
                "tests": _TEXTS,
                "check": _TEXT,
            },
            ["prompt", "language", "starter", "solution"],
        ),
    },
    "required": ["single", "truefalse", "multi", "fill", "match", "code"],
}


FEEDBACK_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": _TEXT,
        "items": _items({"question": {"type": "INTEGER"}, "feedback": _TEXT}, ["question", "feedback"]),
    },
    "required": ["summary", "items"],
}


class GeminiError(Exception):
    pass


def load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str:
    load_env()
    return os.environ.get("GEMINI_API_KEY", "").strip()


def draft_lessons(title: str, goal: str) -> tuple[str, list[dict]]:
    key = api_key()
    if not key:
        raise GeminiError("Add GEMINI_API_KEY to a .env file in the project, then create the course again.")
    focus = goal.strip() or "the main idea"
    prompt = (
        "You are Lumina, a tutor. Draft a study plan for one course.\n"
        f"Course name: {title}\n"
        f"Focus: {focus}\n"
        "Write exactly four lessons, in the order a beginner should study them. "
        "Each lesson takes 15 to 25 minutes and has exactly three sections labeled "
        "Concept, Try, and Check. Each lesson has exactly three quiz questions. "
        "Each question has exactly three short choices, and answer is the index of the correct choice. "
        "The correct choice must follow from that lesson's study text. "
        "Do not put the correct choice first every time. "
        "Use plain sentences. The overview is one sentence about the plan."
    )
    payload = _generate(key, prompt, PLAN_SCHEMA)
    return _plan(payload, title, focus)


ASSESSMENT_BATCHES = [
    (
        {"single": 7, "truefalse": 3, "multi": 2, "fill": 3, "match": 1},
        "the core of the lesson: definitions, key facts, terminology, and how the parts relate",
    ),
    (
        {"single": 7, "truefalse": 3, "multi": 2, "fill": 2, "match": 1, "code": 1},
        "applying the lesson: short scenarios, worked examples, comparisons, and common beginner mistakes",
    ),
]


def draft_assessment(course: dict, lesson: dict, count: int = 30) -> list[dict]:
    """At least `count` questions: two batches written in parallel, then a top-up if some were unusable."""
    key = api_key()
    if not key:
        raise GeminiError("Add GEMINI_API_KEY to a .env file in the project, then try again.")
    questions: list[dict] = []
    seen: set[str] = set()

    def keep(payload) -> None:
        if not isinstance(payload, dict):
            return
        for item in _assessment_items(payload):
            question = clean(item)
            if not question:
                continue
            fingerprint = re.sub(r"\W+", " ", question["prompt"].lower()).strip()
            if fingerprint not in seen:
                seen.add(fingerprint)
                questions.append(question)

    errors = []
    with ThreadPoolExecutor(max_workers=len(ASSESSMENT_BATCHES)) as pool:
        jobs = [
            pool.submit(_assessment_batch, key, course, lesson, mix, angle, [])
            for mix, angle in ASSESSMENT_BATCHES
        ]
        for job in jobs:
            try:
                keep(job.result())
            except GeminiError as exc:
                errors.append(exc)
    if errors and not questions:
        raise errors[0]
    missing = count - len(questions)
    if missing > 0:
        mix = {"single": missing - missing // 3 + 2, "truefalse": missing // 3 + 1}
        avoid = [question["prompt"][:140] for question in questions]
        try:
            keep(_assessment_batch(key, course, lesson, mix, "any part of the lesson not covered yet", avoid))
        except GeminiError:
            pass
    if len(questions) < count:
        raise GeminiError(
            f"Gemini returned only {len(questions)} usable questions; an assessment needs {count}. Try again."
        )
    objective = [question for question in questions if question["type"] != "code"]
    random.shuffle(objective)
    return objective + [question for question in questions if question["type"] == "code"]


def _assessment_batch(key: str, course: dict, lesson: dict, mix: dict, angle: str, avoid: list[str]) -> dict:
    study = "\n".join(
        f"{section.get('label') or 'Note'}: {section.get('text') or ''}" for section in lesson.get("sections") or []
    )
    def plural(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'}"

    lists = []
    if mix.get("single"):
        lists.append(
            f"- single: {plural(mix['single'], 'question')}, each with 4 short choices; "
            "answer is the index of the one correct choice."
        )
    if mix.get("truefalse"):
        lists.append(
            f"- truefalse: {plural(mix['truefalse'], 'statement')}, a mix of true and false ones; "
            "true says whether each is true."
        )
    if mix.get("multi"):
        lists.append(
            f"- multi: {plural(mix['multi'], 'question')} with 4 or 5 choices; answers lists every correct index "
            "(at least 2, not all). End each prompt with 'Select all that apply.'"
        )
    if mix.get("fill"):
        lists.append(
            f"- fill: {plural(mix['fill'], 'sentence')}, each with exactly one blank written as ___; answers lists "
            "accepted answers (one to three words each, including common spellings or synonyms)."
        )
    if mix.get("match"):
        lists.append(f"- match: {plural(mix['match'], 'question')}, each with 4 pairs of a term and its meaning.")
    if mix.get("code"):
        languages = ", ".join(available_languages())
        lists.append(
            f"- code: 1 small coding task in one of: {languages}. "
            "Use sql when the course is about databases or SQL, otherwise the language that best fits the course. "
            "A beginner should finish it in 5 to 10 minutes, and it must relate to this lesson. "
            "For python or javascript the task is one function that returns its result (it does not print it): "
            "starter has the function signature with a placeholder body plus one line printing an example call; "
            "solution is the complete function with the same print line; tests lists 5 single-line calls of the "
            "function with literal arguments, such as add(2, 3), covering normal cases and edge cases. The first "
            "two tests are shown to the learner as examples and the rest stay hidden. Do not read input, files, "
            "the network, the clock, or random numbers. "
            "For sql, setup creates at most 3 small SQLite tables with under 12 rows each using CREATE TABLE and "
            "INSERT; starter is a simple query to edit; solution is one SELECT statement; check is 2 to 4 INSERT "
            "statements adding different rows to the same tables, used as a hidden check that the query works on "
            "other data. If no programming language fits the course at all, leave the code list empty."
        )
    empty = [name for name in ("single", "truefalse", "multi", "fill", "match", "code") if not mix.get(name)]
    if empty:
        lists.append(f"Leave these lists empty: {', '.join(empty)}.")
    avoid_text = ""
    if avoid:
        avoid_text = "These questions already exist; do not repeat or rephrase them:\n" + "\n".join(
            f"- {prompt}" for prompt in avoid
        ) + "\n\n"
    prompt = (
        "You are Lumina, a tutor writing part of a graded assessment for one lesson.\n"
        f"Course: {course.get('title') or 'Course'}\n"
        f"Focus: {course.get('goal') or 'the main idea'}\n"
        f"Lesson: {lesson.get('title') or 'Lesson'}\n"
        f"Study text:\n{study}\n\n"
        f"{avoid_text}"
        f"Questions in this part focus on {angle}.\n"
        "Write these lists:\n" + "\n".join(lists) + "\n"
        "Rules: keep every text short; wrong choices are plausible; do not use 'all of the above' or "
        "'none of the above'; every question tests a different idea or detail; stay within what a beginner "
        "could learn from this lesson and the basic background it relies on."
    )
    tokens = 12288 if mix.get("code") else 8192
    return _generate(key, prompt, ASSESSMENT_SCHEMA, "a question set", timeout=150, max_tokens=tokens, retries=3)


def explain_attempt(course: dict, lesson: dict, misses: list[dict], score: str) -> dict:
    """Feedback for each missed question. Each miss has number, kind, prompt, yours, and correct."""
    key = api_key()
    if not key:
        raise GeminiError("Add GEMINI_API_KEY to a .env file in the project, then try again.")
    study = "\n".join(
        f"{section.get('label') or 'Note'}: {section.get('text') or ''}" for section in lesson.get("sections") or []
    )
    blocks = []
    for miss in misses:
        blocks.append(
            f"Question {miss['number']} ({miss['kind']}): {miss['prompt']}\n"
            f"Learner's answer:\n{miss['yours']}\n"
            f"Correct answer:\n{miss['correct']}"
        )
    prompt = (
        "You are Lumina, a patient tutor. A learner just finished an assessment and you are reviewing the "
        "questions they missed.\n"
        f"Course: {course.get('title') or 'Course'}\n"
        f"Lesson: {lesson.get('title') or 'Lesson'}\n"
        f"Score: {score}\n"
        f"Study text:\n{study}\n\n"
        "Missed questions:\n\n" + "\n\n".join(blocks) + "\n\n"
        "For every missed question write feedback of 2 or 3 short sentences, addressed to the learner as 'you': "
        "name the likely misunderstanding behind their answer (or note that it was left blank), explain the idea "
        "that makes the correct answer right, and give one tip to remember it. For coding questions, point to "
        "the specific bug or missing case in their code and hint at the fix, without pasting the full solution. "
        "Use the question numbers given. Then write summary: at most 2 sentences on the pattern in these "
        "mistakes and what to review next. Plain text only; you may use `backticks` for code."
    )
    payload = _generate(key, prompt, FEEDBACK_SCHEMA, "feedback", timeout=90, max_tokens=4096)
    if not isinstance(payload, dict):
        raise GeminiError("Gemini returned feedback Lumina could not use. Try again.")
    numbers = {miss["number"] for miss in misses}
    items = {}
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        try:
            number = int(item.get("question"))
        except (TypeError, ValueError):
            continue
        text = _clip(item.get("feedback"), 900)
        if number in numbers and text:
            items[str(number)] = text
    if not items:
        raise GeminiError("Gemini returned feedback Lumina could not use. Try again.")
    return {"summary": _clip(payload.get("summary"), 500), "items": items}


def _assessment_items(payload: dict) -> list[dict]:
    def listed(name: str) -> list[dict]:
        return [item for item in payload.get(name) or [] if isinstance(item, dict)]

    single = [
        {"type": "single", "prompt": item.get("prompt"), "choices": item.get("choices"), "answers": [item.get("answer")]}
        for item in listed("single")
    ]
    truefalse = [
        {"type": "truefalse", "prompt": item.get("statement"), "answers": [0 if item.get("true") else 1]}
        for item in listed("truefalse")
    ]
    multi = [{"type": "multi", **item} for item in listed("multi")]
    fill = [
        {"type": "fill", "prompt": item.get("sentence"), "blanks": item.get("answers")}
        for item in listed("fill")
    ]
    match = [
        {
            "type": "match",
            "prompt": item.get("prompt"),
            "pairs": [
                {"left": pair.get("term"), "right": pair.get("meaning")}
                for pair in item.get("pairs") or []
                if isinstance(pair, dict)
            ],
        }
        for item in listed("match")
    ]
    code = [{"type": "code", **item} for item in listed("code")]
    order = [single[:1], truefalse, fill[:1], single[1:2], multi, fill[1:], single[2:], match, code]
    return [item for group in order for item in group]


def discuss(course: dict, history: list[dict], prompt: str, mode: str = "learn") -> str:
    key = api_key()
    if not key:
        raise GeminiError("Add GEMINI_API_KEY to a .env file in the project, then try again.")
    lessons = []
    scores = []
    for index, lesson in enumerate(course.get("lessons") or [], start=1):
        lines = [f"{index}. {lesson.get('title') or 'Lesson'}"]
        for section in lesson.get("sections") or []:
            lines.append(f"{section.get('label') or 'Note'}: {section.get('text') or ''}")
        lessons.append("\n".join(lines))
        attempts = lesson.get("attempts") or []
        if attempts:
            latest = attempts[-1]
            scores.append(f"{lesson.get('title') or 'Lesson'} {latest.get('score')}/{latest.get('total')}")
    manners = {
        "learn": "Teach one concept at a time. Explain it simply, give one real example, then ask one short check the learner can answer in their next message.",
        "practice": "Start with one practice question on the idea they asked about. When they answer, say if the idea is right and why, then offer a slightly harder or simpler follow-up.",
        "revise": "Use the recent quiz scores. Briefly revisit one weak idea, then ask them to try it again in their own words.",
        "ask": "Answer the question directly in a few sentences, then name the single next thing worth studying.",
    }
    manner = manners.get(mode, manners["learn"])
    record = "; ".join(scores) if scores else "No quiz scores yet."
    system = (
        "You are Lumina, a patient tutor. Stay on this course. "
        "Do not dump a whole chapter. Let the learner set the pace. "
        "If recent quizzes are strong, go one step further. If they are weak, use a simpler example and do not treat one miss as failure. "
        "If they ask for a quiz answer, explain the idea instead of only naming the choice. "
        "Plain text is fine. You may use **bold** for a key term.\n"
        f"{manner}\n"
        f"Course: {course.get('title') or 'Course'}\n"
        f"Focus: {course.get('goal') or 'the main idea'}\n"
        f"Overview: {course.get('overview') or ''}\n"
        f"Recent quizzes: {record}\n"
        "Lessons:\n"
        + "\n\n".join(lessons)
    )
    contents = []
    for note in history[-16:]:
        asked = " ".join(str(note.get("prompt") or "").split())
        answer = _reply_text(note.get("reply"))
        if not asked or not answer:
            continue
        contents.append({"role": "user", "parts": [{"text": asked}]})
        contents.append({"role": "model", "parts": [{"text": answer}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    text = _generate_text(key, contents, system)
    if not text:
        raise GeminiError("Gemini did not answer. Try again.")
    return text


def _reply_text(reply) -> str:
    if isinstance(reply, dict):
        parts = [step.get("text") or "" for step in reply.get("steps") or [] if isinstance(step, dict)]
        return " ".join(part for part in parts if part).strip()
    return " ".join(str(reply or "").split())


def _generate(
    key: str,
    prompt: str,
    schema: dict,
    what: str = "a lesson plan",
    timeout: int = 60,
    max_tokens: int | None = None,
    retries: int = 1,
) -> dict:
    config = {
        "temperature": 0.7,
        "responseMimeType": "application/json",
        "responseSchema": schema,
    }
    if max_tokens:
        config["maxOutputTokens"] = max_tokens
    parsed = _post(
        key,
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        },
        timeout,
        retries,
    )
    try:
        return json.loads(_strip_fence(_candidate_text(parsed)))
    except (json.JSONDecodeError, GeminiError) as exc:
        raise GeminiError(f"Gemini returned {what} Lumina could not use. Try again.") from exc


def _generate_text(key: str, contents: list[dict], system: str) -> str:
    parsed = _post(
        key,
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7},
        },
    )
    return _clip(_candidate_text(parsed), 2500)


def _post(key: str, body: dict, timeout: int = 60, retries: int = 1) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        if exc.code in (500, 503) and retries > 0:
            time.sleep(3 + random.random() * 4)
            return _post(key, body, timeout, retries - 1)
        if exc.code == 429:
            raise GeminiError(
                "The Gemini API key has reached its usage limit. Wait a while, or check the key's plan and billing."
            ) from exc
        message = _error_message(detail) or "Gemini could not answer."
        raise GeminiError(message) from exc
    except urllib.error.URLError as exc:
        raise GeminiError("Gemini could not be reached. Try again in a moment.") from exc
    except (TimeoutError, OSError) as exc:
        raise GeminiError("Gemini took too long to answer. Try again in a moment.") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GeminiError("Gemini could not answer. Try again.") from exc


def _candidate_text(parsed: dict) -> str:
    try:
        return parsed["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise GeminiError("Gemini could not answer. Try again.") from exc


def _plan(payload: dict, title: str, focus: str) -> tuple[str, list[dict]]:
    lessons_in = payload.get("lessons") if isinstance(payload, dict) else None
    if not isinstance(lessons_in, list) or len(lessons_in) < 3:
        raise GeminiError("Gemini returned a lesson plan Lumina could not use. Try again.")
    lessons = []
    for item in lessons_in[:4]:
        if not isinstance(item, dict):
            raise GeminiError("Gemini returned a lesson plan Lumina could not use. Try again.")
        sections = _sections(item.get("sections"))
        quiz = _quiz(item.get("quiz"))
        if len(sections) < 2 or len(quiz) != 3:
            raise GeminiError("Gemini returned a lesson plan Lumina could not use. Try again.")
        minutes = item.get("minutes")
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 15
        minutes = min(40, max(10, minutes))
        lessons.append(
            {
                "title": _clip(item.get("title"), 120) or "Lesson",
                "minutes": minutes,
                "sections": sections,
                "quiz": quiz,
                "studied": None,
                "attempts": [],
            }
        )
    overview = _clip(payload.get("overview"), 280)
    if not overview:
        overview = f"Four lessons on {title}, aimed at {focus}. Study a lesson, then take its quiz."
    return overview, lessons


def _sections(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    sections = []
    for item in value[:3]:
        if not isinstance(item, dict):
            continue
        text = _clip(item.get("text"), 700)
        if not text:
            continue
        sections.append({"label": _clip(item.get("label"), 40) or "Note", "text": text})
    return sections


def _quiz(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    questions = []
    for item in value[:3]:
        question = _question(item, 3)
        if question is None:
            return []
        questions.append(question)
    return questions


def _question(item, size: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    choices = item.get("choices")
    if not isinstance(choices, list):
        return None
    cleaned = [_clip(choice, 240) for choice in choices if _clip(choice, 240)]
    if len(cleaned) != size or len(set(cleaned)) != size:
        return None
    try:
        answer = int(item.get("answer"))
    except (TypeError, ValueError):
        return None
    if answer < 0 or answer >= size:
        return None
    prompt = _clip(item.get("prompt"), 300)
    if not prompt:
        return None
    return {"prompt": prompt, "choices": cleaned, "answer": answer}


def _clip(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip()


def _strip_fence(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1]
        if body.endswith("```"):
            body = body[: body.rfind("```")]
    return body.strip()


def _error_message(detail: str) -> str:
    try:
        message = json.loads(detail)["error"]["message"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return ""
    text = " ".join(str(message).split())
    if not text:
        return ""
    return text[:180]
