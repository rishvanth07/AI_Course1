#!/usr/bin/env python3
"""Lumina — a small AI portal for smart learning. Standard library only."""

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from datetime import date, timedelta
from html import escape
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from db import create_account, init_db, read_account, read_user, session_secret, update_user
from gemini import GeminiError, discuss, draft_assessment, draft_lessons, explain_attempt
from questions import (
    BLANK,
    LABELS,
    LANGUAGES,
    TYPES,
    answered,
    fill_matches,
    format_table,
    grade,
    hidden_count,
    kind_of,
    label,
    run_code,
    run_sql,
    sample_tests,
    seconds_for,
    sql_tables,
)

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5057
SECRET = b""
PASSWORD_ROUNDS = 600_000
LOGIN_LIMIT = 5
LOGIN_WINDOW = 15 * 60
LOGIN_FAILURES: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COURSE_RE = re.compile(r"/courses/([a-f0-9]{8})(?:/(prompt|quiz))?$")
LESSON_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)$")
LESSON_OPEN_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/open$")
LESSON_ASSESS_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/assess$")
LESSON_QUIZ_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/quiz$")
LESSON_PREPARE_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/assess/prepare$")
LESSON_RUN_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/assess/run$")
LESSON_FEEDBACK_RE = re.compile(r"/courses/([a-f0-9]{8})/lessons/(\d+)/assess/feedback$")
CERTIFICATE_RE = re.compile(r"/courses/([a-f0-9]{8})/certificate$")
SESSION_SECONDS = 60 * 60 * 24 * 14

PATHS = [
    {
        "index": "01",
        "title": "Name the idea",
        "text": "One sentence you could teach. If you cannot say it, the lesson stays here.",
    },
    {
        "index": "02",
        "title": "Try something small",
        "text": "A single exercise, not a chapter. Small enough to finish before your attention leaves.",
    },
    {
        "index": "03",
        "title": "Check the gap",
        "text": "The tutor asks the part that still feels fuzzy, then waits for your words.",
    },
    {
        "index": "04",
        "title": "Return on purpose",
        "text": "A second pass when the idea is about to fade, so it stays instead of feeling familiar.",
    },
]

COURSES = [
    {
        "tag": "Code",
        "title": "Python, patiently",
        "level": "Beginner",
        "hours": "6 hours",
        "outcome": "Write small programs you can explain out loud.",
    },
    {
        "tag": "Data",
        "title": "Numbers that mean something",
        "level": "Intermediate",
        "hours": "4 hours",
        "outcome": "Read a chart without being fooled by the scale.",
    },
    {
        "tag": "Math",
        "title": "Calculus in pictures",
        "level": "Beginner",
        "hours": "5 hours",
        "outcome": "See change first, then give it a name.",
    },
    {
        "tag": "Writing",
        "title": "Clear writing",
        "level": "All levels",
        "hours": "3 hours",
        "outcome": "Say one thing per sentence, and stop.",
    },
    {
        "tag": "Machines",
        "title": "Learning machines",
        "level": "Intermediate",
        "hours": "8 hours",
        "outcome": "Know what a model can do, and what it only seems to do.",
    },
    {
        "tag": "Systems",
        "title": "How systems break",
        "level": "Intermediate",
        "hours": "4 hours",
        "outcome": "Find the constraint before you reach for a fix.",
    },
]

SUGGESTIONS = ("Python loops", "Calculus", "Clear writing", "Reading charts")

TOPICS = [
    {
        "keys": ("python", "code", "coding", "programming", "loop", "function"),
        "title": "Python, from first principles",
        "minutes": 25,
        "next": "Functions, and what they can see",
        "steps": [
            {
                "label": "Concept",
                "text": "A loop visits each item once. An empty list means the body never runs.",
            },
            {
                "label": "Try",
                "text": "Write a loop that prints each word in a list, then run it on an empty list.",
            },
            {
                "label": "Check",
                "text": "Say what the loop variable is after the loop ends. Then test that guess.",
            },
        ],
    },
    {
        "keys": ("calculus", "derivative", "integral", "math", "algebra"),
        "title": "Change, seen before it is named",
        "minutes": 30,
        "next": "Slope at a single point",
        "steps": [
            {
                "label": "Concept",
                "text": "A derivative is how fast a quantity is changing at one moment, not across a whole trip.",
            },
            {
                "label": "Try",
                "text": "Sketch a hill. Mark where you are climbing, where you are flat, and where you are coming down.",
            },
            {
                "label": "Check",
                "text": "Point to the steepest spot and say what a large derivative would mean there.",
            },
        ],
    },
    {
        "keys": ("write", "writing", "essay", "sentence", "grammar"),
        "title": "Sentences that carry one idea",
        "minutes": 20,
        "next": "Cutting a paragraph in half",
        "steps": [
            {
                "label": "Concept",
                "text": "A clear sentence makes one claim. The next sentence may add evidence, not a second claim.",
            },
            {
                "label": "Try",
                "text": "Take a muddy sentence you wrote and split it until each piece says only one thing.",
            },
            {
                "label": "Check",
                "text": "Read the new lines aloud. If you run out of breath, it still holds two ideas.",
            },
        ],
    },
    {
        "keys": ("data", "chart", "statistics", "stats", "graph"),
        "title": "Reading a chart without the trick",
        "minutes": 25,
        "next": "Averages that hide a split",
        "steps": [
            {
                "label": "Concept",
                "text": "The axis is part of the argument. A cropped scale can make a small change look large.",
            },
            {
                "label": "Try",
                "text": "Find one chart and write down where the vertical axis starts. Zero, or somewhere else?",
            },
            {
                "label": "Check",
                "text": "Redraw the same points from zero. Did the story survive?",
            },
        ],
    },
    {
        "keys": ("machine", "ml", "model", "ai", "neural"),
        "title": "What a model is actually doing",
        "minutes": 30,
        "next": "Training data, and what it left out",
        "steps": [
            {
                "label": "Concept",
                "text": "A model finds patterns in examples. It does not know the world those examples came from.",
            },
            {
                "label": "Try",
                "text": "Name a task, then list three kinds of examples a model would need to see.",
            },
            {
                "label": "Check",
                "text": "Name one situation missing from that list. That is where it will sound sure and be wrong.",
            },
        ],
    },
    {
        "keys": ("system", "systems", "design", "debug", "bug"),
        "title": "Find the constraint first",
        "minutes": 25,
        "next": "One change, then measure again",
        "steps": [
            {
                "label": "Concept",
                "text": "A system fails at its narrowest point. Fixing a wide part will not move the result.",
            },
            {
                "label": "Try",
                "text": "Pick a slow process you know and write the single step everything else waits on.",
            },
            {
                "label": "Check",
                "text": "If that step got twice as fast, would the whole process? If not, you chose the wrong step.",
            },
        ],
    },
]


def esc(value) -> str:
    return escape(str(value), quote=True)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ROUNDS)
    return f"pbkdf2_sha256${PASSWORD_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    except ValueError:
        return False
    return hmac.compare_digest(actual.hex(), digest)


DUMMY_HASH = hash_password(secrets.token_hex(16))


def password_stamp(stored: str) -> str:
    return hashlib.sha256(stored.encode()).hexdigest()[:16]


def session_digest(email: str, expires: int, stamp: str) -> str:
    return hmac.new(SECRET, f"{email}|{expires}|{stamp}".encode(), hashlib.sha256).hexdigest()


def sign_session(email: str, stored: str) -> str:
    expires = int(time.time()) + SESSION_SECONDS
    stamp = password_stamp(stored)
    return f"{email}.{expires}.{stamp}.{session_digest(email, expires, stamp)}"


def read_session(token: str) -> str | None:
    parts = token.rsplit(".", 3)
    if len(parts) != 4:
        return None
    email, expires, stamp, digest = parts
    if not EMAIL_RE.fullmatch(email) or not expires.isdigit() or int(expires) < time.time():
        return None
    if not hmac.compare_digest(digest, session_digest(email, int(expires), stamp)):
        return None
    account = read_account(email)
    if not account or not account["password_hash"]:
        return None
    if not hmac.compare_digest(stamp, password_stamp(account["password_hash"])):
        return None
    return email


def session_cookie(email: str | None, stored: str = "") -> str:
    cookie = SimpleCookie()
    cookie["lumina"] = sign_session(email, stored) if email else ""
    cookie["lumina"]["path"] = "/"
    cookie["lumina"]["httponly"] = True
    cookie["lumina"]["samesite"] = "Lax"
    cookie["lumina"]["max-age"] = str(SESSION_SECONDS if email else 0)
    return cookie.output(header="").strip()


def account_markup(email: str | None, *, dashboard: bool = False) -> str:
    if not email:
        return (
            '<a class="btn btn-ghost" href="/login">Sign in</a>'
            '<a class="btn btn-solid" href="/signup">Create account</a>'
        )
    safe = esc(email)
    current = ' class="btn btn-ghost is-current"' if dashboard else ' class="btn btn-ghost"'
    return (
        f'<a{current} href="/dashboard">Dashboard</a>'
        f'<span class="whoami" title="{safe}">{esc(account_name(email))}</span>'
        '<form class="signout" method="post" action="/logout">'
        '<button class="btn btn-ghost" type="submit">Sign out</button>'
        "</form>"
    )


ICON_HOME = (
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">'
    '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z" '
    'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
    "</svg>"
)
ICON_COURSES = (
    '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">'
    '<path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5z" '
    'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>'
    "</svg>"
)


def side_link(href: str, label: str, icon: str, current: bool) -> str:
    cls = "side-link is-current" if current else "side-link"
    attr = ' aria-current="page"' if current else ""
    return f'<a class="{cls}" href="{href}"{attr}>{icon}<span>{label}</span></a>'


def sidebar_nav(here: str, email: str, course_id: str = "") -> str:
    courses = (read_user(email).get("courses") or [])[:8]
    rows = [
        '<p class="side-kicker">Learn</p>',
        side_link("/dashboard", "Overview", ICON_HOME, here == "dashboard"),
        side_link("/courses", "Courses", ICON_COURSES, here == "courses"),
    ]
    if courses:
        rows.append('<p class="side-kicker">Your courses</p>')
        for course in courses:
            current = course.get("id") == course_id
            cls = "side-link side-course is-current" if current else "side-link side-course"
            attr = ' aria-current="page"' if current else ""
            title = esc(course.get("title") or "Course")
            initial = esc((course.get("title") or "C")[:1].upper())
            rows.append(
                f'<a class="{cls}" href="/courses/{esc(course.get("id") or "")}"{attr}>'
                f'<span class="mini" aria-hidden="true">{initial}</span>'
                f'<span class="side-label">{title}</span></a>'
            )
    return "".join(rows)


def sidebar_user(email: str) -> str:
    name = account_name(email)
    initial = esc(name[:1].upper())
    return (
        '<div class="side-user">'
        f'<span class="avatar" aria-hidden="true">{initial}</span>'
        f'<span class="side-mail" title="{esc(email)}">{esc(name)}</span>'
        "</div>"
        '<form method="post" action="/logout">'
        '<button class="side-out" type="submit" title="Sign out">'
        '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">'
        '<path d="M10 7V5a2 2 0 0 1 2-2h7v18h-7a2 2 0 0 1-2-2v-2M15 12H3m0 0 3-3m-3 3 3 3" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
        "<span>Sign out</span></button>"
        "</form>"
    )


def draft_path(query: str) -> dict:
    text = " ".join(query.lower().split())
    for topic in TOPICS:
        if any(key in text for key in topic["keys"]):
            return {
                "title": topic["title"],
                "minutes": topic["minutes"],
                "next": topic["next"],
                "steps": topic["steps"],
            }

    subject = " ".join(query.split())
    return {
        "title": f"A first pass on {subject}",
        "minutes": 20,
        "next": "A second example, slightly harder",
        "steps": [
            {
                "label": "Concept",
                "text": f"Say “{subject}” in one sentence a newcomer could repeat.",
            },
            {
                "label": "Try",
                "text": "Do the smallest version of it once, with a real example from your own work.",
            },
            {
                "label": "Check",
                "text": "Close the notes and explain it again. The missing word is the next lesson.",
            },
        ],
    }


