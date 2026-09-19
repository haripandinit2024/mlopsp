"""Authorization under Firebase: roles, student isolation, prediction writes."""
import unittest

from tests.firebase.fakes import FirebaseTestCase
from tests.api.test_endpoints_api import VALID_PROFILE


def grant_invite_code(test_case, code="test-invite"):
    import backend.app as app_module

    test_case.app_module = app_module
    test_case._original_code = app_module.PRIVILEGED_INVITE_CODE
    app_module.PRIVILEGED_INVITE_CODE = code
    return code


def release_invite_code(test_case):
    test_case.app_module.PRIVILEGED_INVITE_CODE = test_case._original_code


class TestRoleEnforcement(FirebaseTestCase):
    def setUp(self):
        super().setUp()
        self.code = grant_invite_code(self)

    def tearDown(self):
        release_invite_code(self)
        super().tearDown()

    def test_student_cannot_reach_admin_endpoints(self):
        self.sign_in(uid="s1", email="s1@example.com", role="student")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 403)
        self.assertEqual(self.client.get("/api/interventions").status_code, 403)
        self.assertEqual(self.client.get("/api/users/me").status_code, 200)

    def test_faculty_cannot_reach_admin_endpoints(self):
        self.sign_in(uid="f1", email="f1@example.com", role="faculty",
                     invite_code=self.code)
        self.assertEqual(self.client.get("/api/overview").status_code, 403)
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 200)

    def test_admin_can_reach_admin_endpoints(self):
        self.sign_in(uid="a1", email="a1@example.com", role="admin",
                     invite_code=self.code)
        self.assertEqual(self.client.get("/api/overview").status_code, 200)

    def test_anonymous_is_401_on_protected_api(self):
        for path in ("/api/users/me", "/api/students/me", "/api/overview",
                     "/api/faculty/CS", "/api/interventions", "/api/student/1"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_protected_page_redirects_anonymous(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


class TestStudentIsolation(FirebaseTestCase):
    """Students may browse any roster record but never see the training label."""

    def setUp(self):
        super().setUp()
        # Faculty sign-in needs the invite code in firebase mode.
        self.code = grant_invite_code(self)

    def tearDown(self):
        release_invite_code(self)
        super().tearDown()

    def test_student_can_read_any_roster_record(self):
        self.sign_in(uid="s2", email="s2@example.com", role="student", student_id=42)

        own = self.client.get("/api/students/42")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.get_json()["student"]["student_id"], 42)

        other = self.client.get("/api/students/43")
        self.assertEqual(other.status_code, 200)

        legacy = self.client.get("/api/student/43")
        self.assertEqual(legacy.status_code, 200)

    def test_student_can_enumerate_the_roster(self):
        self.sign_in(uid="s3", email="s3@example.com", role="student", student_id=1)
        allowed = sum(
            1 for sid in range(1, 8)
            if self.client.get(f"/api/students/{sid}").status_code == 200
        )
        self.assertEqual(allowed, 7)

    def test_unlinked_student_gets_a_clear_403(self):
        self.sign_in(uid="s4", email="s4@example.com", role="student")
        response = self.client.get("/api/students/me")
        self.assertEqual(response.status_code, 403)
        self.assertIn("not linked", response.get_json()["error"])

    def test_student_record_hides_the_training_label(self):
        self.sign_in(uid="s5", email="s5@example.com", role="student", student_id=1)
        body = self.client.get("/api/students/1").get_json()["student"]
        self.assertNotIn("actual_dropout", body)

    def test_staff_keep_roster_wide_read_access(self):
        self.sign_in(uid="f2", email="f2@example.com", role="faculty",
                     invite_code=self.code)
        self.assertEqual(self.client.get("/api/students/1").status_code, 200)
        self.assertEqual(self.client.get("/api/students/2").status_code, 200)

    def test_academic_reads_are_scoped(self):
        self.sign_in(uid="s6", email="s6@example.com", role="student", student_id=5)
        self.assertEqual(self.client.get("/api/students/5/academic").status_code, 200)
        self.assertEqual(self.client.get("/api/students/6/academic").status_code, 403)


class TestPredictionRecording(FirebaseTestCase):
    def setUp(self):
        super().setUp()
        self.code = grant_invite_code(self)

    def tearDown(self):
        release_invite_code(self)
        super().tearDown()

    def test_student_cannot_record_a_prediction(self):
        self.sign_in(uid="s7", email="s7@example.com", role="student")
        response = self.client.post("/api/predictions", json={
            "student_id": 1, "profile": VALID_PROFILE})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.firebase.predictions, [])

    def test_faculty_can_record_a_prediction_from_a_profile(self):
        self.sign_in(uid="f3", email="f3@example.com", role="faculty",
                     invite_code=self.code)
        payload = dict(VALID_PROFILE)
        payload["Student_ID"] = 42
        response = self.client.post("/api/predictions", json={
            "student_id": 42, "profile": payload})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["student_id"], 42)
        self.assertIn(body["risk_tier"], {"Low", "Medium", "High"})
        self.assertTrue(body["model_version"])
        self.assertEqual(len(self.firebase.predictions), 1)

    def test_recorded_prediction_captures_version_and_factors(self):
        self.sign_in(uid="f4", email="f4@example.com", role="faculty",
                     invite_code=self.code)
        payload = dict(VALID_PROFILE)
        payload["Student_ID"] = 7
        self.client.post("/api/predictions", json={"student_id": 7, "profile": payload})
        record = self.firebase.predictions[0]
        for key in ("student_id", "risk_score", "risk_level", "model_version",
                    "contributing_factors"):
            self.assertIn(key, record)
        self.assertTrue(record["model_version"], "model version was not recorded")

    def test_invalid_profile_is_rejected_before_any_write(self):
        self.sign_in(uid="f5", email="f5@example.com", role="faculty",
                     invite_code=self.code)
        bad = dict(VALID_PROFILE)
        bad["GPA"] = "not-a-number"
        response = self.client.post("/api/predictions", json={
            "student_id": 1, "profile": bad})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.firebase.predictions, [])

    def test_prediction_without_a_student_is_rejected(self):
        self.sign_in(uid="f6", email="f6@example.com", role="faculty",
                     invite_code=self.code)
        response = self.client.post("/api/predictions", json={"profile": VALID_PROFILE})
        self.assertEqual(response.status_code, 400)

    def test_student_can_read_back_their_own_prediction_history(self):
        self.sign_in(uid="f7", email="f7@example.com", role="faculty",
                     invite_code=self.code)
        payload = dict(VALID_PROFILE)
        payload["Student_ID"] = 42
        self.client.post("/api/predictions", json={"student_id": 42, "profile": payload})
        self.client.post("/api/auth/logout")

        self.sign_in(uid="s8", email="s8@example.com", role="student", student_id=42)
        response = self.client.get("/api/students/42/prediction")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["predictions"]), 1)

    def test_student_cannot_read_someone_elses_prediction_history(self):
        self.sign_in(uid="s9", email="s9@example.com", role="student", student_id=1)
        self.assertEqual(self.client.get("/api/students/2/prediction").status_code, 403)


