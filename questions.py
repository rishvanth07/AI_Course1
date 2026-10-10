"""Assessment question types: cleaning drafted questions, running code answers, and grading."""

import json
import random
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TYPES = ("single", "truefalse", "multi", "fill", "match", "code")
LABELS = {
    "single": "Single choice",
    "truefalse": "True or false",
    "multi": "Multiple answers",
    "fill": "Fill in the blank",
    "match": "Match the pairs",
    "code": "Coding",
}
SECONDS = {"single": 75, "truefalse": 45, "multi": 105, "fill": 90, "match": 150, "code": 420}
LANGUAGES = {"python": "Python", "javascript": "JavaScript", "sql": "SQL"}
BLANK = "_____"
OUTPUT_LIMIT = 4000
CODE_LIMIT = 20000
RUN_SECONDS = 4
SAMPLE_TESTS = 2
MIN_TESTS = 3
MAX_TESTS = 6

LIMITER = r"""
import os, resource, sys
for name, value in (("RLIMIT_CPU", 3), ("RLIMIT_FSIZE", 1_000_000), ("RLIMIT_CORE", 0)):
    try:
        resource.setrlimit(getattr(resource, name), (value, value))
    except (AttributeError, ValueError, OSError):
        pass
os.execv(sys.argv[1], sys.argv[1:])
"""

PY_LAUNCHER = r"""
import sys, traceback
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
source = open("main.py", encoding="utf-8").read()
try:
    exec(compile(source, "main.py", "exec"), {"__name__": "__main__"})
except SystemExit:
    raise
except BaseException as exc:
    frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if frame.filename == "main.py"]
    lines = traceback.format_list(frames) + traceback.format_exception_only(type(exc), exc)
    sys.stderr.write("Traceback (most recent call last):\n" + "".join(lines))
    sys.exit(1)
"""

PY_TESTS = r"""


def __lumina_check():
    import json as _json, sys as _sys
    _results = []
    for _call in __CALLS__:
        try:
            _results.append([True, repr(eval(_call, globals()))])
        except Exception as _exc:
            _results.append([False, f"{type(_exc).__name__}: {_exc}"])
    _sys.stdout.write("\n" + __TOKEN__ + _json.dumps(_results) + "\n")


__lumina_check()
"""

JS_TESTS = r"""
;(() => {
  const __show = (value) => {
    if (value === undefined) return "undefined";
    if (typeof value === "function") return "[Function]";
    if (typeof value === "number" && !Number.isFinite(value)) return String(value);
    try {
      const text = JSON.stringify(value);
      return text === undefined ? String(value) : text;
    } catch {
      return String(value);
    }
  };
  const __results = [];
  for (const __call of __CALLS__) {
    try {
      __results.push([true, __show(eval(__call))]);
    } catch (error) {
      __results.push([false, `${(error && error.name) || "Error"}: ${(error && error.message) || error}`]);
    }
  }
  process.stdout.write("\n" + __TOKEN__ + JSON.stringify(__results) + "\n");
})();
"""


def available_languages() -> list[str]:
    languages = ["python", "sql"]
    if shutil.which("node"):
        languages.insert(1, "javascript")
    return languages


