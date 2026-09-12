"""Unit tests: backend/auth.py — password storage, uniqueness, lookup."""
import unittest

from tests.base import AppTestCase, DEFAULT_PASSWORD
from backend import auth


class TestPasswordStorage(AppTestCase):
    def test_password_is_hashed_not_plaintext(self):
        self.make_user("student", "hash@example.com", password="SuperSecret1")
        with auth._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE email = ?", ("hash@example.com",)
            ).fetchone()
        stored = row["password_hash"]
        self.assertNotEqual(stored, "SuperSecret1", "password stored in plaintext")
        self.assertNotIn("SuperSecret1", stored)
        self.assertTrue(auth.check_password_hash(stored, "SuperSecret1"))
        self.assertFalse(auth.check_password_hash(stored, "WrongPassword1"))

    def test_two_users_same_password_get_different_hashes(self):
        self.make_user("student", "a@example.com")
        self.make_user("student", "b@example.com")
        with auth._connect() as conn:
            hashes = [
                r["password_hash"]
                for r in conn.execute("SELECT password_hash FROM users").fetchall()
            ]
        self.assertEqual(len(hashes), 2)
        self.assertNotEqual(hashes[0], hashes[1], "hashes are not salted uniquely")

    def test_public_user_dict_never_includes_hash(self):
        user = self.make_user("admin", "admin2@example.com")
        self.assertNotIn("password_hash", user)
        self.assertEqual(set(user), {"id", "name", "email", "role", "student_id"})

    def test_student_id_is_optional_and_stored_when_given(self):
        staff = self.make_user("faculty", "fac1@example.com")
        student = self.make_user("student", "st1@example.com", student_id=1)
        self.assertIsNone(staff["student_id"])
        self.assertEqual(student["student_id"], 1)

    def test_non_numeric_student_id_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("S", "bad@example.com", "student", DEFAULT_PASSWORD,
                             student_id="abc")

    def test_non_positive_student_id_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("S", "zero@example.com", "student", DEFAULT_PASSWORD,
                             student_id=0)


class TestUserValidation(AppTestCase):
    def test_duplicate_email_is_rejected(self):
        self.make_user("student", "dupe@example.com")
        with self.assertRaises(ValueError):
            self.make_user("student", "dupe@example.com")

    def test_duplicate_email_is_case_insensitive(self):
        self.make_user("student", "Case@Example.com")
        with self.assertRaises(ValueError):
            self.make_user("student", "case@example.com")

    def test_invalid_role_is_rejected(self):
        with self.assertRaises(ValueError):
            auth.create_user("X", "role@example.com", "superuser", DEFAULT_PASSWORD)

    def test_role_is_constrained_at_database_level(self):
        with auth._connect() as conn:
            with self.assertRaises(Exception):
                conn.execute(
                    "INSERT INTO users (name, email, role, password_hash) VALUES (?,?,?,?)",
                    ("X", "raw@example.com", "root", "x"),
                )

    def test_email_uniqueness_enforced_by_database(self):
        self.make_user("student", "uniq@example.com")
        with auth._connect() as conn:
            with self.assertRaises(Exception):
                conn.execute(
                    "INSERT INTO users (name, email, role, password_hash) VALUES (?,?,?,?)",
                    ("Dup", "uniq@example.com", "student", "x"),
                )


class TestAuthentication(AppTestCase):
    def test_correct_credentials_succeed(self):
        self.make_user("faculty", "fac@example.com")
        self.assertIsNotNone(auth.authenticate("fac@example.com", DEFAULT_PASSWORD))

    def test_wrong_password_returns_none(self):
        self.make_user("faculty", "fac2@example.com")
        self.assertIsNone(auth.authenticate("fac2@example.com", "not-the-password"))

    def test_unknown_email_returns_none(self):
        self.assertIsNone(auth.authenticate("nobody@example.com", DEFAULT_PASSWORD))

    def test_empty_password_does_not_authenticate(self):
        self.make_user("student", "empty@example.com")
        self.assertIsNone(auth.authenticate("empty@example.com", ""))

    def test_lookup_is_case_insensitive_and_trimmed(self):
        self.make_user("student", "Mixed@Example.com")
        self.assertIsNotNone(auth.authenticate("  mixed@example.com  ", DEFAULT_PASSWORD))

    def test_sql_injection_payload_in_email_is_safe(self):
        self.make_user("student", "safe@example.com")
        payloads = ["' OR '1'='1", "admin@example.com'--", "'; DROP TABLE users; --", '" OR 1=1--']
        for p in payloads:
            self.assertIsNone(auth.authenticate(p, p))
        # Table must still exist and still hold our user.
        with auth._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertEqual(count, 1)

    def test_sql_injection_cannot_bypass_password(self):
        self.make_user("admin", "realadmin@example.com")
        self.assertIsNone(
            auth.authenticate("realadmin@example.com", "' OR '1'='1")
        )


if __name__ == "__main__":
    unittest.main()
