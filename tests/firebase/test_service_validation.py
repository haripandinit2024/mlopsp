"""
Validation and pure-function tests for the Firestore service layer.

These need no Firebase connection, so they run everywhere.
"""
import os
import unittest
from unittest import mock

from backend import firebase_admin_app as fb, firestore_service as store


class TestUserDocument(unittest.TestCase):
    def test_password_fields_are_never_part_of_a_user_document(self):
        document = store.user_document("uid-1", "A", "a@example.com", "student")
        for forbidden in ("password", "password_hash", "passwordHash",
                          "private_key", "serviceAccount"):
            self.assertNotIn(forbidden, document)

    def test_email_is_normalised(self):
        document = store.user_document("uid-2", "A", "  MiXeD@Example.COM ", "student")
        self.assertEqual(document["email"], "mixed@example.com")

    def test_invalid_role_rejected(self):
        with self.assertRaises(ValueError):
            store.user_document("uid-3", "A", "a@example.com", "superuser")

    def test_student_link_is_dropped_for_staff(self):
        document = store.user_document("uid-4", "A", "a@example.com", "faculty",
                                       student_id=42)
        self.assertIsNone(document["studentId"])

    def test_blank_name_rejected(self):
        with self.assertRaises(ValueError):
            store.user_document("uid-5", "   ", "a@example.com", "student")

    def test_api_shape_matches_the_existing_frontend_contract(self):
        document = store.user_document("uid-6", "A", "a@example.com", "student", 7)
        api = store.to_api_user(document)
        self.assertEqual(api["id"], "uid-6")          # legacy field
        self.assertEqual(api["uid"], "uid-6")
        self.assertEqual(api["student_id"], 7)
        self.assertEqual(api["role"], "student")


class TestNumericValidation(unittest.TestCase):
    def test_marks_and_attendance_ranges(self):
        good = {"studentId": 1, "subject": "Maths", "internalMarks": 0,
                "assignmentMarks": 100, "attendance": 100, "backlog": 0}
        document = store._validate_academic(good)
        self.assertEqual(document["attendance"], 100)

    def test_attendance_above_100_rejected(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": 50, "assignmentMarks": 50,
                                      "attendance": 101})

    def test_negative_marks_rejected(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": -1, "assignmentMarks": 50,
                                      "attendance": 50})

    def test_negative_attendance_rejected(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": 50, "assignmentMarks": 50,
                                      "attendance": -0.1})

    def test_non_numeric_marks_rejected(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": "eighty", "assignmentMarks": 50,
                                      "attendance": 50})

    def test_boolean_is_not_accepted_as_a_number(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": True, "assignmentMarks": 50,
                                      "attendance": 50})

    def test_nan_and_infinity_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    store._validate_academic({"studentId": 1, "subject": "M",
                                              "internalMarks": value,
                                              "assignmentMarks": 50,
                                              "attendance": 50})

    def test_negative_backlog_rejected(self):
        with self.assertRaises(ValueError):
            store._validate_academic({"studentId": 1, "subject": "M",
                                      "internalMarks": 50, "assignmentMarks": 50,
                                      "attendance": 50, "backlog": -2})

    def test_invalid_student_id_rejected(self):
        for bad in (None, "", 0, -5, "abc"):
            with self.subTest(student_id=bad):
                with self.assertRaises(ValueError):
                    store._validate_academic({"studentId": bad, "subject": "M",
                                              "internalMarks": 50,
                                              "assignmentMarks": 50,
                                              "attendance": 50})


class TestInterventionApiShape(unittest.TestCase):
    def test_mapping_preserves_the_legacy_field_names(self):
        document = {
            "id": "abc", "studentId": 5, "studentName": "Sam", "type": "Tutoring",
            "reason": "low GPA", "description": "weekly", "priority": "High",
            "assignedTo": "f1", "status": "Open", "createdBy": "prof",
            "createdAt": "2026-01-01T00:00:00+00:00",
            "updatedAt": "2026-01-02T00:00:00+00:00",
        }
        api = store.to_api_intervention(document)
        for legacy_key in ("student_id", "student_name", "intervention_type",
                           "description", "status", "created_by", "created_at",
                           "updated_at"):
            self.assertIn(legacy_key, api)
        self.assertEqual(api["student_id"], 5)
        self.assertEqual(api["intervention_type"], "Tutoring")


class TestAuthBackendSelection(unittest.TestCase):
    def test_explicit_legacy_wins(self):
        with mock.patch.dict(os.environ, {"AUTH_BACKEND": "legacy"}, clear=False):
            from backend import authorization
            self.assertEqual(authorization.auth_backend(), "legacy")

    def test_explicit_firebase_wins(self):
        with mock.patch.dict(os.environ, {"AUTH_BACKEND": "firebase"}, clear=False):
            from backend import authorization
            self.assertEqual(authorization.auth_backend(), "firebase")

    def test_auto_falls_back_to_legacy_when_firebase_is_unconfigured(self):
        with mock.patch.dict(os.environ, {"AUTH_BACKEND": "auto"}, clear=False), \
                mock.patch.object(fb, "is_configured", lambda: False):
            from backend import authorization
            self.assertEqual(authorization.auth_backend(), "legacy")

    def test_auto_selects_firebase_when_configured(self):
        with mock.patch.dict(os.environ, {"AUTH_BACKEND": "auto"}, clear=False), \
                mock.patch.object(fb, "is_configured", lambda: True):
            from backend import authorization
            self.assertEqual(authorization.auth_backend(), "firebase")

    def test_package_absence_is_reported_not_raised(self):
        diagnostics = fb.diagnostics()
        self.assertIn("package_installed", diagnostics)
        self.assertIn("configured", diagnostics)


class TestSecretsHygiene(unittest.TestCase):
    def test_diagnostics_never_include_credentials(self):
        with mock.patch.dict(os.environ, {
            "FIREBASE_SERVICE_ACCOUNT_JSON": '{"private_key": "SUPERSECRET"}',
            "FIREBASE_PROJECT_ID": "proj",
        }, clear=False):
            payload = repr(fb.diagnostics())
            self.assertNotIn("SUPERSECRET", payload)
            self.assertNotIn("private_key", payload)

    def test_web_config_omits_storage_bucket(self):
        config = fb.web_config()
        self.assertNotIn("storageBucket", config)
        self.assertNotIn("measurementId", config)

    @staticmethod
    def _strip_comments(source: str) -> str:
        """Remove comments so documentation may legitimately name the banned APIs."""
        import re

        without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        return re.sub(r"//[^\n]*", "", without_block)

    def test_no_firebase_storage_api_is_used_in_frontend(self):
        """Firebase Storage must not be imported or called in executable code."""
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        forbidden = ("getStorage", "uploadBytes", "getDownloadURL(",
                     "firebase-storage", "uploadBytesResumable", "firebase/storage")
        checked = 0
        for path in (root / "frontend" / "js").glob("*.js"):
            code = self._strip_comments(path.read_text(encoding="utf-8"))
            checked += 1
            for token in forbidden:
                self.assertNotIn(token, code,
                                 f"{path.name} calls Firebase Storage ({token})")
        self.assertGreater(checked, 0, "no frontend JS files were checked")


if __name__ == "__main__":
    unittest.main()
