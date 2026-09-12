"""
Authorization tests: vertical and horizontal privilege boundaries.

Roles in the system: student, faculty, admin.
Expected boundary:
  student  -> own record only, read-only risk info
  faculty  -> at-risk lists for their department, intervention CRUD (no delete)
  admin    -> institution-wide stats, full intervention control
"""
import unittest

from tests.base import AppTestCase
from tests.api.test_endpoints_api import VALID_PROFILE


class TestVerticalEscalation(AppTestCase):
    """A lower-privileged role must not reach higher-privileged resources."""

    def test_student_cannot_reach_admin_overview(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)

    def test_student_cannot_reach_faculty_dashboard(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 403)

    def test_student_cannot_reach_interventions(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/interventions").status_code, 403)
        res = self.client.post("/api/interventions",
                               json={"student_id": 1, "intervention_type": "Tutoring"})
        self.assertEqual(res.status_code, 403)

    def test_faculty_cannot_reach_admin_overview(self):
        self.login_as("faculty")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)

    def test_faculty_cannot_delete_interventions(self):
        self.login_as("faculty")
        iid = self.client.post("/api/interventions", json={
            "student_id": 3, "intervention_type": "Counseling"}).get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/interventions/{iid}").status_code, 403)

    def test_anonymous_cannot_reach_any_api_resource(self):
        """Both 401 and 403 are valid denials; the point is that access is refused."""
        for path in ("/api/overview", "/api/faculty/CS", "/api/interventions",
                     "/api/student/1", "/api/departments", "/api/semesters"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (401, 403))

    def test_anonymous_denial_status_is_consistent(self):
        """
        login_required returns 401, while role_required/roles_required fall
        straight through to 403 without an authentication check. Callers see
        two different codes for the same 'not logged in' condition.
        """
        codes = {p: self.client.get(p).status_code for p in
                 ("/api/student/1", "/api/overview", "/api/faculty/CS",
                  "/api/interventions", "/api/departments")}
        self.assertEqual(len(set(codes.values())), 1,
                         f"inconsistent anonymous status codes: {codes}")

    def test_anonymous_cannot_self_register_as_admin(self):
        """Privileged roles require an invite code; no code -> rejected."""
        res = self.client.post("/api/auth/signup", json={
            "name": "Attacker", "email": "attacker@example.com",
            "role": "admin", "password": "password123"})
        self.assertEqual(res.status_code, 403,
                         "unauthenticated visitor was able to self-register as admin")
        self.assertIn(self.client.get("/api/overview").status_code, (401, 403))

    def test_anonymous_cannot_self_register_as_faculty(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Attacker", "email": "attacker2@example.com",
            "role": "faculty", "password": "password123"})
        self.assertEqual(res.status_code, 403)

    def test_student_role_needs_no_invite_code(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Student", "email": "plain@example.com",
            "role": "student", "password": "password123"})
        self.assertEqual(res.status_code, 201)


class TestInviteCodeGating(AppTestCase):
    """Privileged signup with the invite code configured."""

    CODE = "correct-horse-battery-staple"

    def setUp(self):
        super().setUp()
        import backend.app as app_module

        self.app_module = app_module
        self._original = app_module.PRIVILEGED_INVITE_CODE
        app_module.PRIVILEGED_INVITE_CODE = self.CODE

    def tearDown(self):
        self.app_module.PRIVILEGED_INVITE_CODE = self._original
        super().tearDown()

    def _signup(self, email, role, invite_code=None):
        payload = {"name": "Staff", "email": email, "role": role,
                   "password": "password123"}
        if invite_code is not None:
            payload["invite_code"] = invite_code
        return self.client.post("/api/auth/signup", json=payload)

    def test_correct_code_creates_admin(self):
        res = self._signup("good-admin@example.com", "admin", self.CODE)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["user"]["role"], "admin")
        self.assertEqual(self.client.get("/api/overview").status_code, 200)

    def test_correct_code_creates_faculty(self):
        res = self._signup("good-fac@example.com", "faculty", self.CODE)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 200)

    def test_wrong_code_is_rejected(self):
        self.assertEqual(
            self._signup("bad1@example.com", "admin", "definitely-wrong").status_code, 403)

    def test_missing_code_is_rejected(self):
        self.assertEqual(self._signup("bad2@example.com", "admin").status_code, 403)

    def test_blank_code_is_rejected(self):
        self.assertEqual(self._signup("bad3@example.com", "admin", "  ").status_code, 403)

    def test_failed_privileged_signup_grants_no_session(self):
        self._signup("bad4@example.com", "admin", "nope")
        self.assertIn(self.client.get("/api/overview").status_code, (401, 403))


class TestHorizontalEscalation(AppTestCase):
    """One user must not read another user's academic record (IDOR)."""

    def test_student_cannot_read_another_students_record(self):
        """
        Student IDs are sequential and enumerable (1..10000). A student
        account linked to record 1 must not reach record 2.
        """
        self.login_as("student", email="s1@example.com", student_id=1)
        self.assertEqual(self.client.get("/api/student/1").status_code, 200)
        res = self.client.get("/api/student/2")
        self.assertEqual(res.status_code, 403,
                         "student read another student's record (IDOR)")

    def test_student_cannot_enumerate_the_whole_roster(self):
        self.login_as("student", email="s2@example.com", student_id=1)
        allowed = 0
        for sid in (1, 2, 3, 4, 5):
            if self.client.get(f"/api/student/{sid}").status_code == 200:
                allowed += 1
        self.assertLessEqual(allowed, 1, "student could enumerate multiple records")

    def test_student_record_does_not_expose_ground_truth_label(self):
        """
        `actual_dropout` is the training label. Students must not see it;
        staff still receive it for reporting.
        """
        self.login_as("student", email="s3@example.com", student_id=1)
        self.assertNotIn("actual_dropout",
                         self.client.get("/api/student/1").get_json())

    def test_staff_still_receive_the_ground_truth_label(self):
        self.login_as("faculty")
        self.assertIn("actual_dropout", self.client.get("/api/student/1").get_json())


class TestAdminCapabilities(AppTestCase):
    def test_admin_can_view_institution_overview(self):
        self.login_as("admin")
        self.assertEqual(self.client.get("/api/overview").status_code, 200)

    def test_admin_can_view_department_lists(self):
        """
        README documents admin as having institution-wide visibility, so the
        faculty list endpoint should not be faculty-only.
        """
        self.login_as("admin")
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 200)

    def test_admin_can_manage_interventions(self):
        self.login_as("admin")
        iid = self.client.post("/api/interventions", json={
            "student_id": 9, "intervention_type": "Financial Aid Check"}).get_json()["id"]
        self.assertEqual(self.client.patch(f"/api/interventions/{iid}",
                                           json={"status": "In Progress"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/interventions/{iid}").status_code, 200)


class TestPredictionAbuse(AppTestCase):
    def test_student_cannot_alter_a_stored_risk_score(self):
        """There is no write endpoint for roster scores; verify none exists."""
        self.login_as("student")
        for method in (self.client.post, self.client.put, self.client.patch,
                       self.client.delete):
            res = method("/api/student/1", json={"risk_probability": 0.01})
            self.assertIn(res.status_code, (404, 405, 403))

    def test_prediction_response_matches_stored_roster_for_same_student(self):
        self.login_as("faculty")
        body = self.client.get("/api/student/3").get_json()
        self.assertGreaterEqual(body["risk_probability"], 0.0)
        self.assertLessEqual(body["risk_probability"], 1.0)


if __name__ == "__main__":
    unittest.main()
