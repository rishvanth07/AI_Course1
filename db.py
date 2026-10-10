"""SQLite storage for learners, courses, lessons, and quiz attempts."""

import json
import secrets
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_FILE = ROOT / "data" / "lumina.db"
LEGACY_FILE = ROOT / "data" / "learners.json"
LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    overview TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL,
    path_json TEXT NOT NULL DEFAULT '',
    quiz_json TEXT NOT NULL DEFAULT '',
    certificate_json TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    sections_json TEXT NOT NULL,
    quiz_json TEXT NOT NULL,
    studied TEXT,
    assessment_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS lesson_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    picks_json TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT '',
    violations INTEGER NOT NULL DEFAULT 0,
    flags_json TEXT NOT NULL DEFAULT '[]',
    questions_json TEXT NOT NULL DEFAULT '',
    feedback_json TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    reply_json TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS course_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    total INTEGER NOT NULL,
    picks_json TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
);
"""


def connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with LOCK:
        with connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
            for column in ("name", "password_hash", "created"):
                if column not in columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(lesson_attempts)")}
            if "violations" not in columns:
                conn.execute("ALTER TABLE lesson_attempts ADD COLUMN violations INTEGER NOT NULL DEFAULT 0")
            if "flags_json" not in columns:
                conn.execute("ALTER TABLE lesson_attempts ADD COLUMN flags_json TEXT NOT NULL DEFAULT '[]'")
            if "questions_json" not in columns:
                conn.execute("ALTER TABLE lesson_attempts ADD COLUMN questions_json TEXT NOT NULL DEFAULT ''")
            if "feedback_json" not in columns:
                conn.execute("ALTER TABLE lesson_attempts ADD COLUMN feedback_json TEXT NOT NULL DEFAULT ''")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(courses)")}
            if "certificate_json" not in columns:
                conn.execute("ALTER TABLE courses ADD COLUMN certificate_json TEXT NOT NULL DEFAULT ''")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(lessons)")}
            if "assessment_json" not in columns:
                conn.execute("ALTER TABLE lessons ADD COLUMN assessment_json TEXT NOT NULL DEFAULT '[]'")
            imported = conn.execute("SELECT value FROM meta WHERE key = 'imported'").fetchone()
            if imported is None:
                _import_legacy(conn)
                conn.execute("INSERT INTO meta (key, value) VALUES ('imported', '1')")
            conn.commit()


def session_secret() -> bytes:
    with LOCK:
        with connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'secret'").fetchone()
            if row is None:
                value = secrets.token_hex(32)
                conn.execute("INSERT INTO meta (key, value) VALUES ('secret', ?)", (value,))
                conn.commit()
                return bytes.fromhex(value)
            return bytes.fromhex(row["value"])


def read_account(email: str) -> dict | None:
    with LOCK:
        with connect() as conn:
            row = conn.execute(
                "SELECT email, name, password_hash, created FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            return dict(row) if row else None


def create_account(email: str, name: str, password_hash: str, created: str) -> bool:
    """Create the account, or claim one that has data but no password yet. False if already taken."""
    with LOCK:
        with connect() as conn:
            row = conn.execute("SELECT password_hash FROM users WHERE email = ?", (email,)).fetchone()
            if row is not None and row["password_hash"]:
                return False
            if row is None:
                conn.execute(
                    "INSERT INTO users (email, name, password_hash, created) VALUES (?, ?, ?, ?)",
                    (email, name, password_hash, created),
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, password_hash = ?, created = ? WHERE email = ?",
                    (name, password_hash, created, email),
                )
            conn.commit()
            return True


def read_user(email: str) -> dict:
    with LOCK:
        with connect() as conn:
            return _load(conn, email)


def update_user(email: str, mutator) -> dict:
    with LOCK:
        with connect() as conn:
            user = _load(conn, email)
            mutator(user)
            _save(conn, email, user)
            conn.commit()
            return json.loads(json.dumps(user))


def _import_legacy(conn: sqlite3.Connection) -> None:
    if not LEGACY_FILE.exists():
        return
    try:
        store = json.loads(LEGACY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    if not isinstance(store, dict):
        return
    for email, user in store.items():
        if not isinstance(email, str) or not isinstance(user, dict):
            continue
        _save(conn, email, {"courses": user.get("courses") or []})


def _load(conn: sqlite3.Connection, email: str) -> dict:
    exists = conn.execute("SELECT email FROM users WHERE email = ?", (email,)).fetchone()
    if exists is None:
        return {"courses": []}
    courses = []
    rows = conn.execute(
        "SELECT * FROM courses WHERE email = ? ORDER BY position, id",
        (email,),
    ).fetchall()
    for row in rows:
        course_id = row["id"]
        lessons = []
        lesson_rows = conn.execute(
            "SELECT * FROM lessons WHERE course_id = ? ORDER BY position, id",
            (course_id,),
        ).fetchall()
        for lesson in lesson_rows:
            attempts = [
                {
                    "score": attempt["score"],
                    "total": attempt["total"],
                    "picks": json.loads(attempt["picks_json"]),
                    "at": attempt["at"],
                    "violations": attempt["violations"],
                    "flags": json.loads(attempt["flags_json"] or "[]"),
                    "questions": json.loads(attempt["questions_json"]) if attempt["questions_json"] else None,
                    "feedback": json.loads(attempt["feedback_json"]) if attempt["feedback_json"] else None,
                }
                for attempt in conn.execute(
                    "SELECT * FROM lesson_attempts WHERE lesson_id = ? ORDER BY id",
                    (lesson["id"],),
                )
            ]
            lessons.append(
                {
                    "id": lesson["id"],
                    "title": lesson["title"],
                    "minutes": lesson["minutes"],
                    "sections": json.loads(lesson["sections_json"]),
                    "quiz": json.loads(lesson["quiz_json"]),
                    "assessment": json.loads(lesson["assessment_json"] or "[]"),
                    "studied": lesson["studied"],
                    "attempts": attempts,
                }
            )
        notes = [
            {
                "prompt": note["prompt"],
                "reply": json.loads(note["reply_json"]),
                "at": note["at"],
            }
            for note in conn.execute(
                "SELECT * FROM notes WHERE course_id = ? ORDER BY position, id",
                (course_id,),
            )
        ]
        attempts = [
            {
                "score": attempt["score"],
                "total": attempt["total"],
                "picks": json.loads(attempt["picks_json"]),
                "at": attempt["at"],
            }
            for attempt in conn.execute(
                "SELECT * FROM course_attempts WHERE course_id = ? ORDER BY id",
                (course_id,),
            )
        ]
        courses.append(
            {
                "id": course_id,
                "title": row["title"],
                "goal": row["goal"],
                "created": row["created"],
                "overview": row["overview"],
                "lessons": lessons,
                "path": json.loads(row["path_json"] or "null"),
                "notes": notes,
                "quiz": json.loads(row["quiz_json"] or "null") or {"title": "", "questions": []},
                "attempts": attempts,
                "certificate": json.loads(row["certificate_json"]) if row["certificate_json"] else None,
            }
        )
    return {"courses": courses}


def _save(conn: sqlite3.Connection, email: str, user: dict) -> None:
    conn.execute("INSERT OR IGNORE INTO users (email) VALUES (?)", (email,))
    conn.execute("DELETE FROM courses WHERE email = ?", (email,))
    seen_lessons: set[str] = set()
    for position, course in enumerate(user.get("courses") or []):
        course_id = str(course.get("id") or f"course-{position}")
        conn.execute(
            """
            INSERT INTO courses (
                id, email, title, goal, overview, created, position, path_json, quiz_json, certificate_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id,
                email,
                course.get("title") or "Course",
                course.get("goal") or "",
                course.get("overview") or "",
                course.get("created") or "",
                position,
                json.dumps(course.get("path")),
                json.dumps(course.get("quiz") or {"title": "", "questions": []}),
                json.dumps(course["certificate"]) if course.get("certificate") else "",
            ),
        )
        for lesson_index, lesson in enumerate(course.get("lessons") or []):
            lesson_id = str(lesson.get("id") or f"{course_id}-{lesson_index}")
            if lesson_id in seen_lessons:
                lesson_id = f"{course_id}-{lesson_id}-{lesson_index}"
            seen_lessons.add(lesson_id)
            lesson["id"] = lesson_id
            conn.execute(
                """
                INSERT INTO lessons (
                    id, course_id, position, title, minutes, sections_json, quiz_json, studied, assessment_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson_id,
                    course_id,
                    lesson_index,
                    lesson.get("title") or "Lesson",
                    int(lesson.get("minutes") or 15),
                    json.dumps(lesson.get("sections") or []),
                    json.dumps(lesson.get("quiz") or []),
                    lesson.get("studied"),
                    json.dumps(lesson.get("assessment") or []),
                ),
            )
            for attempt in lesson.get("attempts") or []:
                conn.execute(
                    """
                    INSERT INTO lesson_attempts (
                        lesson_id, score, total, picks_json, at, violations, flags_json, questions_json, feedback_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lesson_id,
                        int(attempt.get("score") or 0),
                        int(attempt.get("total") or 0),
                        json.dumps(attempt.get("picks") or []),
                        attempt.get("at") or "",
                        int(attempt.get("violations") or 0),
                        json.dumps(attempt.get("flags") or []),
                        json.dumps(attempt["questions"]) if attempt.get("questions") else "",
                        json.dumps(attempt["feedback"]) if attempt.get("feedback") else "",
                    ),
                )
        for note_index, note in enumerate(course.get("notes") or []):
            conn.execute(
                """
                INSERT INTO notes (course_id, position, prompt, reply_json, at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    note_index,
                    note.get("prompt") or "",
                    json.dumps(note.get("reply")),
                    note.get("at") or "",
                ),
            )
        for attempt in course.get("attempts") or []:
            conn.execute(
                """
                INSERT INTO course_attempts (course_id, score, total, picks_json, at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    int(attempt.get("score") or 0),
                    int(attempt.get("total") or 0),
                    json.dumps(attempt.get("picks") or []),
                    attempt.get("at") or "",
                ),
            )
