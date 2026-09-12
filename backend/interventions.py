import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

INTERVENTION_TYPES = (
    "Counseling",
    "Tutoring",
    "Attendance Support",
    "Financial Aid Check",
    "Mentorship",
    "Other",
)

STATUSES = ("Open", "In Progress", "Resolved")

SCHEMA = """
CREATE TABLE IF NOT EXISTS interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    student_name TEXT NOT NULL DEFAULT '',
    intervention_type TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Open',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db():
    with _connect() as conn:
        conn.execute(SCHEMA)
        conn.commit()


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")


def create(student_id, student_name, intervention_type, description, created_by):
    if student_id is None or student_id == "":
        raise ValueError("student_id is required")
    if not intervention_type:
        raise ValueError("intervention_type is required")
    if intervention_type not in INTERVENTION_TYPES:
        raise ValueError("invalid intervention_type")
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO interventions
               (student_id, student_name, intervention_type, description, status,
                created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'Open', ?, ?, ?)""",
            (
                int(student_id),
                student_name or "",
                intervention_type,
                description or "",
                created_by or "",
                now,
                now,
            ),
        )
        conn.commit()
        return dict(
            conn.execute(
                "SELECT * FROM interventions WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        )


def list_interventions(status=None, student_id=None, term=None):
    query = "SELECT * FROM interventions WHERE 1=1"
    args = []
    if status:
        query += " AND status = ?"
        args.append(status)
    if student_id is not None and student_id != "":
        query += " AND student_id = ?"
        args.append(int(student_id))
    if term:
        like = f"%{term}%"
        query += " AND (student_name LIKE ? OR description LIKE ? OR intervention_type LIKE ?)"
        args += [like, like, like]
    query += " ORDER BY id DESC"
    with _connect() as conn:
        return [dict(r) for r in conn.execute(query, args).fetchall()]


def update_status(iid, status):
    if status not in STATUSES:
        raise ValueError("invalid status")
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE interventions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, iid),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        return dict(
            conn.execute(
                "SELECT * FROM interventions WHERE id = ?", (iid,)
            ).fetchone()
        )


def delete(iid):
    with _connect() as conn:
        cur = conn.execute("DELETE FROM interventions WHERE id = ?", (iid,))
        conn.commit()
        return cur.rowcount > 0


def get(iid):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM interventions WHERE id = ?", (iid,)
        ).fetchone()
        return dict(row) if row else None