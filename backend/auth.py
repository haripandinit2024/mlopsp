"""
Authentication - SQLite user store with hashed passwords.

Roles: student, faculty, admin. Each user gets exactly one role and the
dashboard only exposes the views allowed for that role.
"""
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

VALID_ROLES = ("student", "faculty", "admin")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('student', 'faculty', 'admin')),
    password_hash TEXT NOT NULL,
    student_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after the initial schema, applied on every startup so existing
# databases are upgraded in place.
_MIGRATIONS = (
    ("student_id", "ALTER TABLE users ADD COLUMN student_id INTEGER"),
)


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(_SCHEMA)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        for column, statement in _MIGRATIONS:
            if column not in existing:
                conn.execute(statement)
        conn.commit()


def user_from_row(row):
    keys = row.keys()
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        # None for staff accounts; identifies which roster record a student
        # login is allowed to read.
        "student_id": row["student_id"] if "student_id" in keys else None,
    }


def create_user(name, email, role, password, student_id=None):
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}")
    # Normalise the same way lookups do, so an account created directly through
    # this module is always reachable by `find_user_by_email`.
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("Email is required")

    if student_id is not None and student_id != "":
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            raise ValueError("student_id must be an integer") from None
        if student_id < 1:
            raise ValueError("student_id must be a positive integer")
    else:
        student_id = None

    hashed = generate_password_hash(password)
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, role, password_hash, student_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, email, role, hashed, student_id),
            )
            conn.commit()
            return user_from_row(conn.execute(
                "SELECT id, name, email, role, password_hash, student_id FROM users "
                "WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone())
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with that email already exists") from exc


def find_user_by_email(email):
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, email, role, password_hash, student_id FROM users "
            "WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
    return row


def authenticate(email, password):
    row = find_user_by_email(email)
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return user_from_row(row)