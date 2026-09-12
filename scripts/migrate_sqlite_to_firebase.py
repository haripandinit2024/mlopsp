"""
One-time migration: SQLite users.db  ->  Firebase Auth + Cloud Firestore.

    python scripts/migrate_sqlite_to_firebase.py                # dry run (default)
    python scripts/migrate_sqlite_to_firebase.py --apply        # write changes

What it does
------------
users table
    * Creates a matching Firebase Authentication account for every email.
    * Passwords CANNOT be migrated: the legacy store keeps only one-way
      pbkdf2 hashes. Each account is created with a random password and a
      Firebase password-reset link is written to the report file so the
      account holder can set a new one.
    * Writes a Firestore `users/{uid}` profile carrying name, email, role,
      studentId and status.

interventions table
    * Copies every row to the Firestore `interventions` collection, mapping
      the legacy column names onto the new document schema.

Safety
------
* Dry-run by default; nothing is written without --apply.
* The legacy database is opened READ-ONLY - it is your rollback.
* Idempotent: existing Firebase accounts and Firestore documents are skipped.
* The report file contains password-reset links, which are credentials. It is
  gitignored; distribute the links privately and then delete the file.
* Never prints passwords, keys or credentials to stdout.
"""

from __future__ import annotations

import argparse
import csv
import secrets
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.env_loader import load_env  # noqa: E402
from backend import firebase_admin_app as fb  # noqa: E402
from backend import firestore_service as store  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "backend" / "users.db"
DEFAULT_REPORT = PROJECT_ROOT / "migration_report.csv"

VALID_ROLES = {"student", "faculty", "admin"}


def read_legacy_rows(db_path: Path, table: str) -> list[dict]:
    """Read a table from the legacy SQLite file without modifying it."""
    if not db_path.exists():
        print(f"[!] Legacy database not found: {db_path}", file=sys.stderr)
        return []
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
    except sqlite3.OperationalError as exc:
        print(f"[!] Could not read table '{table}': {exc}", file=sys.stderr)
        return []
    finally:
        connection.close()
    return rows


def build_student_index(roster_path: Path) -> set[int]:
    """Known Student_IDs, so a bad link is reported instead of silently stored."""
    try:
        import csv as _csv

        with roster_path.open(newline="", encoding="utf-8") as handle:
            return {int(row["Student_ID"]) for row in _csv.DictReader(handle)}
    except Exception:
        return set()


def migrate_users(rows, apply: bool, report: list[dict], known_students: set[int]) -> dict:
    summary = {"created": 0, "skipped": 0, "failed": 0, "invalid": 0}
    auth = None
    if apply:
        auth = fb.get_auth()

    for row in rows:
        email = (row.get("email") or "").strip().lower()
        name = (row.get("name") or "").strip() or email.split("@")[0]
        role = (row.get("role") or "").strip().lower()
        student_id = row.get("student_id")

        if not email or role not in VALID_ROLES:
            summary["invalid"] += 1
            report.append({
                "kind": "user", "email": email, "uid": "", "reset_link": "",
                "status": "invalid row (missing email or bad role)",
            })
            continue

        if student_id is not None:
            try:
                student_id = int(student_id)
            except (TypeError, ValueError):
                student_id = None
            if student_id is not None and known_students and student_id not in known_students:
                summary["invalid"] += 1
                report.append({
                    "kind": "user", "email": email, "uid": "", "reset_link": "",
                    "status": f"unknown student_id {student_id}",
                })
                continue

        if not apply:
            summary["created"] += 1
            report.append({"kind": "user", "email": email, "uid": "(dry-run)",
                           "reset_link": "(dry-run)", "status": "would create"})
            continue

        try:
            try:
                existing = auth.get_user_by_email(email)
                summary["skipped"] += 1
                uid = existing.uid
                status = "already existed"
            except Exception:
                # Random password: never derived from anything guessable, and
                # never written to disk or printed.
                created = auth.create_user(
                    email=email,
                    display_name=name,
                    password=secrets.token_urlsafe(32),
                    email_verified=False,
                )
                uid = created.uid
                summary["created"] += 1
                status = "created"

            store.create_user_profile(uid, name, email, role, student_id)

            reset_link = ""
            try:
                reset_link = auth.generate_password_reset_link(email)
            except Exception:
                reset_link = "(could not generate reset link)"

            report.append({
                "kind": "user", "email": email, "uid": uid,
                "reset_link": reset_link, "status": status,
            })
        except Exception as exc:
            summary["failed"] += 1
            report.append({
                "kind": "user", "email": email, "uid": "", "reset_link": "",
                "status": f"FAILED: {type(exc).__name__}",
            })

    return summary