QUIZZES = [
    {
        "keys": ("python", "code", "coding", "programming", "loop", "function"),
        "title": "Loops, in three questions",
        "questions": [
            {
                "prompt": "A for-loop is given an empty list. What does the body do?",
                "choices": ["It runs once.", "It never runs.", "Python stops the program."],
                "answer": 1,
            },
            {
                "prompt": "What is worth testing after the loop ends?",
                "choices": [
                    "What the loop variable still points at.",
                    "How many comments you added.",
                    "Whether the file is named main.py.",
                ],
                "answer": 0,
            },
            {
                "prompt": "Which session is finished?",
                "choices": [
                    "You can say the idea and you tried it once.",
                    "You highlighted a whole chapter.",
                    "You copied an example you cannot explain.",
                ],
                "answer": 0,
            },
        ],
    },
    {
        "keys": ("calculus", "derivative", "integral", "math", "algebra"),
        "title": "Change, in three questions",
        "questions": [
            {
                "prompt": "A derivative describes change where?",
                "choices": ["Across a whole trip.", "At one moment.", "Only at zero."],
                "answer": 1,
            },
            {
                "prompt": "You are on a flat part of a hill. The derivative is…",
                "choices": ["Large.", "Near zero.", "Impossible to discuss."],
                "answer": 1,
            },
            {
                "prompt": "Where is the derivative largest?",
                "choices": ["The steepest spot.", "The highest spot.", "The starting spot."],
                "answer": 0,
            },
        ],
    },
    {
        "keys": ("write", "writing", "essay", "sentence", "grammar"),
        "title": "Sentences, in three questions",
        "questions": [
            {
                "prompt": "A clear sentence holds how many claims?",
                "choices": ["One.", "As many as fit.", "At least two, for balance."],
                "answer": 0,
            },
            {
                "prompt": "You run out of breath reading a line aloud. What does that usually mean?",
                "choices": [
                    "It still holds two ideas.",
                    "The font is too small.",
                    "The claim is already clear.",
                ],
                "answer": 0,
            },
            {
                "prompt": "The sentence after a claim should usually add…",
                "choices": ["Evidence.", "A second claim.", "A new topic."],
                "answer": 0,
            },
        ],
    },
    {
        "keys": ("data", "chart", "statistics", "stats", "graph"),
        "title": "Charts, in three questions",
        "questions": [
            {
                "prompt": "Which part of a chart is part of the argument?",
                "choices": ["The axis scale.", "The color of the border.", "The caption font."],
                "answer": 0,
            },
            {
                "prompt": "A vertical axis that does not start at zero can…",
                "choices": [
                    "Make a small change look large.",
                    "Make the data more honest.",
                    "Remove the need to read the title.",
                ],
                "answer": 0,
            },
            {
                "prompt": "How do you test a dramatic chart?",
                "choices": [
                    "Redraw the same points from zero.",
                    "Trust the steepest line.",
                    "Read only the title.",
                ],
                "answer": 0,
            },
        ],
    },
    {
        "keys": ("machine", "ml", "model", "ai", "neural"),
        "title": "Models, in three questions",
        "questions": [
            {
                "prompt": "What does a model actually learn from?",
                "choices": ["The examples it was shown.", "The whole world.", "Your intention."],
                "answer": 0,
            },
            {
                "prompt": "A confident answer about a missing situation is…",
                "choices": [
                    "Where it is most likely wrong.",
                    "Proof the model understands.",
                    "A sign the training is finished.",
                ],
                "answer": 0,
            },
            {
                "prompt": "Before you trust a model on a task, you should name…",
                "choices": [
                    "Three kinds of examples it needed to see.",
                    "Only the accuracy number.",
                    "The logo on the tool.",
                ],
                "answer": 0,
            },
        ],
    },
    {
        "keys": ("system", "systems", "design", "debug", "bug"),
        "title": "Constraints, in three questions",
        "questions": [
            {
                "prompt": "A system fails first at…",
                "choices": ["Its narrowest point.", "Its widest point.", "The newest part."],
                "answer": 0,
            },
            {
                "prompt": "You speed up a step that nothing is waiting on. The process…",
                "choices": ["May not get faster.", "Always gets twice as fast.", "Cannot be measured."],
                "answer": 0,
            },
            {
                "prompt": "How do you know you found the constraint?",
                "choices": [
                    "Making that step faster moves the whole result.",
                    "The step has the longest name.",
                    "It was the last thing you touched.",
                ],
                "answer": 0,
            },
        ],
    },
]


def build_quiz(subject: str) -> dict:
    text = subject.lower()
    for quiz in QUIZZES:
        if any(key in text for key in quiz["keys"]):
            return {"title": quiz["title"], "questions": quiz["questions"]}
    path = draft_path(subject)
    concept = path["steps"][0]["text"]
    return {
        "title": "A short check",
        "questions": [
            {
                "prompt": f"What belongs in the first step on {subject}?",
                "choices": [
                    concept,
                    "A long definition you have not tried.",
                    "A project too big to finish today.",
                ],
                "answer": 0,
            },
            {
                "prompt": "A finished sitting ends when you can…",
                "choices": [
                    "Say the idea and test it once.",
                    "Highlight every paragraph.",
                    "Repeat a sentence you do not understand.",
                ],
                "answer": 0,
            },
            {
                "prompt": "The check is useful when it shows…",
                "choices": [
                    "The word you still cannot explain.",
                    "How fast you clicked.",
                    "How many notes you copied.",
                ],
                "answer": 0,
            },
        ],
    }


def today_key() -> str:
    return date.today().isoformat()


def new_course(title: str, goal: str) -> dict:
    overview, lessons = draft_lessons(title, goal)
    return {
        "id": secrets.token_hex(4),
        "title": title,
        "goal": goal,
        "created": today_key(),
        "overview": overview,
        "lessons": lessons,
        "path": None,
        "notes": [],
        "quiz": {"title": "", "questions": []},
        "attempts": [],
    }


def ensure_plans(email: str) -> dict:
    user = read_user(email)
    courses = user.get("courses") or []
    if not courses or all(course.get("lessons") for course in courses):
        return user

    def mutate(found: dict) -> None:
        for course in found.get("courses") or []:
            if course.get("lessons"):
                continue
            try:
                overview, lessons = draft_lessons(course.get("title") or "Course", course.get("goal") or "")
            except GeminiError:
                continue
            course["lessons"] = lessons
            course["overview"] = overview

    return update_user(email, mutate)


def course_progress(course: dict) -> tuple[int, int, int]:
    lessons = course.get("lessons") or []
    total = len(lessons)
    done = sum(1 for lesson in lessons if lesson.get("attempts"))
    percent = round(100 * done / total) if total else 0
    return done, total, percent


def find_course(user: dict, course_id: str) -> dict | None:
    for course in user.get("courses", []):
        if course.get("id") == course_id:
            return course
    return None


def path_html(path: dict) -> str:
    steps = "".join(
        "<li>"
        f"<strong>{esc(step['label'])}</strong>"
        f"<p>{esc(step['text'])}</p>"
        "</li>"
        for step in path["steps"]
    )
    return (
        '<article class="plan">'
        "<header>"
        f"<h2>{esc(path['title'])}</h2>"
        f"<span class=\"minutes\">{esc(str(path['minutes']))} min</span>"
        "</header>"
        f"<ol>{steps}</ol>"
        f"<p class=\"next\">Then: {esc(path['next'])}</p>"
        "</article>"
    )


def render_page(email: str | None = None) -> str:
    suggestions = "\n".join(
        f'<button class="chip" type="button" data-query="{esc(item)}">{esc(item)}</button>'
        for item in SUGGESTIONS
    )
    paths = "\n".join(
        "<li>"
        f'<span class="num">{esc(item["index"])}</span>'
        f"<h3>{esc(item['title'])}</h3>"
        f"<p>{esc(item['text'])}</p>"
        "</li>"
        for item in PATHS
    )
    courses = "\n".join(
        "<article class=\"card\">"
        '<div class="card-top">'
        f'<span class="pill">{esc(item["tag"])}</span>'
        f'<span class="meta">{esc(item["level"])} · {esc(item["hours"])}</span>'
        "</div>"
        f"<h3>{esc(item['title'])}</h3>"
        f"<p>{esc(item['outcome'])}</p>"
        f'<button class="text-link" type="button" data-query="{esc(item["title"])}">'
        'Draft this path <span aria-hidden="true">→</span></button>'
        "</article>"
        for item in COURSES
    )
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    return (
        template.replace("<!--SUGGESTIONS-->", suggestions)
        .replace("<!--PATHS-->", paths)
        .replace("<!--COURSES-->", courses)
        .replace("<!--ACCOUNT-->", account_markup(email))
    )


def render_auth(page: str, error: str = "", fields: dict[str, str] | None = None) -> str:
    template = (ROOT / "templates" / f"{page}.html").read_text(encoding="utf-8")
    message = f'<p class="hint" role="alert">{error}</p>' if error else ""
    fields = fields or {}
    return (
        template.replace("<!--ERROR-->", message)
        .replace("<!--EMAIL-->", esc(fields.get("email", "")))
        .replace("<!--NAME-->", esc(fields.get("name", "")))
    )


def normal_email(value: str) -> str:
    return value.strip().lower()


def login_wait(email: str) -> int:
    """Seconds until this email may try again, or 0."""
    now = time.time()
    with LOGIN_LOCK:
        recent = [at for at in LOGIN_FAILURES.get(email, []) if now - at < LOGIN_WINDOW]
        LOGIN_FAILURES[email] = recent
        if len(recent) < LOGIN_LIMIT:
            return 0
        return int(LOGIN_WINDOW - (now - recent[0])) + 1


def note_login(email: str, ok: bool) -> None:
    with LOGIN_LOCK:
        if ok:
            LOGIN_FAILURES.pop(email, None)
        else:
            LOGIN_FAILURES.setdefault(email, []).append(time.time())


def authenticate(email: str, password: str) -> tuple[str | None, str]:
    """Return (error_html, password_hash). error_html is None when the login is good."""
    if not EMAIL_RE.fullmatch(email) or len(email) > 180 or not password:
        return "Enter your email and password.", ""
    wait = login_wait(email)
    if wait:
        minutes = max(1, round(wait / 60))
        return f"Too many failed attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.", ""
    account = read_account(email)
    stored = account["password_hash"] if account else ""
    if account and not stored:
        return (
            "This account was created before passwords were saved. "
            f'<a href="/signup?email={esc(quote(email))}">Set a password</a> to keep your courses.'
        ), ""
    ok = verify_password(password, stored or DUMMY_HASH)
    note_login(email, ok and bool(stored))
    if not ok or not stored:
        return "Email or password is incorrect.", ""
    return None, stored


def register(name: str, email: str, password: str, confirm: str) -> tuple[str | None, str]:
    """Return (error, password_hash). error is None when the account was created."""
    if not 2 <= len(name) <= 60:
        return "Enter your name (2 to 60 characters).", ""
    if not EMAIL_RE.fullmatch(email) or len(email) > 180:
        return "Enter a complete email address.", ""
    if not 8 <= len(password) <= 128:
        return "Use a password of 8 to 128 characters.", ""
    if password.lower() == email or password.isdigit() or len(set(password)) < 4:
        return "Choose a less guessable password.", ""
    if password != confirm:
        return "The two passwords don't match.", ""
    stored = hash_password(password)
    if not create_account(email, name, stored, today_key()):
        return 'An account with this email already exists. <a href="/login">Sign in</a> instead.', ""
    return None, stored


def account_name(email: str) -> str:
    account = read_account(email)
    return (account or {}).get("name") or email.split("@", 1)[0]


def add_count(counts: dict[str, int], day: str | None, amount: int = 1) -> None:
    if not day:
        return
    key = day[:10]
    counts[key] = counts.get(key, 0) + amount