def clean(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    kind = str(item.get("type") or "").strip().lower()
    prompt = _clip(item.get("prompt"), 600)
    if not prompt:
        return None
    builders = {
        "single": _single,
        "truefalse": _truefalse,
        "multi": _multi,
        "fill": _fill,
        "match": _match,
        "code": _code,
    }
    builder = builders.get(kind)
    return builder(item, prompt) if builder else None


def kind_of(question: dict) -> str:
    kind = question.get("type")
    return kind if kind in TYPES else "single"


def label(question: dict) -> str:
    kind = kind_of(question)
    if kind == "code":
        return f"Coding · {LANGUAGES.get(question.get('language'), 'Code')}"
    return LABELS[kind]


def seconds_for(questions: list[dict]) -> int:
    return max(60, sum(SECONDS[kind_of(question)] for question in questions))


def _single(item: dict, prompt: str) -> dict | None:
    choices = _choices(item.get("choices"))
    answers = _indexes(item.get("answers"), len(choices))
    if not 3 <= len(choices) <= 5 or len(answers) != 1:
        return None
    correct = choices[answers[0]]
    random.shuffle(choices)
    return {"type": "single", "prompt": prompt, "choices": choices, "answer": choices.index(correct)}


def _truefalse(item: dict, prompt: str) -> dict | None:
    answers = _indexes(item.get("answers"), 2)
    if len(answers) != 1:
        return None
    return {"type": "truefalse", "prompt": prompt, "choices": ["True", "False"], "answer": answers[0]}


def _multi(item: dict, prompt: str) -> dict | None:
    choices = _choices(item.get("choices"))
    answers = _indexes(item.get("answers"), len(choices))
    if not 4 <= len(choices) <= 6 or not 2 <= len(answers) < len(choices):
        return None
    correct = {choices[index] for index in answers}
    random.shuffle(choices)
    return {
        "type": "multi",
        "prompt": prompt,
        "choices": choices,
        "answers": sorted(index for index, choice in enumerate(choices) if choice in correct),
    }


def _fill(item: dict, prompt: str) -> dict | None:
    text = re.sub(r"_{3,}", BLANK, prompt)
    if text.count(BLANK) != 1:
        return None
    accept = []
    for value in item.get("blanks") or []:
        answer = _clip(value, 80)
        if answer and _norm(answer) not in {_norm(seen) for seen in accept}:
            accept.append(answer)
    if not 1 <= len(accept) <= 5:
        return None
    return {"type": "fill", "prompt": text, "accept": accept}


def _match(item: dict, prompt: str) -> dict | None:
    pairs = []
    for pair in item.get("pairs") or []:
        if not isinstance(pair, dict):
            return None
        left = _clip(pair.get("left"), 160)
        right = _clip(pair.get("right"), 160)
        if not left or not right:
            return None
        pairs.append((left, right))
    lefts = [left for left, _ in pairs]
    rights = [right for _, right in pairs]
    if not 3 <= len(pairs) <= 6 or len(set(lefts)) != len(lefts) or len(set(rights)) != len(rights):
        return None
    shuffled = rights[:]
    for _ in range(6):
        random.shuffle(shuffled)
        if shuffled != rights:
            break
    return {
        "type": "match",
        "prompt": prompt,
        "left": lefts,
        "right": shuffled,
        "answer": [shuffled.index(right) for right in rights],
    }


def _code(item: dict, prompt: str) -> dict | None:
    language = str(item.get("language") or "").strip().lower()
    if language not in available_languages():
        return None
    starter = _source(item.get("starter"), 3000)
    solution = _source(item.get("solution"), 4000)
    if not solution:
        return None
    question = {"type": "code", "prompt": prompt, "language": language, "starter": starter, "solution": solution}
    if language == "sql":
        setup = _source(item.get("setup"), 6000)
        if not setup:
            return None
        question["setup"] = setup
        expected = run_sql(setup, solution)
        if not expected["ok"] or not expected["columns"] or not expected["rows"]:
            return None
        question["ordered"] = "order by" in solution.lower()
        if starter and _same_rows(run_sql(setup, starter), expected, question["ordered"]):
            return None
        check = _source(item.get("check"), 4000)
        if check:
            hidden = run_sql(f"{setup}\n{check}", solution)
            if hidden["ok"] and hidden["rows"]:
                question["check"] = check
        return question
    calls = _calls(item.get("tests"))
    if len(calls) >= MIN_TESTS:
        ran = run_tests(language, solution, calls)
        tests = []
        if ran["results"] is not None:
            tests = [
                {"call": call, "expected": value}
                for call, (ok, value) in zip(calls, ran["results"])
                if ok and len(value) <= 300
            ]
        if len(tests) >= MIN_TESTS:
            question["tests"] = tests
            if starter and check_code(question, starter)["passed"]:
                return None
            return question
    expected = run_program(language, solution)
    output = normalize_output(expected["output"])
    if not expected["ok"] or not output:
        return None
    if starter and normalize_output(run_program(language, starter)["output"]) == output:
        return None
    question["expected"] = output
    return question


def _calls(value) -> list[str]:
    if not isinstance(value, list):
        return []
    calls = []
    for item in value:
        call = str(item or "").strip().rstrip(";").strip()
        if call and "\n" not in call and len(call) <= 200 and call not in calls:
            calls.append(call)
    return calls[:MAX_TESTS]


def sample_tests(question: dict) -> list[dict]:
    return (question.get("tests") or [])[:SAMPLE_TESTS]


def hidden_count(question: dict) -> int:
    return max(0, len(question.get("tests") or []) - SAMPLE_TESTS)


def check_code(question: dict, code: str, *, samples_only: bool = False) -> dict:
    """Run an answer and compare it with the expected result.

    For Python and JavaScript questions with tests, each test call's value is compared;
    `samples_only` limits the run to the example calls so hidden inputs never reach the learner.
    """
    language = question["language"]
    if language == "sql":
        result = run_sql(question["setup"], code)
        expected = run_sql(question["setup"], question["solution"])
        ordered = question.get("ordered", False)
        passed = _same_rows(result, expected, ordered)
        hidden = None
        if question.get("check") and not samples_only and passed:
            data = f"{question['setup']}\n{question['check']}"
            hidden = _same_rows(run_sql(data, code), run_sql(data, question["solution"]), ordered)
            passed = passed and hidden
        return {**result, "passed": passed, "hidden": hidden}
    tests = question.get("tests") or []
    if not tests:
        result = run_program(language, code)
        passed = result["ok"] and normalize_output(result["output"]) == question.get("expected")
        return {**result, "passed": passed, "tests": None}
    chosen = tests[:SAMPLE_TESTS] if samples_only else tests
    ran = run_tests(language, code, [test["call"] for test in chosen])
    checks = []
    for position, test in enumerate(chosen):
        got = ran["results"][position] if ran["results"] is not None else None
        checks.append(
            {
                "call": test["call"],
                "expected": test["expected"],
                "got": (got[1] if got else "")[:300],
                "raised": bool(got) and not got[0],
                "pass": bool(got) and got[0] and got[1] == test["expected"],
            }
        )
    passed = ran["results"] is not None and all(check["pass"] for check in checks)
    return {"ok": ran["ok"], "output": ran["output"], "error": ran["error"], "passed": passed, "tests": checks}


def run_tests(language: str, source: str, calls: list[str]) -> dict:
    token = f"@@lumina-{secrets.token_hex(6)}@@"
    harness = (PY_TESTS if language == "python" else JS_TESTS).replace("__CALLS__", json.dumps(calls))
    harness = harness.replace("__TOKEN__", json.dumps(token))
    result = run_program(language, f"{source.rstrip()}\n{harness}", limit=1_100_000)
    results = None
    kept = []
    for line in result["output"].split("\n"):
        if line.startswith(token):
            try:
                results = json.loads(line[len(token):])
            except ValueError:
                results = None
        else:
            kept.append(line)
    valid = (
        isinstance(results, list)
        and len(results) == len(calls)
        and all(isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], str) for entry in results)
    )
    output = "\n".join(kept).rstrip("\n")
    output = f"{output}\n" if output else ""
    return {
        "ok": result["ok"] and valid,
        "output": output[:OUTPUT_LIMIT],
        "error": result["error"],
        "results": results if valid else None,
    }