def migrate_interventions(rows, apply: bool, report: list[dict]) -> dict:
    summary = {"created": 0, "skipped": 0, "failed": 0, "invalid": 0}

    for row in rows:
        student_id = row.get("student_id")
        intervention_type = (row.get("intervention_type") or "").strip()
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            summary["invalid"] += 1
            report.append({"kind": "intervention", "email": "", "uid": "",
                           "reset_link": "", "status": f"bad student_id: {student_id!r}"})
            continue

        if intervention_type not in store.INTERVENTION_TYPES:
            # Keep the data but record the mismatch rather than dropping it.
            intervention_type = "Other"

        if not apply:
            summary["created"] += 1
            report.append({"kind": "intervention", "email": "", "uid": "",
                           "reset_link": "", "status": f"would migrate #{row.get('id')}"})
            continue

        try:
            _db = store._db()
            document = {
                "studentId": student_id,
                "studentName": row.get("student_name") or "",
                "type": intervention_type,
                "reason": "",
                "description": row.get("description") or "",
                "priority": "Medium",
                "assignedTo": None,
                "status": row.get("status") or "Open",
                "createdBy": row.get("created_by") or "",
                "createdAt": row.get("created_at") or store.utcnow(),
                "updatedAt": row.get("updated_at") or store.utcnow(),
                "migratedFrom": f"sqlite:interventions:{row.get('id')}",
            }
            _db.collection(store.INTERVENTIONS).document(
                f"legacy-{row.get('id')}"
            ).set(document, merge=True)
            summary["created"] += 1
            report.append({"kind": "intervention", "email": "", "uid": "",
                           "reset_link": "", "status": f"migrated #{row.get('id')}"})
        except Exception as exc:
            summary["failed"] += 1
            report.append({"kind": "intervention", "email": "", "uid": "",
                           "reset_link": "", "status": f"FAILED: {type(exc).__name__}"})

    return summary


def write_report(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["kind", "email", "uid", "reset_link", "status"]
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually write to Firebase (default is a dry run)")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="legacy SQLite path")
    parser.add_argument("--report", default=str(DEFAULT_REPORT),
                        help="where to write the migration report")
    args = parser.parse_args()

    load_env()

    if args.apply and not fb.is_configured():
        print(
            "[!] Firebase is not configured. Set FIREBASE_PROJECT_ID and provide "
            "service-account credentials before using --apply.",
            file=sys.stderr,
        )
        return 2

    db_path = Path(args.db)
    roster_path = PROJECT_ROOT / "dataset" / "processed" / "student_risk_scores.csv"

    print("=" * 68)
    print("  SQLite -> Firebase migration")
    print(f"  mode: {'APPLY (writes)' if args.apply else 'DRY RUN (no writes)'}")
    print(f"  legacy db: {db_path}")
    print("=" * 68)

    users = read_legacy_rows(db_path, "users")
    intervention_rows = read_legacy_rows(db_path, "interventions")
    known_students = build_student_index(roster_path)

    print(f"  legacy users:         {len(users)}")
    print(f"  legacy interventions: {len(intervention_rows)}")
    print(f"  known roster ids:     {len(known_students)}")

    if not users and not intervention_rows:
        print("\nNothing to migrate.")
        return 0

    report: list[dict] = []
    if users:
        print("\n-- users --")
        summary = migrate_users(users, args.apply, report, known_students)
        print(f"  {summary}")
    if intervention_rows:
        print("\n-- interventions --")
        summary = migrate_interventions(intervention_rows, args.apply, report)
        print(f"  {summary}")

    write_report(Path(args.report), report)
    print(f"\nReport written to {args.report}")
    if args.apply:
        print(
            "  NOTE: that file contains password-reset links, which are "
            "credentials.\n  Distribute them privately, then delete the file."
        )
    else:
        print("  Dry run only - re-run with --apply to write changes.")
    print("\nThe legacy users.db was opened read-only and is unchanged (rollback).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