def activity_counts(user: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    undated = 0
    for course in user.get("courses") or []:
        if course.get("created"):
            add_count(counts, course.get("created"))
        else:
            undated += 1
        for note in course.get("notes") or []:
            if note.get("at"):
                add_count(counts, note.get("at"))
            else:
                undated += 1
        for attempt in course.get("attempts") or []:
            if attempt.get("at"):
                add_count(counts, attempt.get("at"))
            else:
                undated += 1
        for lesson in course.get("lessons") or []:
            if lesson.get("studied"):
                add_count(counts, lesson.get("studied"))
            for attempt in lesson.get("attempts") or []:
                if attempt.get("at"):
                    add_count(counts, attempt.get("at"))
                else:
                    undated += 1
    if undated:
        add_count(counts, today_key(), undated)
    return counts


def heat_level(count: int) -> int:
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count <= 3:
        return 2
    return 3


def heatmap_html(email: str, user: dict) -> str:
    counts = activity_counts(user)
    end = date.today()
    start = end - timedelta(days=end.weekday() + 17 * 7)
    weeks: list[list[tuple[date, int, str]]] = []
    week: list[tuple[date, int, str]] = []
    cursor = start
    while cursor <= end:
        count = counts.get(cursor.isoformat(), 0)
        label = cursor.strftime("%d %b %Y").lstrip("0")
        if count == 1:
            title = f"1 activity on {label}"
        elif count:
            title = f"{count} activities on {label}"
        else:
            title = f"No activity on {label}"
        week.append((cursor, heat_level(count), title))
        if len(week) == 7:
            weeks.append(week)
            week = []
        cursor += timedelta(days=1)
    if week:
        weeks.append(week)

    months = []
    seen = ""
    for column in weeks:
        name = column[0][0].strftime("%b")
        months.append(name if name != seen else "")
        seen = name
    month_html = "".join(f"<span>{esc(name)}</span>" for name in months)
    cells = []
    for column in weeks:
        for _day, level, title in column:
            cells.append(f'<i class="lv{level}" title="{esc(title)}"></i>')
    total = sum(counts.values())
    name = account_name(email)
    initial = esc(name[:1].upper())
    return (
        '<section class="panel profile">'
        '<div class="profile-head">'
        f'<span class="avatar" aria-hidden="true">{initial}</span>'
        "<div>"
        f"<h2>{esc(name)}</h2>"
        f'<p class="sub">{esc(email)}</p>'
        "</div>"
        f'<p class="heat-total">{total} in the last 18 weeks</p>'
        "</div>"
        '<div class="heat" aria-label="Activity heatmap">'
        f'<div class="heat-months">{month_html}</div>'
        '<div class="heat-body">'
        '<div class="heat-labels"><span>Mon</span><span>Wed</span><span>Fri</span></div>'
        f'<div class="heat-grid">{"".join(cells)}</div>'
        "</div>"
        '<div class="heat-legend"><span>Less</span>'
        '<i class="lv0"></i><i class="lv1"></i><i class="lv2"></i><i class="lv3"></i>'
        "<span>More</span></div>"
        "</div>"
        "</section>"
    )


COVERS = [
    (("python", "code", "coding", "programming", "loop", "function"), "cover-python.jpg"),
    (("calculus", "derivative", "integral", "math", "algebra"), "cover-math.jpg"),
    (("write", "writing", "essay", "sentence", "grammar"), "cover-writing.jpg"),
    (("data", "chart", "statistics", "stats", "graph"), "cover-data.jpg"),
    (("machine", "ml", "model", "ai", "neural"), "cover-ai.jpg"),
    (("system", "systems", "design", "debug", "bug"), "cover-systems.jpg"),
]


def course_cover(course: dict) -> str:
    text = f"{course.get('title', '')} {course.get('goal', '')}".lower()
    for keys, name in COVERS:
        if any(key in text for key in keys):
            return f"/static/covers/{name}"
    return "/static/covers/cover-learn.jpg"


def course_list_html(courses: list[dict]) -> str:
    if not courses:
        return '<p class="empty-note">No courses yet. Create one above and Gemini will draft a lesson plan.</p>'
    cards = []
    for course in courses:
        done, total, percent = course_progress(course)
        progress_label = f"{done} of {total} lessons" if total else "Lesson plan"
        goal = course.get("goal") or "Open the course and start the first lesson."
        cards.append(
            f'<a class="learn-card" href="/courses/{esc(course["id"])}">'
            f'<span class="card-cover"><img src="{course_cover(course)}" alt=""></span>'
            '<span class="card-body">'
            f"<h3>{esc(course['title'])}</h3>"
            f"<p>{esc(goal)}</p>"
            f'<span class="card-meta">{esc(progress_label)}</span>'
            f'<span class="card-bar" aria-hidden="true"><span style="width:{percent}%"></span></span>'
            "</span></a>"
        )
    return f'<div class="card-grid">{"".join(cards)}</div>'


def reply_html(path: dict) -> str:
    paragraphs = [
        f"<p><strong>{esc(step['label'])}.</strong> {esc(step['text'])}</p>"
        for step in path["steps"]
    ]
    paragraphs.append(f"<p>Next: {esc(path['next'])}</p>")
    return "".join(paragraphs)


def user_bubble(text: str) -> str:
    return (
        '<div class="msg msg-user">'
        f'<div class="bubble">{esc(text)}</div>'
        "</div>"
    )


def tutor_bubble(path: dict) -> str:
    return (
        '<div class="msg msg-tutor">'
        '<span class="avatar" aria-hidden="true">L</span>'
        '<div class="bubble-wrap">'
        f'<div class="bubble">{reply_html(path)}</div>'
        '<div class="msg-actions"><button type="button" class="msg-copy">Copy</button></div>'
        "</div></div>"
    )


def format_inline(value: str) -> str:
    text = esc(value)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def tutor_text(text: str) -> str:
    blocks = [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]
    paragraphs = "".join(
        f"<p>{format_inline(part).replace(chr(10), '<br>')}</p>" for part in blocks
    )
    if not paragraphs:
        paragraphs = "<p>Ask anything about this course.</p>"
    return (
        '<div class="msg msg-tutor">'
        '<span class="avatar" aria-hidden="true">L</span>'
        '<div class="bubble-wrap">'
        f'<div class="bubble">{paragraphs}</div>'
        '<div class="msg-actions"><button type="button" class="msg-copy">Copy</button></div>'
        "</div></div>"
    )


def opening_line(course: dict) -> str:
    title = course.get("title") or "this course"
    goal = course.get("goal") or "the main idea"
    overview = course.get("overview") or ""
    lead = f"What do you want to understand about {title}? The focus is {goal}."
    if overview:
        lead = f"{lead} {overview}"
    return lead + " Ask a question, or open a lesson on the right and take its assessment."


def suggestion_html(course: dict) -> str:
    if course.get("notes"):
        return ""
    prompts = [
        ("Explain the first lesson in plain language.", "Explain the first lesson"),
        ("What should I study next?", "What next?"),
        ("Give me one real example from this course.", "Give me an example"),
    ]
    chips = "".join(
        f'<button type="button" class="suggest" data-prompt="{esc(prompt)}">{esc(label)}</button>'
        for prompt, label in prompts
    )
    lessons = course.get("lessons") or []
    if lessons:
        target = next((index for index, lesson in enumerate(lessons) if not lesson.get("attempts")), 0)
        chips += f'<a class="suggest" href="{assess_url(course, target)}">Take an assessment</a>'
    return f'<div class="suggestions" aria-label="Suggestions">{chips}</div>'


def assess_url(course: dict, index: int) -> str:
    return f"/courses/{esc(course['id'])}/lessons/{index}/assess"


def chat_html(course: dict) -> str:
    parts = [tutor_text(opening_line(course)), suggestion_html(course)]
    for note in course.get("notes") or []:
        parts.append(user_bubble(note.get("prompt") or ""))
        reply = note.get("reply")
        if isinstance(reply, dict) and reply.get("steps"):
            parts.append(tutor_bubble(reply))
        else:
            parts.append(tutor_text(str(reply or "")))
    return "".join(parts)


def quiz_html(course: dict, *, review: bool, error: str) -> str:
    quiz = course["quiz"]
    attempts = course.get("attempts") or []
    parts = [f"<h2>{esc(quiz['title'])}</h2>"]
    if attempts:
        last = attempts[-1]
        parts.append(
            f'<p class="score">{last["score"]} of {last["total"]} on the latest sitting.</p>'
        )
    if error:
        parts.append(f'<p class="hint" role="alert">{esc(error)}</p>')

    if review and attempts:
        picks = attempts[-1]["picks"]
        for index, question in enumerate(quiz["questions"]):
            chosen = picks[index] if index < len(picks) else None
            choices = []
            for choice_index, choice in enumerate(question["choices"]):
                classes = ["choice"]
                if choice_index == question["answer"]:
                    classes.append("is-right")
                elif choice_index == chosen:
                    classes.append("is-miss")
                mark = ""
                if choice_index == question["answer"]:
                    mark = '<span class="mark-word">Answer</span>'
                elif choice_index == chosen:
                    mark = '<span class="mark-word">Yours</span>'
                choices.append(
                    f'<p class="{" ".join(classes)}"><span>{esc(choice)}</span>{mark}</p>'
                )
            parts.append(
                "<fieldset class=\"question\">"
                f"<legend>{index + 1}. {esc(question['prompt'])}</legend>"
                + "".join(choices)
                + "</fieldset>"
            )
        parts.append(
            f'<a class="btn btn-ghost" href="/courses/{esc(course["id"])}?retry=1">Attend again</a>'
        )
        return "".join(parts)

    fields = []
    for index, question in enumerate(quiz["questions"]):
        choices = []
        for choice_index, choice in enumerate(question["choices"]):
            choices.append(
                "<label class=\"choice\">"
                f'<input type="radio" name="q{index}" value="{choice_index}" required>'
                f"<span>{esc(choice)}</span>"
                "</label>"
            )
        fields.append(
            "<fieldset class=\"question\">"
            f"<legend>{index + 1}. {esc(question['prompt'])}</legend>"
            + "".join(choices)
            + "</fieldset>"
        )
    parts.append(
        f'<form method="post" action="/courses/{esc(course["id"])}/quiz">'
        + "".join(fields)
        + '<button class="btn btn-solid" type="submit">Submit quiz</button>'
        "</form>"
    )
    return "".join(parts)


def page_shell(title: str, email: str, here: str, body: str, course_id: str = "") -> str:
    template = (ROOT / "templates" / "app.html").read_text(encoding="utf-8")
    return (
        template.replace("<!--TITLE-->", esc(title))
        .replace("<!--NAV-->", sidebar_nav(here, email, course_id))
        .replace("<!--ACCOUNT-->", sidebar_user(email))
        .replace("<!--BODY-->", body)
    )


def continue_html(courses: list[dict]) -> str:
    if not courses:
        return (
            '<section class="continue continue-empty">'
            "<p>No course yet. Create one and Lumina will draft the lesson plan.</p>"
            '<a class="btn btn-solid" href="/courses">Create a course</a>'
            "</section>"
        )
    chosen = courses[0]
    for course in courses:
        done, total, _percent = course_progress(course)
        if total and done < total:
            chosen = course
            break
    done, total, percent = course_progress(chosen)
    label = f"{done} of {total} lessons" if total else "Open the lesson plan"
    return (
        f'<a class="continue" href="/courses/{esc(chosen["id"])}">'
        '<span class="continue-kicker">Continue learning</span>'
        f"<strong>{esc(chosen['title'])}</strong>"
        f"<span>{esc(label)} · {percent}%</span>"
        f'<span class="card-bar" aria-hidden="true"><span style="width:{percent}%"></span></span>'
        "</a>"
    )


def render_dashboard(email: str, user: dict) -> str:
    courses = user.get("courses") or []
    finished = sum(course_progress(course)[0] for course in courses)
    sittings = sum(len(course.get("attempts") or []) for course in courses)
    sittings += sum(len(lesson.get("attempts") or []) for course in courses for lesson in course.get("lessons") or [])
    body = f"""
      <header class="topbar">
        <div>
          <p class="crumb">Workspace</p>
          <h1>Overview</h1>
        </div>
      </header>
      <div class="content">
        {continue_html(courses)}
        <section class="stats" aria-label="Summary">
          <article class="stat"><span>Courses</span><strong>{len(courses)}</strong></article>
          <article class="stat"><span>Lessons done</span><strong>{finished}</strong></article>
          <article class="stat"><span>Quizzes</span><strong>{sittings}</strong></article>
        </section>
        {heatmap_html(email, user)}
      </div>
    """
    return page_shell("Overview — Lumina", email, "dashboard", body)


def render_courses(email: str, user: dict, error: str = "", title: str = "", goal: str = "") -> str:
    courses = user.get("courses") or []
    message = f'<p class="hint" role="alert">{esc(error)}</p>' if error else ""
    body = f"""
      <header class="topbar">
        <div>
          <p class="crumb">Workspace</p>
          <h1>Courses</h1>
        </div>
      </header>
      <div class="content">
        <section class="panel" id="create">
          <div class="panel-head">
            <h2>New course</h2>
            <p class="sub">Gemini drafts a lesson plan from the name and focus.</p>
          </div>
          <form class="composer" id="create-course" method="post" action="/courses">
            {message}
            <div class="composer-row">
              <label class="sr" for="course-title">Course name</label>
              <input id="course-title" name="title" maxlength="80" required placeholder="Course name" value="{esc(title)}">
              <label class="sr" for="course-goal">Focus</label>
              <input id="course-goal" name="goal" maxlength="180" placeholder="What do you want to get better at?" value="{esc(goal)}">
              <button class="btn btn-solid" type="submit">Create</button>
            </div>
          </form>
          <div class="loader" id="create-loader" hidden>
            <div class="loader-card" role="status">
              <span class="spinner" aria-hidden="true"></span>
              <p>Drafting your lesson plan</p>
            </div>
          </div>
          <script>
            document.querySelector("#create-course").addEventListener("submit", () => {{
              const loader = document.querySelector("#create-loader");
              const button = document.querySelector("#create-course button");
              loader.hidden = false;
              button.disabled = true;
            }});
          </script>
        </section>
        <section class="panel">
          <div class="panel-head"><h2>Your courses</h2></div>
          {course_list_html(courses)}
        </section>
      </div>
    """
    return page_shell("Courses — Lumina", email, "courses", body)


def lesson_state(lesson: dict) -> tuple[str, str]:
    attempts = lesson.get("attempts") or []
    if attempts:
        latest = attempts[-1]
        return "done", f"{latest['score']}/{latest['total']}"
    if lesson.get("studied"):
        return "study", "Studying"
    return "new", "Not started"


def progress_html(course: dict) -> str:
    done, total, percent = course_progress(course)
    goal = course.get("goal") or "Work through the lessons in order."
    overview = course.get("overview") or "Study a lesson, then take its quiz."
    label = f"{done} of {total} lessons finished" if total else "No lessons yet"
    return (
        '<section class="panel">'
        '<div class="panel-body">'
        '<div class="progress-top">'
        "<div>"
        "<h2>Progress</h2>"
        f"<p>{esc(goal)}</p>"
        f'<p class="sub">{esc(overview)}</p>'
        "</div>"
        f"<strong>{percent}%</strong>"
        "</div>"
        f'<div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent}" aria-label="Course progress">'
        f'<span style="width:{percent}%"></span></div>'
        f'<p class="sub progress-count">{esc(label)}</p>'
        "</div></section>"
    )


def lesson_list_html(course: dict) -> str:
    rows = []
    for index, lesson in enumerate(course.get("lessons") or []):
        kind, label = lesson_state(lesson)
        rows.append(
            f'<button type="button" class="lesson-row" data-open="{index}">'
            f'<span class="lesson-num">{index + 1:02d}</span>'
            '<span class="lesson-copy">'
            f"<h3>{esc(lesson['title'])}</h3>"
            f'<p>{lesson["minutes"]} min</p>'
            "</span>"
            f'<span class="status status-{kind}">{esc(label)}</span>'
            "</button>"
        )
    return f'<div class="lesson-list">{"".join(rows)}</div>'


def lesson_pane_html(course: dict, index: int, lesson: dict) -> str:
    sections = "".join(
        '<div class="study-block">'
        f"<h3>{esc(section['label'])}</h3>"
        f"<p>{format_inline(section['text'])}</p>"
        "</div>"
        for section in lesson.get("sections") or []
    )
    quiz_label = "Retake assessment" if lesson.get("attempts") else "Take assessment"
    return (
        f'<div class="drawer-pane" data-pane="{index}" hidden>'
        '<header class="drawer-head">'
        "<div>"
        f'<p class="drawer-kicker">Lesson {index + 1:02d} · {lesson["minutes"]} min</p>'
        f"<h2>{esc(lesson['title'])}</h2>"
        "</div>"
        '<button type="button" class="drawer-close" data-close aria-label="Close lesson">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">'
        '<path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
        "</svg></button>"
        "</header>"
        f'<div class="drawer-body">{sections}</div>'
        '<footer class="drawer-foot">'
        f'<a class="btn btn-solid start-quiz" href="{assess_url(course, index)}">{quiz_label}</a>'
        "</footer>"
        "</div>"
    )


def lesson_drawer_html(course: dict) -> str:
    panes = "".join(
        lesson_pane_html(course, index, lesson)
        for index, lesson in enumerate(course.get("lessons") or [])
    )
    return (
        '<div class="drawer-backdrop" id="drawer-backdrop" data-close hidden></div>'
        '<aside class="lesson-drawer" id="lesson-drawer" role="dialog" aria-modal="true" aria-label="Lesson" aria-hidden="true" inert>'
        f"{panes}"
        "</aside>"
    )


def plan_side_html(course: dict) -> str:
    done, total, percent = course_progress(course)
    label = f"{done} of {total} lessons" if total else "No lessons yet"
    return (
        '<aside class="plan-side" id="plan-side">'
        '<div class="plan-side-head"><h2>Lesson plan</h2><p class="sub">Open a lesson, then take its assessment.</p></div>'
        '<div class="plan-progress">'
        '<div class="plan-progress-top"><span>Progress</span>'
        f"<strong>{percent}%</strong></div>"
        f'<div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{percent}" aria-label="Course progress">'
        f'<span style="width:{percent}%"></span></div>'
        f'<p class="sub">{esc(label)}</p>'
        f"{certificate_side_html(course)}"
        "</div>"
        f"{lesson_list_html(course)}"
        "</aside>"
    )


ASSESS_WARNING_LIMIT = 3
ASSESS_PASS_PERCENT = 70
ASSESS_QUESTION_COUNT = 30
ASSESS_FLAGS = {
    "tab": "Switched tab or window",
    "fullscreen": "Left full screen",
    "camera-off": "Camera turned off",
    "camera-covered": "Camera covered or dark",
    "no-face": "No face in view",
    "faces": "More than one face",
}


def best_percent(lesson: dict) -> int | None:
    scores = [
        round(100 * (attempt.get("score") or 0) / attempt["total"])
        for attempt in lesson.get("attempts") or []
        if attempt.get("total")
    ]
    return max(scores) if scores else None


def certificate_status(course: dict) -> dict:
    lessons = course.get("lessons") or []
    bests = [best_percent(lesson) for lesson in lessons]
    passed = sum(1 for best in bests if best is not None and best >= ASSESS_PASS_PERCENT)
    eligible = bool(lessons) and passed == len(lessons)
    average = round(sum(best or 0 for best in bests) / len(bests)) if bests else 0
    return {"eligible": eligible, "passed": passed, "total": len(lessons), "average": average, "bests": bests}


def certificate_url(course: dict) -> str:
    return f"/courses/{esc(course['id'])}/certificate"


def certificate_side_html(course: dict) -> str:
    status = certificate_status(course)
    issued = course.get("certificate")
    if issued:
        return (
            f'<a class="cert-side is-earned" href="{certificate_url(course)}">'
            "<strong>Certificate earned</strong>"
            f"<span>Issued {esc(issued.get('issued') or '')} · View or print</span></a>"
        )
    if status["eligible"]:
        return (
            f'<a class="cert-side is-ready" href="{certificate_url(course)}">'
            "<strong>Course complete</strong>"
            "<span>Claim your certificate</span></a>"
        )
    if not status["total"]:
        return ""
    return (
        f'<a class="cert-side" href="{certificate_url(course)}">'
        "<strong>Certificate</strong>"
        f"<span>{status['passed']} of {status['total']} assessments passed at {ASSESS_PASS_PERCENT}%</span></a>"
    )


def bank_ready(lesson: dict) -> bool:
    bank = lesson.get("assessment") or []
    return len(bank) >= ASSESS_QUESTION_COUNT and all(question.get("type") in TYPES for question in bank)


def assessment_questions(lesson: dict) -> list[dict]:
    return lesson.get("assessment") or lesson.get("quiz") or []


def attempt_questions(lesson: dict, attempt: dict) -> list[dict]:
    if attempt.get("questions"):
        return attempt["questions"]
    size = len(attempt.get("picks") or [])
    bank = lesson.get("assessment") or []
    candidates = [lesson.get("quiz") or []]
    if not any(question.get("type") for question in bank):
        candidates.insert(0, bank)
    for questions in candidates:
        if questions and len(questions) == size:
            return questions
    return []


def prompt_html(question: dict) -> str:
    text = esc(question.get("prompt") or "")
    if kind_of(question) == "fill":
        text = text.replace(BLANK, '<span class="as-blank" aria-label="blank"></span>', 1)
    return re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)