def grade(question: dict, number: int, form: dict[str, list[str]]):
    kind = kind_of(question)
    if kind in ("single", "truefalse"):
        raw = _first(form, f"q{number}")
        if raw == "":
            return -1, False
        pick = _index(raw, len(question["choices"]))
        return pick, pick == question["answer"]
    if kind == "multi":
        picks = sorted({_index(raw, len(question["choices"])) for raw in form.get(f"q{number}", []) if raw != ""})
        return picks, picks == question["answers"]
    if kind == "fill":
        text = _clip(_first(form, f"q{number}"), 200)
        return text, fill_matches(question, text)
    if kind == "match":
        picks = []
        for row in range(len(question["left"])):
            raw = _first(form, f"q{number}_{row}")
            picks.append(-1 if raw == "" else _index(raw, len(question["right"])))
        return picks, picks == question["answer"]
    code = _first(form, f"q{number}")[:CODE_LIMIT].replace("\r\n", "\n")
    if not code.strip() or code.strip() == question.get("starter", "").strip():
        return {"code": code, "output": "", "error": "", "passed": False, "ran": False}, False
    result = check_code(question, code)
    if question["language"] == "sql":
        output = format_table(result["columns"], result["rows"]) if result["ok"] else ""
    else:
        output = result["output"]
    pick = {
        "code": code,
        "output": output[:OUTPUT_LIMIT],
        "error": result["error"][:OUTPUT_LIMIT],
        "passed": result["passed"],
        "ran": True,
    }
    if result.get("tests"):
        pick["tests"] = [{"got": check["got"], "raised": check["raised"], "pass": check["pass"]} for check in result["tests"]]
    if result.get("hidden") is not None:
        pick["hidden"] = result["hidden"]
    return pick, result["passed"]