class TestAcademicWrites(FirebaseTestCase):
    def setUp(self):
        super().setUp()
        self.code = grant_invite_code(self)

    def tearDown(self):
        release_invite_code(self)
        super().tearDown()

    def test_student_cannot_write_academic_records(self):
        self.sign_in(uid="s10", email="s10@example.com", role="student", student_id=1)
        response = self.client.post("/api/students/1/academic", json={
            "subject": "Maths", "internalMarks": 80, "assignmentMarks": 70,
            "attendance": 90})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.firebase.academic, [])

    def test_faculty_can_write_valid_academic_records(self):
        self.sign_in(uid="f8", email="f8@example.com", role="faculty",
                     invite_code=self.code)
        response = self.client.post("/api/students/1/academic", json={
            "subject": "Maths", "internalMarks": 80, "assignmentMarks": 70,
            "attendance": 90})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        self.assertEqual(len(self.firebase.academic), 1)

    def test_out_of_range_values_are_rejected(self):
        self.sign_in(uid="f9", email="f9@example.com", role="faculty",
                     invite_code=self.code)
        cases = [
            {"attendance": 120, "internalMarks": 80, "assignmentMarks": 70},
            {"attendance": -1, "internalMarks": 80, "assignmentMarks": 70},
            {"attendance": 90, "internalMarks": 101, "assignmentMarks": 70},
            {"attendance": 90, "internalMarks": -5, "assignmentMarks": 70},
        ]
        for case in cases:
            with self.subTest(case=case):
                response = self.client.post("/api/students/1/academic", json=dict(
                    case, subject="Maths"))
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.firebase.academic, [], "invalid row was persisted")

    def test_missing_subject_is_rejected(self):
        self.sign_in(uid="f10", email="f10@example.com", role="faculty",
                     invite_code=self.code)
        response = self.client.post("/api/students/1/academic", json={
            "internalMarks": 80, "assignmentMarks": 70, "attendance": 90})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