def question_body(number: int, question: dict) -> str:
    kind = kind_of(question)
    name = f"q{number}"
    if kind in ("single", "truefalse", "multi"):
        input_type = "checkbox" if kind == "multi" else "radio"
        options = "".join(
            '<label class="as-option">'
            f'<input type="{input_type}" name="{name}" value="{choice_index}">'
            f'<span class="as-letter" aria-hidden="true">{chr(65 + choice_index)}</span>'
            f"<span>{esc(choice)}</span>"
            "</label>"
            for choice_index, choice in enumerate(question.get("choices") or [])
        )
        hint = '<p class="as-hint">Select every correct answer.</p>' if kind == "multi" else ""
        return f'{hint}<div class="as-options{" as-options-row" if kind == "truefalse" else ""}">{options}</div>'
    if kind == "fill":
        return (
            f'<label class="as-fill"><span>Your answer</span>'
            f'<input type="text" name="{name}" maxlength="200" autocomplete="off" spellcheck="false" '
            'placeholder="Type the missing word or phrase"></label>'
        )
    if kind == "match":
        options = '<option value="">Choose a match…</option>' + "".join(
            f'<option value="{right_index}">{esc(right)}</option>' for right_index, right in enumerate(question["right"])
        )
        rows = "".join(
            '<div class="as-match-row">'
            f'<label for="{name}_{row}">{esc(left)}</label>'
            f'<select id="{name}_{row}" name="{name}_{row}">{options}</select>'
            "</div>"
            for row, left in enumerate(question["left"])
        )
        return f'<p class="as-hint">Pick the description that matches each term.</p><div class="as-match">{rows}</div>'
    language = question.get("language", "python")
    tables = ""
    if language == "sql":
        blocks = []
        for table in sql_tables(question.get("setup", "")):
            head = "".join(f"<th>{esc(column)}</th>" for column in table["columns"])
            body = "".join(
                "<tr>" + "".join(f"<td>{esc('NULL' if value is None else value)}</td>" for value in row) + "</tr>"
                for row in table["rows"]
            )
            blocks.append(
                f'<div class="as-table"><p>{esc(table["name"])}</p>'
                f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
            )
        tables = f'<details class="as-tables" open><summary>Tables</summary>{"".join(blocks)}</details>'
    samples = sample_tests(question)
    hidden = hidden_count(question)
    examples = ""
    if samples:
        rows = "".join(
            f"<li><code>{esc(test['call'])}</code><span>→</span><code>{esc(test['expected'])}</code></li>"
            for test in samples
        )
        more = f'<p class="as-hint">Plus {hidden} hidden test{"s" if hidden != 1 else ""} checked when you submit.</p>' if hidden else ""
        examples = f'<div class="as-examples"><p class="as-examples-title">Examples</p><ul>{rows}</ul>{more}</div>'
    if language == "sql":
        expected = "Your query's rows are compared with the expected result"
        if question.get("check"):
            expected += ", then checked again on hidden extra rows"
        expected += "."
    elif samples:
        expected = "Your function's return values are checked against the examples and the hidden tests."
    else:
        expected = "Your program's printed output is compared with the expected output."
    return (
        f"{tables}{examples}"
        f'<div class="as-code" data-language="{esc(language)}">'
        f'<div class="as-code-head"><span>{esc(LANGUAGES.get(language, "Code"))}</span>'
        '<div class="as-code-tools">'
        f'<button type="button" class="as-reset" data-reset="{number}">Reset</button>'
        f'<button type="button" class="btn btn-ghost as-run" data-run="{number}">Run code</button>'
        "</div></div>"
        '<div class="as-editor">'
        '<pre class="as-gutter" aria-hidden="true">1</pre>'
        '<div class="as-editor-main">'
        '<pre class="as-highlight" aria-hidden="true"><code></code></pre>'
        f'<textarea name="{name}" class="as-code-input" spellcheck="false" autocapitalize="off" autocomplete="off" '
        f'wrap="off" rows="12" data-starter="{esc(question.get("starter", ""))}" aria-label="Code editor">'
        f'{esc(question.get("starter", ""))}</textarea>'
        "</div></div>"
        f'<div class="as-console" data-console="{number}" aria-live="polite"><p class="as-console-note">{expected} '
        "Run your code to check it before submitting. Press Ctrl+Enter or ⌘+Enter to run.</p></div>"
        "</div>"
    )