def fill_matches(question: dict, text: str) -> bool:
    return bool(text) and _norm(text) in {_norm(answer) for answer in question["accept"]}


def answered(question: dict, pick) -> bool:
    kind = kind_of(question)
    if kind in ("single", "truefalse"):
        return isinstance(pick, int) and pick >= 0
    if kind == "match":
        return isinstance(pick, list) and any(value >= 0 for value in pick)
    if kind == "code":
        return isinstance(pick, dict) and pick.get("ran", False)
    return bool(pick)


def run_code(question: dict, code: str) -> dict:
    if question["language"] == "sql":
        return run_sql(question["setup"], code)
    if question.get("tests"):
        result = check_code(question, code, samples_only=True)
        return {
            "ok": result["ok"],
            "output": result["output"],
            "error": result["error"],
            "tests": result["tests"],
            "hidden": hidden_count(question),
        }
    return run_program(question["language"], code)


def run_program(language: str, source: str, limit: int = OUTPUT_LIMIT) -> dict:
    with tempfile.TemporaryDirectory(prefix="lumina-run-") as folder:
        root = Path(folder)
        (root / "limit.py").write_text(LIMITER, encoding="utf-8")
        if language == "javascript":
            node = shutil.which("node")
            if not node:
                return {"ok": False, "output": "", "error": "JavaScript isn't available on this computer."}
            (root / "main.js").write_text(source, encoding="utf-8")
            command = [node, "--max-old-space-size=128", "main.js"]
        else:
            (root / "main.py").write_text(source, encoding="utf-8")
            (root / "launch.py").write_text(PY_LAUNCHER, encoding="utf-8")
            command = [sys.executable, "-s", "-P", "launch.py"]
        out_path = root / "stdout.txt"
        err_path = root / "stderr.txt"
        try:
            with out_path.open("w") as out, err_path.open("w") as err:
                done = subprocess.run(
                    [sys.executable, "-I", "limit.py", *command],
                    cwd=folder,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", "PYTHONHASHSEED": "0"},
                    timeout=RUN_SECONDS,
                )
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": _read(out_path), "error": f"Stopped after {RUN_SECONDS} seconds. Check for an endless loop."}
        output = _read(out_path, limit)
        error = _read(err_path)
    if done.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
        error = "Stopped: the program used too much processor time."
    elif done.returncode == -signal.SIGXFSZ or "File too large" in error:
        error = "Stopped: the program printed too much output."
    elif language == "javascript" and error:
        error = _node_error(error)
    return {"ok": done.returncode == 0, "output": output, "error": error}