def assess_page(title: str, body: str) -> str:
    template = (ROOT / "templates" / "assess.html").read_text(encoding="utf-8")
    return template.replace("<!--TITLE-->", esc(title)).replace("<!--BODY-->", body)


def assess_bar(course: dict, index: int, lesson: dict, extra: str = "") -> str:
    return (
        '<header class="as-bar">'
        '<div class="as-brand">'
        '<span class="mark" aria-hidden="true">'
        '<svg viewBox="0 0 32 32" width="16" height="16"><path d="M10 8.5v15h12" fill="none" stroke="currentColor" '
        'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
        "<div>"
        f'<p class="as-course">{esc(course["title"])}</p>'
        f'<p class="as-lesson">Lesson {index + 1:02d} · {esc(lesson["title"])}</p>'
        "</div></div>"
        f"{extra}"
        "</header>"
    )


def render_assessment(course: dict, index: int, error: str = "") -> str:
    lesson = course["lessons"][index]
    questions = assessment_questions(lesson)
    count = len(questions)
    seconds = seconds_for(questions)
    minutes = (seconds + 59) // 60
    attempts = len(lesson.get("attempts") or [])
    message = f'<p class="as-alert" role="alert">{esc(error)}</p>' if error else ""
    preparing = not bank_ready(lesson)
    prepare_attr = f' data-prepare="{assess_url(course, index)}/prepare"' if preparing else ""
    count_text = "Preparing…" if preparing else str(count)
    time_text = "Preparing…" if preparing else f"{minutes} min"
    prepare_note = (
        '<div class="as-prep" id="prep" role="status">'
        '<span class="spinner" aria-hidden="true"></span>'
        f'<p id="prep-text">Preparing {ASSESS_QUESTION_COUNT} questions for this lesson. This can take a minute or two…</p>'
        '<button type="button" class="btn btn-ghost" id="prep-retry" hidden>Try again</button>'
        "</div>"
        if preparing
        else ""
    )

    fieldsets = []
    for number, question in enumerate(questions):
        kind = kind_of(question)
        fieldsets.append(
            f'<fieldset class="as-question" data-question="{number}" data-type="{kind}"{"" if number == 0 else " hidden"}>'
            f'<p class="as-count">Question {number + 1} of {count}<span class="as-type">{esc(label(question))}</span></p>'
            f"<legend>{prompt_html(question)}</legend>"
            f"{question_body(number, question)}"
            "</fieldset>"
        )
    kinds = []
    for question in questions:
        name = LABELS[kind_of(question)] if kind_of(question) != "code" else label(question)
        if name not in kinds:
            kinds.append(name)
    type_list = (
        "" if preparing else '<ul class="as-kinds">' + "".join(f"<li>{esc(name)}</li>" for name in kinds) + "</ul>"
    )
    nav = "".join(
        f'<button type="button" class="as-dot" data-goto="{number}" aria-label="Question {number + 1}">{number + 1}</button>'
        for number in range(count)
    )
    extra = (
        '<div class="as-status" data-exam-only hidden>'
        '<span class="as-cam-pill" id="cam-pill"><i aria-hidden="true"></i>Camera</span>'
        '<span class="as-warn-count" id="warn-count" title="Warnings">'
        f'Warnings <strong>0</strong>/{ASSESS_WARNING_LIMIT}</span>'
        '<span class="as-timer" id="timer" role="timer" aria-live="off">--:--</span>'
        "</div>"
    )
    previous = f"{attempts} previous attempt{'s' if attempts != 1 else ''}" if attempts else "First attempt"
    body = f"""
      {assess_bar(course, index, lesson, extra)}
      <main class="as-main" id="assessment"{prepare_attr} data-run="{assess_url(course, index)}/run"
        data-seconds="{seconds}" data-limit="{ASSESS_WARNING_LIMIT}" data-count="{count}">
        <section class="as-intro" id="intro">
          <p class="as-kicker">Assessment</p>
          <h1>{esc(lesson["title"])}</h1>
          {message}
          {prepare_note}
          <dl class="as-facts">
            <div><dt>Questions</dt><dd id="fact-count">{count_text}</dd></div>
            <div><dt>Time limit</dt><dd id="fact-time">{time_text}</dd></div>
            <div><dt>Pass mark</dt><dd>{ASSESS_PASS_PERCENT}%</dd></div>
            <div><dt>Attempts</dt><dd>{previous}</dd></div>
          </dl>
          {type_list}
          <h2>Before you start</h2>
          <ul class="as-rules">
            <li>The assessment opens in full screen, and your camera stays on throughout.</li>
            <li>Switching tabs, switching windows, or leaving full screen counts as a warning.</li>
            <li>Turning the camera off, covering it, leaving the frame, or another person in view counts as a warning.</li>
            <li>After {ASSESS_WARNING_LIMIT} warnings, or when time runs out, your answers are submitted automatically.</li>
            <li>Answers are shown only after you submit.</li>
          </ul>
          <section class="as-camera" id="cam-check" aria-labelledby="cam-title">
            <div class="as-cam-frame">
              <video id="cam-preview" muted playsinline autoplay></video>
              <span class="as-cam-empty" id="cam-empty">Camera off</span>
            </div>
            <div class="as-cam-copy">
              <h2 id="cam-title">Camera check</h2>
              <p id="cam-status">Turn on your camera to continue. Video stays in this browser; it is not recorded or uploaded.</p>
              <button type="button" class="btn btn-ghost" id="cam-enable">Turn on camera</button>
            </div>
          </section>
          <div class="as-actions">
            <a class="btn btn-ghost" href="/courses/{esc(course["id"])}">Back to course</a>
            <button type="button" class="btn btn-solid" id="start" disabled>Start assessment</button>
          </div>
        </section>
        <p class="as-note as-fs-note" id="fs-note" hidden>Full screen isn't available in this browser. Tab and window switches are still recorded.</p>

        <form class="as-exam" id="exam" method="post" action="/courses/{esc(course["id"])}/lessons/{index}/quiz" hidden>
          <input type="hidden" name="violations" id="violations" value="0">
          <input type="hidden" name="flags" id="flags" value="">
          <input type="hidden" name="ended" id="ended" value="submitted">
          <div class="as-paper">
            <div class="as-progress" aria-hidden="true"><span id="progress-bar"></span></div>
            {"".join(fieldsets)}
            <div class="as-step">
              <button type="button" class="btn btn-ghost" id="prev">Previous</button>
              <button type="button" class="btn btn-solid" id="next">Next</button>
            </div>
          </div>
          <aside class="as-side">
            <p class="as-side-title">Questions</p>
            <div class="as-dots">{nav}</div>
            <p class="as-answered" id="answered">0 of {count} answered</p>
            <button type="button" class="btn btn-solid as-submit" id="submit-exam">Submit assessment</button>
          </aside>
        </form>
      </main>

      <figure class="as-cam-live" data-exam-only hidden>
        <video id="cam-live" muted playsinline autoplay></video>
        <figcaption id="cam-caption">Camera on</figcaption>
      </figure>

      <div class="as-modal" id="warn-modal" role="alertdialog" aria-modal="true" aria-labelledby="warn-title" hidden>
        <div class="as-modal-card">
          <h2 id="warn-title">You left the assessment</h2>
          <p id="warn-text">Switching tabs or leaving full screen is recorded.</p>
          <button type="button" class="btn btn-solid" id="resume">Return to assessment</button>
        </div>
      </div>

      <div class="as-modal" id="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title" hidden>
        <div class="as-modal-card">
          <h2 id="confirm-title">Submit assessment?</h2>
          <p id="confirm-text">You can't change your answers after submitting.</p>
          <div class="as-actions">
            <button type="button" class="btn btn-ghost" id="cancel-submit">Keep working</button>
            <button type="button" class="btn btn-solid" id="confirm-submit">Submit</button>
          </div>
        </div>
      </div>

      <div class="as-modal" id="sending" role="status" hidden>
        <div class="as-modal-card as-sending">
          <span class="spinner" aria-hidden="true"></span>
          <p id="sending-text">Submitting your answers…</p>
        </div>
      </div>
      <script src="/static/js/highlight.js"></script>
      <script src="/static/js/assess.js"></script>
    """
    return assess_page(f"Assessment · {lesson['title']} — Lumina", body)


def review_detail(question: dict, pick) -> tuple[bool, str]:
    kind = kind_of(question)
    missing = "<em>Not answered</em>"

    def line(name: str, value: str) -> str:
        return f"<p><span>{name}</span>{value}</p>"

    if kind in ("single", "truefalse"):
        choices = question.get("choices") or []
        answer = question.get("answer")
        correct = isinstance(pick, int) and pick == answer
        yours = esc(choices[pick]) if isinstance(pick, int) and 0 <= pick < len(choices) else missing
        right = esc(choices[answer]) if isinstance(answer, int) and 0 <= answer < len(choices) else ""
        return correct, line("Your answer", yours) + ("" if correct else line("Correct answer", right))
    if kind == "multi":
        choices = question["choices"]
        chosen = [value for value in pick if isinstance(value, int) and 0 <= value < len(choices)] if isinstance(pick, list) else []
        correct = sorted(chosen) == question["answers"]
        yours = "; ".join(esc(choices[value]) for value in chosen) or missing
        right = "; ".join(esc(choices[value]) for value in question["answers"])
        return correct, line("Your answers", yours) + ("" if correct else line("Correct answers", right))
    if kind == "fill":
        text = pick if isinstance(pick, str) else ""
        correct = fill_matches(question, text)
        right = " or ".join(esc(answer) for answer in question["accept"])
        return correct, line("Your answer", esc(text) if text else missing) + (
            "" if correct else line("Accepted", right)
        )
    if kind == "match":
        values = pick if isinstance(pick, list) else []
        items = []
        correct = values == question["answer"]
        for row, left in enumerate(question["left"]):
            chosen = values[row] if row < len(values) else -1
            expected = question["answer"][row]
            ok = chosen == expected
            yours = esc(question["right"][chosen]) if 0 <= chosen < len(question["right"]) else missing
            fix = "" if ok else f'<small>Correct: {esc(question["right"][expected])}</small>'
            items.append(
                f'<li class="{"is-right" if ok else "is-miss"}"><b>{esc(left)}</b><span>{yours}{fix}</span></li>'
            )
        return correct, f'<ul class="as-match-review">{"".join(items)}</ul>'
    result = pick if isinstance(pick, dict) else {}
    correct = bool(result.get("passed"))
    code_language = esc(question.get("language") or "")
    language = LANGUAGES.get(question.get("language"), "Code")
    tests = question.get("tests") or []
    if not result.get("ran"):
        body = line("Your code", missing)
    else:
        output = result.get("output") or ""
        error = result.get("error") or ""
        body = (
            f'<p class="as-code-label">Your {language}</p>'
            f'<pre class="as-pre" data-language="{code_language}">{esc(result.get("code") or "")}</pre>'
        )
        if output:
            body += f'<p class="as-code-label">Output</p><pre class="as-pre">{esc(output)}</pre>'
        if error:
            body += f'<p class="as-code-label">Error</p><pre class="as-pre as-pre-error">{esc(error)}</pre>'
    if tests:
        checks = result.get("tests") or []
        rows = []
        for position, test in enumerate(tests):
            check = checks[position] if position < len(checks) else {}
            ok = bool(check.get("pass"))
            got = check.get("got") or "—"
            kind = "Example" if position < len(sample_tests(question)) else "Hidden"
            rows.append(
                f'<tr class="{"is-right" if ok else "is-miss"}"><td>{kind}</td>'
                f"<td><code>{esc(test['call'])}</code></td><td><code>{esc(test['expected'])}</code></td>"
                f'<td><code>{esc(got)}</code></td><td class="as-test-mark">{"Passed" if ok else "Failed"}</td></tr>'
            )
        passed_count = sum(1 for check in checks if check.get("pass"))
        body += (
            f'<p class="as-code-label">Tests · {passed_count} of {len(tests)} passed</p>'
            '<div class="as-tests"><table><thead><tr><th>Test</th><th>Call</th><th>Expected</th><th>Returned</th>'
            f'<th><span class="sr">Result</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        )
    elif not correct and result.get("hidden") is not False:
        if question.get("language") == "sql":
            expected = run_sql(question.get("setup", ""), question["solution"])
            shown = format_table(expected["columns"], expected["rows"]) if expected["ok"] else ""
        else:
            shown = question.get("expected", "")
        if shown:
            body += f'<p class="as-code-label">Expected output</p><pre class="as-pre">{esc(shown)}</pre>'
    if result.get("hidden") is False:
        body += (
            '<p class="as-hidden-note">Your query gave the right rows on the tables shown, but different rows once '
            "more data was added. Check that it doesn't depend on specific values in the sample rows.</p>"
        )
    body += (
        '<details class="as-solution"><summary>Show a model solution</summary>'
        f'<pre class="as-pre" data-language="{code_language}">{esc(question.get("solution") or "")}</pre></details>'
    )
    return correct, body


def answer_text(question: dict, pick) -> tuple[str, str]:
    """The learner's answer and the correct answer, as plain text for the feedback prompt."""
    kind = kind_of(question)
    blank = "(left blank)"
    if kind in ("single", "truefalse"):
        choices = question.get("choices") or []
        answer = question.get("answer")
        yours = choices[pick] if isinstance(pick, int) and 0 <= pick < len(choices) else blank
        options = "; ".join(choices)
        return yours, f"{choices[answer] if isinstance(answer, int) and answer < len(choices) else ''} (options: {options})"
    if kind == "multi":
        choices = question["choices"]
        chosen = [choices[value] for value in pick if isinstance(value, int) and 0 <= value < len(choices)] if isinstance(pick, list) else []
        return "; ".join(chosen) or blank, "; ".join(choices[value] for value in question["answers"])
    if kind == "fill":
        return (pick if isinstance(pick, str) and pick else blank), " or ".join(question["accept"])
    if kind == "match":
        values = pick if isinstance(pick, list) else []
        yours = []
        right = []
        for row, left in enumerate(question["left"]):
            chosen = values[row] if row < len(values) else -1
            yours.append(f"{left} -> {question['right'][chosen] if 0 <= chosen < len(question['right']) else '(none)'}")
            right.append(f"{left} -> {question['right'][question['answer'][row]]}")
        return "\n".join(yours), "\n".join(right)
    result = pick if isinstance(pick, dict) else {}
    if not result.get("ran"):
        yours = blank
    else:
        yours = (result.get("code") or "")[:3000]
        if result.get("output"):
            yours += f"\nPrinted output:\n{result['output'][:800]}"
        if result.get("error"):
            yours += f"\nError:\n{result['error'][:800]}"
    lines = []
    checks = result.get("tests") or []
    for position, test in enumerate(question.get("tests") or []):
        check = checks[position] if position < len(checks) else {}
        if not check.get("pass"):
            lines.append(f"{test['call']} should return {test['expected']}, got {check.get('got') or 'nothing'}")
    if result.get("hidden") is False:
        lines.append("The query gave different rows from the solution once more rows were added to the tables.")
    correct = f"Model solution:\n{question.get('solution') or ''}"
    if lines:
        correct = "Failed tests:\n" + "\n".join(lines) + "\n" + correct
    return yours, correct


def render_assessment_result(course: dict, index: int) -> str:
    lesson = course["lessons"][index]
    attempt = (lesson.get("attempts") or [None])[-1]
    if attempt is None:
        return render_assessment(course, index)
    questions = attempt_questions(lesson, attempt)
    picks = attempt.get("picks") or []
    score = attempt.get("score") or 0
    total = attempt.get("total") or len(questions) or 1
    percent = round(score * 100 / total)
    passed = percent >= ASSESS_PASS_PERCENT
    violations = attempt.get("violations") or 0
    tally: dict[str, int] = {}
    for flag in attempt.get("flags") or []:
        if flag in ASSESS_FLAGS:
            tally[flag] = tally.get(flag, 0) + 1
    flag_list = (
        '<ul class="as-flags">'
        + "".join(
            f"<li>{esc(ASSESS_FLAGS[flag])}<span>×{times}</span></li>" for flag, times in tally.items()
        )
        + "</ul>"
        if tally
        else ""
    )

    feedback = attempt.get("feedback") or {}
    notes = feedback.get("items") or {}
    rows = []
    misses = 0
    for number, question in enumerate(questions):
        pick = picks[number] if number < len(picks) else None
        correct, detail = review_detail(question, pick)
        if correct:
            mark = "Correct"
        elif answered(question, pick):
            mark = "Incorrect"
        else:
            mark = "Not answered"
        misses += 0 if correct else 1
        note = notes.get(str(number + 1))
        coach = (
            '<div class="as-feedback"><p class="as-feedback-title">Lumina’s feedback</p>'
            f"<p>{format_feedback(note)}</p></div>"
            if note
            else ""
        )
        rows.append(
            f'<li class="as-review {"is-right" if correct else "is-miss"}">'
            f'<div class="as-review-head"><strong>Question {number + 1}'
            f'<span class="as-type">{esc(label(question))}</span></strong><span class="as-tag">{mark}</span></div>'
            f'<p class="as-review-q">{prompt_html(question)}</p>'
            f"{detail}{coach}"
            "</li>"
        )
    coach_panel = ""
    if rows and misses:
        if feedback:
            summary = feedback.get("summary") or ""
            coach_panel = (
                '<div class="as-coach is-done"><div><p class="as-coach-title">Feedback from Lumina</p>'
                f"<p>{format_feedback(summary) if summary else 'Notes are added under each question you missed.'}</p>"
                "</div></div>"
            )
        else:
            coach_panel = (
                f'<div class="as-coach" id="coach" data-feedback="{assess_url(course, index)}/feedback">'
                '<div><p class="as-coach-title">Understand your mistakes</p>'
                f'<p id="coach-text">Lumina can explain the {misses} question{"s" if misses != 1 else ""} you missed '
                "and point to what to review.</p></div>"
                '<button type="button" class="btn btn-solid" id="coach-button">Explain my mistakes</button>'
                "</div>"
            )
    review_html = (
        f'<section class="as-reviews"><h2>Review</h2>{coach_panel}<ol>{"".join(rows)}</ol></section>'
        if rows
        else '<section class="as-reviews"><h2>Review</h2><p class="as-note">This attempt used an earlier question set, so its answers can\'t be shown.</p></section>'
    )
    cert_note = ""
    if certificate_status(course)["eligible"]:
        cert_text = "View your certificate" if course.get("certificate") else "You passed every lesson. Claim your certificate"
        cert_note = f'<a class="as-cert-note" href="{certificate_url(course)}">{cert_text} →</a>'
    verdict = "Passed" if passed else "Needs review"
    warning_text = "No warnings" if not violations else f"{violations} warning{'s' if violations != 1 else ''}"
    body = f"""
      {assess_bar(course, index, lesson)}
      <main class="as-main as-result">
        <section class="as-score {"is-pass" if passed else "is-fail"}">
          <p class="as-kicker">Result</p>
          <div class="as-score-row">
            <strong>{score}/{total}</strong>
            <span class="as-verdict">{verdict}</span>
          </div>
          <div class="as-meter" aria-hidden="true"><span style="width:{percent}%"></span></div>
          <dl class="as-facts">
            <div><dt>Score</dt><dd>{percent}%</dd></div>
            <div><dt>Pass mark</dt><dd>{ASSESS_PASS_PERCENT}%</dd></div>
            <div><dt>Integrity</dt><dd>{warning_text}</dd></div>
            <div><dt>Submitted</dt><dd>{esc(attempt.get("at") or "")}</dd></div>
          </dl>
          {flag_list}
          {cert_note}
          <div class="as-actions">
            <a class="btn btn-ghost" href="{assess_url(course, index)}">Retake assessment</a>
            <a class="btn btn-solid" href="/courses/{esc(course["id"])}">Back to course</a>
          </div>
        </section>
        {review_html}
      </main>
      <script src="/static/js/highlight.js"></script>
      <script src="/static/js/result.js"></script>
    """
    return assess_page(f"Result · {lesson['title']} — Lumina", body)


def certificate_bar(course: dict, extra: str = "") -> str:
    return (
        '<header class="as-bar cert-bar">'
        '<div class="as-brand">'
        '<span class="mark" aria-hidden="true">'
        '<svg viewBox="0 0 32 32" width="16" height="16"><path d="M10 8.5v15h12" fill="none" stroke="currentColor" '
        'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
        "<div>"
        f'<p class="as-course">{esc(course["title"])}</p>'
        '<p class="as-lesson">Certificate</p>'
        "</div></div>"
        f'<div class="cert-actions"><a class="btn btn-ghost" href="/courses/{esc(course["id"])}">Back to course</a>{extra}</div>'
        "</header>"
    )


def render_certificate(course: dict, error: str = "", name: str = "") -> str:
    status = certificate_status(course)
    issued = course.get("certificate")
    if issued:
        lessons = len(course.get("lessons") or [])
        body = f"""
          {certificate_bar(course, '<button type="button" class="btn btn-solid" id="print-cert">Print or save as PDF</button>')}
          <main class="cert-page">
            <article class="cert" aria-label="Certificate of completion">
              <div class="cert-frame">
                <div class="cert-top">
                  <span class="cert-logo" aria-hidden="true">
                    <svg viewBox="0 0 32 32" width="22" height="22"><path d="M10 8.5v15h12" fill="none" stroke="currentColor"
                      stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </span>
                  <span class="cert-brand">Lumina</span>
                </div>
                <p class="cert-kicker">Certificate of completion</p>
                <p class="cert-lead">This certifies that</p>
                <h1 class="cert-name">{esc(issued.get("name") or "")}</h1>
                <p class="cert-lead">has completed the course</p>
                <h2 class="cert-course">{esc(course["title"])}</h2>
                <p class="cert-detail">Passed all {lessons} lesson assessments with an average best score of {esc(str(issued.get("score") or 0))}%.</p>
                <div class="cert-foot">
                  <div><strong>{esc(issued.get("issued") or "")}</strong><span>Date issued</span></div>
                  <div class="cert-seal" aria-hidden="true">
                    <svg viewBox="0 0 64 64" width="64" height="64"><circle cx="32" cy="32" r="29" fill="none" stroke="currentColor" stroke-width="2"/>
                    <circle cx="32" cy="32" r="23" fill="none" stroke="currentColor" stroke-width="1" stroke-dasharray="2 3"/>
                    <path d="M24 33l6 6 11-13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </div>
                  <div><strong>{esc(issued.get("id") or "")}</strong><span>Certificate ID</span></div>
                </div>
              </div>
            </article>
          </main>
          <script>
            document.querySelector("#print-cert").addEventListener("click", () => window.print());
          </script>
        """
        return assess_page(f"Certificate · {course['title']} — Lumina", body)

    rows = []
    for index, lesson in enumerate(course.get("lessons") or []):
        best = status["bests"][index]
        if best is None:
            state, text = "new", "Not taken"
        elif best >= ASSESS_PASS_PERCENT:
            state, text = "pass", f"Passed · {best}%"
        else:
            state, text = "low", f"Best {best}%"
        action = (
            ""
            if state == "pass"
            else f'<a href="{assess_url(course, index)}">{"Retake" if best is not None else "Take"} assessment</a>'
        )
        rows.append(
            f'<li class="cert-row is-{state}"><span class="cert-row-num">{index + 1:02d}</span>'
            f'<span class="cert-row-title">{esc(lesson["title"])}</span>'
            f'<span class="cert-row-state">{text}</span>{action}</li>'
        )
    if status["eligible"]:
        message = f'<p class="as-alert" role="alert">{esc(error)}</p>' if error else ""
        panel = f"""
          <p class="as-kicker">Course complete</p>
          <h1>Claim your certificate</h1>
          <p class="cert-intro">You passed every lesson assessment in {esc(course["title"])}. Enter the name to print on the certificate. It can't be changed after it's issued.</p>
          {message}
          <form class="cert-form" method="post" action="{certificate_url(course)}">
            <label for="cert-name">Name on certificate</label>
            <div class="cert-form-row">
              <input id="cert-name" name="name" required minlength="2" maxlength="60" autocomplete="name" value="{esc(name)}">
              <button type="submit" class="btn btn-solid">Issue certificate</button>
            </div>
          </form>
        """
    else:
        panel = f"""
          <p class="as-kicker">Certificate</p>
          <h1>Finish the course to earn a certificate</h1>
          <p class="cert-intro">Pass every lesson assessment with {ASSESS_PASS_PERCENT}% or more. Your best attempt counts. {status["passed"]} of {status["total"]} passed so far.</p>
          <div class="as-meter" aria-hidden="true"><span style="width:{round(100 * status["passed"] / status["total"]) if status["total"] else 0}%"></span></div>
        """
    body = f"""
      {certificate_bar(course)}
      <main class="as-main cert-status">
        <section class="as-intro">
          {panel}
          <ol class="cert-rows">{"".join(rows)}</ol>
        </section>
      </main>
    """
    return assess_page(f"Certificate · {course['title']} — Lumina", body)


def format_feedback(text: str) -> str:
    return re.sub(r"`([^`\n]+)`", r"<code>\1</code>", esc(text))


def render_course(
    email: str,
    course: dict,
    *,
    review: bool = False,
    error: str = "",
    prompt_error: str = "",
    open_lesson: int | None = None,
) -> str:
    del review, error
    prompt_message = f'<p class="hint" role="alert">{esc(prompt_error)}</p>' if prompt_error else ""
    opened = "" if open_lesson is None else str(open_lesson)
    body = f"""
      <section class="desk" data-course="{esc(course["id"])}" data-initial="{esc(opened)}">
        <section class="chat">
          <header class="chat-top">
            <a href="/courses">Courses</a>
            <span class="chat-sep" aria-hidden="true">/</span>
            <h1>{esc(course["title"])}</h1>
          </header>
          <div class="chat-log" id="chat-log">
            <div class="chat-col">
              {chat_html(course)}
            </div>
          </div>
          <form class="chat-dock" id="course-chat" method="post" action="/courses/{esc(course["id"])}/prompt">
            <div class="chat-col">
              {prompt_message}
              <div class="chat-box">
                <label class="sr" for="prompt">Message</label>
                <textarea id="prompt" name="prompt" rows="1" maxlength="2000" required placeholder="Message Lumina"></textarea>
                <button class="send" type="submit" aria-label="Send">
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                    <path d="M12 19V5M6 11l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
          </form>
        </section>
        {plan_side_html(course)}
        {lesson_drawer_html(course)}
      </section>
      <script src="/static/js/course.js"></script>
    """
    return page_shell(f"{course['title']} — Lumina", email, "course", body, course["id"])


def quiz_fields(lesson: dict, picks: list[int] | None = None) -> str:
    fields = []
    for index, question in enumerate(lesson["quiz"]):
        choices = []
        for choice_index, choice in enumerate(question["choices"]):
            checked = " checked" if picks is not None and picks[index] == choice_index else ""
            locked = " disabled" if picks is not None else ""
            mark = ""
            classes = "choice"
            if picks is not None:
                if choice_index == question["answer"]:
                    classes += " is-right"
                    mark = '<span class="mark-word">Answer</span>'
                elif picks[index] == choice_index:
                    classes += " is-miss"
                    mark = '<span class="mark-word">Yours</span>'
            choices.append(
                f'<label class="{classes}">'
                f'<input type="radio" name="q{index}" value="{choice_index}"{" required" if picks is None else ""}{checked}{locked}>'
                f"<span>{esc(choice)}</span>{mark}</label>"
            )
        fields.append(
            f'<fieldset class="question"><legend>{index + 1}. {esc(question["prompt"])}</legend>'
            f'{"".join(choices)}</fieldset>'
        )
    return "".join(fields)


def render_study(email: str, course: dict, index: int, *, error: str = "", retry: bool = False) -> str:
    lesson = course["lessons"][index]
    sections = "".join(
        '<div class="study-block">'
        f"<h3>{esc(section['label'])}</h3>"
        f"<p>{format_inline(section['text'])}</p>"
        "</div>"
        for section in lesson["sections"]
    )
    attempts = lesson.get("attempts") or []
    latest = attempts[-1] if attempts else None
    score = ""
    if latest:
        score = f'<p class="score">Latest score {latest["score"]}/{latest["total"]}</p>'
    message = f'<p class="hint" role="alert">{esc(error)}</p>' if error else ""
    show_form = retry or not latest or error
    if show_form:
        quiz = (
            f'<form method="post" action="/courses/{esc(course["id"])}/lessons/{index}/quiz">'
            f"{message}{quiz_fields(lesson)}"
            '<button class="btn btn-solid" type="submit">Submit quiz</button>'
            "</form>"
        )
    else:
        quiz = (
            f"{quiz_fields(lesson, latest['picks'])}"
            f'<p class="retake"><a href="/courses/{esc(course["id"])}/lessons/{index}?retry=1">Retake quiz</a></p>'
        )
    body = f"""
      <header class="topbar">
        <div>
          <p class="crumb"><a href="/courses/{esc(course["id"])}">{esc(course["title"])}</a></p>
          <h1>{esc(lesson["title"])}</h1>
        </div>
      </header>
      <div class="content">
        {progress_html(course)}
        <section class="panel">
          <div class="panel-head"><h2>Study</h2></div>
          <div class="panel-body">{sections}</div>
        </section>
        <section class="panel" id="quiz">
          <div class="panel-head"><h2>Quiz</h2></div>
          <div class="panel-body">{score}{quiz}</div>
        </section>
      </div>
    """
    return page_shell(f"{lesson['title']} — Lumina", email, "course", body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _learner(self) -> str | None:
        jar = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get("lumina")
        if morsel is None:
            return None
        return read_session(morsel.value)

    def _form(self) -> dict[str, str]:
        return {key: values[0].strip() for key, values in self._form_lists(12000).items()}

    def _form_lists(self, limit: int) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > limit:
            return {}
        raw = self.rfile.read(length) if length else b""
        return parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)

    def _send(self, status: int, body: bytes, content_type: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in extra or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json", [("Cache-Control", "no-store")])

    def _redirect(self, location: str, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for key, value in extra or []:
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, render_page(self._learner()).encode(), "text/html; charset=utf-8")
            return

        if path in ("/login", "/signup"):
            if self._learner():
                self._redirect("/dashboard")
                return
            email = parse_qs(urlparse(self.path).query).get("email", [""])[0][:180]
            page = render_auth(path.removeprefix("/"), fields={"email": email})
            self._send(200, page.encode(), "text/html; charset=utf-8", [("Cache-Control", "no-store")])
            return

        if path == "/dashboard":
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            self._send(200, render_dashboard(email, ensure_plans(email)).encode(), "text/html; charset=utf-8")
            return

        if path == "/courses":
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            self._send(200, render_courses(email, ensure_plans(email)).encode(), "text/html; charset=utf-8")
            return

        lesson_match = LESSON_RE.fullmatch(path)
        if lesson_match:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id = lesson_match.group(1)
            index = int(lesson_match.group(2))
            user = ensure_plans(email)
            course = find_course(user, course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send(404, b"That lesson is not on your desk.", "text/plain; charset=utf-8")
                return
            if not course["lessons"][index].get("studied"):

                def mark(found: dict) -> None:
                    current = find_course(found, course_id)
                    if current is None:
                        return
                    current["lessons"][index]["studied"] = today_key()

                update_user(email, mark)
            self._redirect(f"/courses/{course_id}?lesson={index}")
            return

        course_match = COURSE_RE.fullmatch(path)
        if course_match and course_match.group(2) is None:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course = find_course(ensure_plans(email), course_match.group(1))
            if course is None:
                self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                return
            params = parse_qs(urlparse(self.path).query)
            lesson_value = params.get("lesson", [""])[0]
            open_lesson = int(lesson_value) if lesson_value.isdigit() else None
            self._send(
                200,
                render_course(email, course, open_lesson=open_lesson).encode(),
                "text/html; charset=utf-8",
            )
            return

        assess_match = LESSON_ASSESS_RE.fullmatch(path)
        if assess_match:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id = assess_match.group(1)
            index = int(assess_match.group(2))
            course = find_course(ensure_plans(email), course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send(404, b"That lesson is not on your desk.", "text/plain; charset=utf-8")
                return
            if not assessment_questions(course["lessons"][index]):
                self._redirect(f"/courses/{course_id}?lesson={index}")
                return
            params = parse_qs(urlparse(self.path).query)
            if "result" in params:
                page = render_assessment_result(course, index)
            else:
                page = render_assessment(course, index)
            self._send(200, page.encode(), "text/html; charset=utf-8", [("Cache-Control", "no-store")])
            return

        cert_match = CERTIFICATE_RE.fullmatch(path)
        if cert_match:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course = find_course(ensure_plans(email), cert_match.group(1))
            if course is None:
                self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                return
            page = render_certificate(course, name=(read_account(email) or {}).get("name", ""))
            self._send(200, page.encode(), "text/html; charset=utf-8", [("Cache-Control", "no-store")])
            return

        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            file_path = (ROOT / "static" / relative).resolve()
            if not file_path.is_relative_to(ROOT / "static") or not file_path.is_file():
                self._send(404, b"Not found", "text/plain; charset=utf-8")
                return
            kinds = {
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".svg": "image/svg+xml",
            }
            kind = kinds.get(file_path.suffix, "application/octet-stream")
            self._send(200, file_path.read_bytes(), kind)
            return

        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/login":
            form = self._form()
            email = normal_email(form.get("email", ""))
            error, stored = authenticate(email, form.get("password", ""))
            if error:
                page = render_auth("login", error, {"email": email})
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return
            self._redirect("/dashboard", [("Set-Cookie", session_cookie(email, stored))])
            return

        if path == "/signup":
            form = self._form()
            name = " ".join(form.get("name", "").split())
            email = normal_email(form.get("email", ""))
            error, stored = register(name, email, form.get("password", ""), form.get("confirm", ""))
            if error:
                page = render_auth("signup", error, {"name": name, "email": email})
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return
            self._redirect("/dashboard", [("Set-Cookie", session_cookie(email, stored))])
            return

        if path == "/logout":
            self._redirect("/", [("Set-Cookie", session_cookie(None))])
            return

        if path == "/courses":
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            form = self._form()
            title = " ".join(form.get("title", "").split())
            goal = " ".join(form.get("goal", "").split())
            if len(title) < 2 or len(title) > 80:
                page = render_courses(email, read_user(email), "Give the course a name.", title, goal)
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return
            if len(goal) > 180:
                page = render_courses(email, read_user(email), "Keep the goal under 180 characters.", title, goal)
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return
            try:
                created = new_course(title, goal)
            except GeminiError as exc:
                page = render_courses(email, read_user(email), str(exc), title, goal)
                self._send(502, page.encode(), "text/html; charset=utf-8")
                return

            def add(user: dict) -> None:
                user.setdefault("courses", []).insert(0, created)

            update_user(email, add)
            self._redirect(f"/courses/{created['id']}")
            return

        lesson_open = LESSON_OPEN_RE.fullmatch(path)
        if lesson_open:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id = lesson_open.group(1)
            index = int(lesson_open.group(2))

            def mark_open(found: dict) -> None:
                current = find_course(found, course_id)
                if current is None or index >= len(current.get("lessons") or []):
                    return
                if not current["lessons"][index].get("studied"):
                    current["lessons"][index]["studied"] = today_key()

            update_user(email, mark_open)
            self._send(204, b"", "text/plain; charset=utf-8")
            return

        lesson_prepare = LESSON_PREPARE_RE.fullmatch(path)
        if lesson_prepare:
            email = self._learner()
            if not email:
                self._send_json(401, {"error": "Sign in again to continue."})
                return
            course_id = lesson_prepare.group(1)
            index = int(lesson_prepare.group(2))
            course = find_course(ensure_plans(email), course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send_json(404, {"error": "That lesson is not on your desk."})
                return
            lesson = course["lessons"][index]
            if bank_ready(lesson):
                self._send_json(200, {"ok": True, "count": len(lesson["assessment"])})
                return
            try:
                questions = draft_assessment(course, lesson, ASSESS_QUESTION_COUNT)
            except GeminiError as exc:
                self._send_json(502, {"error": str(exc)})
                return

            def store(found: dict) -> None:
                current = find_course(found, course_id)
                if current is None or index >= len(current.get("lessons") or []):
                    return
                if not bank_ready(current["lessons"][index]):
                    current["lessons"][index]["assessment"] = questions

            update_user(email, store)
            self._send_json(200, {"ok": True, "count": len(questions)})
            return

        cert_match = CERTIFICATE_RE.fullmatch(path)
        if cert_match:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id = cert_match.group(1)
            course = find_course(read_user(email), course_id)
            if course is None:
                self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                return
            if course.get("certificate") or not certificate_status(course)["eligible"]:
                self._redirect(f"/courses/{course_id}/certificate")
                return
            name = " ".join(self._form().get("name", "").split())
            if not 2 <= len(name) <= 60:
                page = render_certificate(course, "Enter a name between 2 and 60 characters.", name)
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return

            def issue(found: dict) -> None:
                current = find_course(found, course_id)
                if current is None or current.get("certificate"):
                    return
                status = certificate_status(current)
                if not status["eligible"]:
                    return
                code = secrets.token_hex(4).upper()
                current["certificate"] = {
                    "name": name,
                    "issued": today_key(),
                    "id": f"LUM-{code[:4]}-{code[4:]}",
                    "score": status["average"],
                }

            update_user(email, issue)
            self._redirect(f"/courses/{course_id}/certificate")
            return

        lesson_feedback = LESSON_FEEDBACK_RE.fullmatch(path)
        if lesson_feedback:
            email = self._learner()
            if not email:
                self._send_json(401, {"error": "Sign in again to continue."})
                return
            course_id = lesson_feedback.group(1)
            index = int(lesson_feedback.group(2))
            course = find_course(read_user(email), course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send_json(404, {"error": "That lesson is not on your desk."})
                return
            lesson = course["lessons"][index]
            attempts = lesson.get("attempts") or []
            if not attempts:
                self._send_json(400, {"error": "Take the assessment first."})
                return
            attempt_number = len(attempts) - 1
            attempt = attempts[-1]
            if attempt.get("feedback"):
                self._send_json(200, {"ok": True})
                return
            questions = attempt_questions(lesson, attempt)
            picks = attempt.get("picks") or []
            misses = []
            for number, question in enumerate(questions):
                pick = picks[number] if number < len(picks) else None
                correct, _detail = review_detail(question, pick)
                if correct:
                    continue
                yours, right = answer_text(question, pick)
                misses.append(
                    {
                        "number": number + 1,
                        "kind": label(question),
                        "prompt": question.get("prompt") or "",
                        "yours": yours,
                        "correct": right,
                    }
                )
            if not misses:
                self._send_json(400, {"error": "Every answer was correct, so there is nothing to explain."})
                return
            try:
                feedback = explain_attempt(course, lesson, misses, f"{attempt.get('score')}/{attempt.get('total')}")
            except GeminiError as exc:
                self._send_json(502, {"error": str(exc)})
                return

            def keep_feedback(found: dict) -> None:
                current = find_course(found, course_id)
                if current is None or index >= len(current.get("lessons") or []):
                    return
                stored = current["lessons"][index].get("attempts") or []
                if len(stored) - 1 == attempt_number:
                    stored[-1]["feedback"] = feedback

            update_user(email, keep_feedback)
            self._send_json(200, {"ok": True})
            return

        lesson_run = LESSON_RUN_RE.fullmatch(path)
        if lesson_run:
            email = self._learner()
            if not email:
                self._send_json(401, {"error": "Sign in again to continue."})
                return
            course_id = lesson_run.group(1)
            index = int(lesson_run.group(2))
            course = find_course(read_user(email), course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send_json(404, {"error": "That lesson is not on your desk."})
                return
            form = self._form_lists(80000)
            raw_number = (form.get("question") or [""])[0]
            questions = assessment_questions(course["lessons"][index])
            if not raw_number.isdigit() or int(raw_number) >= len(questions):
                self._send_json(400, {"error": "That question can't be run."})
                return
            question = questions[int(raw_number)]
            if kind_of(question) != "code":
                self._send_json(400, {"error": "That question can't be run."})
                return
            code = (form.get("code") or [""])[0][:20000].replace("\r\n", "\n")
            if not code.strip():
                self._send_json(200, {"ok": False, "error": "Write some code first."})
                return
            result = run_code(question, code)
            self._send_json(200, result)
            return

        lesson_quiz = LESSON_QUIZ_RE.fullmatch(path)
        if lesson_quiz:
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id = lesson_quiz.group(1)
            index = int(lesson_quiz.group(2))
            user = ensure_plans(email)
            course = find_course(user, course_id)
            if course is None or index >= len(course.get("lessons") or []):
                self._send(404, b"That lesson is not on your desk.", "text/plain; charset=utf-8")
                return
            lesson = course["lessons"][index]
            if not bank_ready(lesson):
                page = render_assessment(course, index, "This assessment's questions aren't ready yet. Start again.")
                self._send(409, page.encode(), "text/html; charset=utf-8")
                return
            questions = assessment_questions(lesson)
            form = self._form_lists(200000)
            picks = []
            score = 0
            try:
                for question_index, question in enumerate(questions):
                    pick, correct = grade(question, question_index, form)
                    picks.append(pick)
                    score += 1 if correct else 0
            except (ValueError, KeyError, TypeError):
                page = render_assessment(course, index, "That answer sheet could not be read. Start again.")
                self._send(400, page.encode(), "text/html; charset=utf-8")
                return
            raw_violations = (form.get("violations") or ["0"])[0]
            violations = min(int(raw_violations), 99) if raw_violations.isdigit() else 0
            flags = [flag for flag in (form.get("flags") or [""])[0].split(",") if flag in ASSESS_FLAGS][:20]
            violations = max(violations, len(flags))

            def record_lesson(found: dict) -> None:
                current = find_course(found, course_id)
                if current is None:
                    return
                target = current["lessons"][index]
                if not target.get("studied"):
                    target["studied"] = today_key()
                target.setdefault("attempts", []).append(
                    {
                        "score": score,
                        "total": len(questions),
                        "picks": picks,
                        "at": today_key(),
                        "violations": violations,
                        "flags": flags,
                        "questions": questions,
                    }
                )

            update_user(email, record_lesson)
            self._redirect(f"/courses/{course_id}/lessons/{index}/assess?result=1")
            return

        course_match = COURSE_RE.fullmatch(path)
        if course_match and course_match.group(2):
            email = self._learner()
            if not email:
                self._redirect("/login")
                return
            course_id, action = course_match.group(1), course_match.group(2)
            form = self._form()
            if action == "prompt":
                prompt = " ".join(form.get("prompt", "").split())
                mode = form.get("mode", "learn")
                if mode not in ("learn", "practice", "revise", "ask"):
                    mode = "learn"
                if not prompt or len(prompt) > 2000:
                    user = read_user(email)
                    course = find_course(user, course_id)
                    if course is None:
                        self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                        return
                    page = render_course(
                        email,
                        course,
                        review=bool(course.get("attempts")),
                        prompt_error="Ask a question under 2000 characters.",
                    )
                    self._send(400, page.encode(), "text/html; charset=utf-8")
                    return
                existing = find_course(read_user(email), course_id)
                if existing is None:
                    self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                    return
                try:
                    reply = discuss(existing, existing.get("notes") or [], prompt, mode)
                except GeminiError as exc:
                    page = render_course(email, existing, prompt_error=str(exc))
                    self._send(502, page.encode(), "text/html; charset=utf-8")
                    return

                def remember(user: dict) -> None:
                    course = find_course(user, course_id)
                    if course is None:
                        return
                    course.setdefault("notes", []).append(
                        {"prompt": prompt, "reply": reply, "at": today_key()}
                    )
                    course["notes"] = course["notes"][-30:]

                user = update_user(email, remember)
                if find_course(user, course_id) is None:
                    self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                    return
                self._redirect(f"/courses/{course_id}")
                return

            user = read_user(email)
            course = find_course(user, course_id)
            if course is None:
                self._send(404, b"That course is not on your desk.", "text/plain; charset=utf-8")
                return
            questions = course["quiz"]["questions"]
            picks = []
            for index in range(len(questions)):
                raw = form.get(f"q{index}", "")
                if not raw.isdigit() or int(raw) >= len(questions[index]["choices"]):
                    page = render_course(email, course, review=False, error="Answer every question.")
                    self._send(400, page.encode(), "text/html; charset=utf-8")
                    return
                picks.append(int(raw))
            score = sum(1 for index, pick in enumerate(picks) if pick == questions[index]["answer"])

            def record(user: dict) -> None:
                found = find_course(user, course_id)
                if found is None:
                    return
                found.setdefault("attempts", []).append(
                    {"score": score, "total": len(questions), "picks": picks, "at": today_key()}
                )

            update_user(email, record)
            self._redirect(f"/courses/{course_id}#quiz")
            return

        if path != "/api/guide":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 4000:
            self._json(400, {"error": "That question is too long."})
            return

        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "Send the question as JSON."})
            return

        query = str(payload.get("query", "")).strip()
        if not query:
            self._json(400, {"error": "Tell Lumina what you want to learn."})
            return
        if len(query) > 180:
            self._json(400, {"error": "Keep the question under 180 characters."})
            return
        self._json(200, draft_path(query))

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8")


if __name__ == "__main__":
    init_db()
    SECRET = session_secret()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Lumina is running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