def _node_error(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "node:internal" in line or "node:diagnostics" in line or line.startswith("Node.js v"):
            continue
        lines.append(re.sub(r"[^\s(]*main\.js", "main.js", line))
    return "\n".join(lines).strip() + "\n"


def run_sql(setup: str, query: str, limit: int = 200) -> dict:
    conn = sqlite3.connect(":memory:")
    try:
        try:
            conn.executescript(setup)
        except sqlite3.Error as exc:
            return {"ok": False, "columns": [], "rows": [], "error": f"Setup failed: {exc}", "truncated": False}
        deadline = time.monotonic() + 2
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
        conn.set_authorizer(_authorize)
        if not query.strip():
            return {"ok": False, "columns": [], "rows": [], "error": "Write a query first.", "truncated": False}
        try:
            cursor = conn.execute(query)
            columns = [column[0] for column in cursor.description or []]
            rows = [[_cell(value) for value in row] for row in cursor.fetchmany(limit + 1)]
        except sqlite3.Error as exc:
            message = "The query took too long." if "interrupt" in str(exc).lower() else str(exc)
            return {"ok": False, "columns": [], "rows": [], "error": message, "truncated": False}
        if not columns:
            return {"ok": False, "columns": [], "rows": [], "error": "Write a query that returns rows, such as a SELECT.", "truncated": False}
        return {"ok": True, "columns": columns, "rows": rows[:limit], "error": "", "truncated": len(rows) > limit}
    finally:
        conn.close()


def sql_tables(setup: str, limit: int = 8) -> list[dict]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(setup)
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
            )
        ]
        tables = []
        for name in names:
            cursor = conn.execute(f'SELECT * FROM "{name.replace(chr(34), "")}" LIMIT {limit}')
            tables.append(
                {
                    "name": name,
                    "columns": [column[0] for column in cursor.description or []],
                    "rows": [[_cell(value) for value in row] for row in cursor.fetchall()],
                }
            )
        return tables
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def format_table(columns: list[str], rows: list[list]) -> str:
    lines = [" | ".join(str(column) for column in columns)]
    lines += [" | ".join("NULL" if value is None else str(value) for value in row) for row in rows]
    return "\n".join(lines)


def normalize_output(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").strip("\n").splitlines()).strip()


def _authorize(action, *_args):
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _same_rows(result: dict, expected: dict, ordered: bool) -> bool:
    if not result.get("ok") or not expected.get("ok"):
        return False
    mine = [tuple(_compare(value) for value in row) for row in result["rows"]]
    theirs = [tuple(_compare(value) for value in row) for row in expected["rows"]]
    if len(result["columns"]) != len(expected["columns"]):
        return False
    if ordered:
        return mine == theirs
    return sorted(mine, key=repr) == sorted(theirs, key=repr)


def _compare(value):
    if isinstance(value, float):
        rounded = round(value, 6)
        return int(rounded) if rounded.is_integer() else rounded
    return value


def _cell(value):
    if isinstance(value, bytes):
        return value.hex()
    return value


def _read(path: Path, limit: int = OUTPUT_LIMIT) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _first(form: dict[str, list[str]], key: str) -> str:
    values = form.get(key) or [""]
    return values[0]


def _index(raw: str, size: int) -> int:
    if not raw.isdigit() or int(raw) >= size:
        raise ValueError("answer out of range")
    return int(raw)


def _choices(value) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clip(choice, 240) for choice in value]
    cleaned = [choice for choice in cleaned if choice]
    return cleaned if len(set(cleaned)) == len(cleaned) else []


def _indexes(value, size: int) -> list[int]:
    if not isinstance(value, list):
        return []
    found = set()
    for item in value:
        try:
            number = int(item)
        except (TypeError, ValueError):
            return []
        if not 0 <= number < size:
            return []
        found.add(number)
    return sorted(found)


def _norm(text: str) -> str:
    return " ".join(str(text).lower().split()).strip(" .,;:!?\"'`")


def _clip(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit].rstrip()


def _source(value, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\t", "    ")
    return text.strip("\n").rstrip()[:limit]
