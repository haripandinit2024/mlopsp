"""API tests: authentication endpoints (signup / login / logout / me)."""
import unittest

from tests.base import AppTestCase, DEFAULT_PASSWORD
from backend import auth


class TestHealth(AppTestCase):
    def test_health_is_public(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ok")


class TestSignup(AppTestCase):
    def test_successful_signup_creates_account_and_session(self):
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "New Student", "email": "new@example.com",
                  "role": "student", "password": DEFAULT_PASSWORD},
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["user"]["role"], "student")
        self.assertNotIn("password_hash", res.get_json()["user"])
        # Session established
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_missing_fields_rejected(self):
        res = self.client.post("/api/auth/signup", json={"email": "x@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_blank_name_rejected(self):
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "   ", "email": "blank@example.com",
                  "role": "student", "password": DEFAULT_PASSWORD},
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_role_rejected(self):
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "X", "email": "r@example.com",
                  "role": "superuser", "password": DEFAULT_PASSWORD},
        )
        self.assertEqual(res.status_code, 400)

    def test_short_password_rejected(self):
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "X", "email": "short@example.com",
                  "role": "student", "password": "1234567"},
        )
        self.assertEqual(res.status_code, 400)

    def test_duplicate_email_rejected(self):
        payload = {"name": "X", "email": "dup@example.com",
                   "role": "student", "password": DEFAULT_PASSWORD}
        self.assertEqual(self.client.post("/api/auth/signup", json=payload).status_code, 201)
        res = self.client.post("/api/auth/signup", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_malformed_email_is_rejected(self):
        """Requirement: validate email format. Currently any string is accepted."""
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "X", "email": "not-an-email",
                  "role": "student", "password": DEFAULT_PASSWORD},
        )
        self.assertEqual(res.status_code, 400)

    def test_password_not_echoed_in_response(self):
        res = self.client.post(
            "/api/auth/signup",
            json={"name": "X", "email": "echo@example.com",
                  "role": "student", "password": "MySecretPass9"},
        )
        self.assertNotIn("MySecretPass9", res.get_data(as_text=True))

    def test_signup_rejects_non_object_json_body(self):
        """A JSON string body must not produce a 500."""
        res = self.client.post(
            "/api/auth/signup", data='"just-a-string"', content_type="application/json"
        )
        self.assertLess(res.status_code, 500)

    def test_student_signup_with_valid_student_id_links_account(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Linked", "email": "linked-student@example.com",
            "role": "student", "password": DEFAULT_PASSWORD, "student_id": 1})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["user"]["student_id"], 1)
        self.assertEqual(self.client.get("/api/student/1").status_code, 200)

    def test_student_signup_with_unknown_student_id_rejected(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Ghost", "email": "ghost@example.com",
            "role": "student", "password": DEFAULT_PASSWORD, "student_id": 999999})
        self.assertEqual(res.status_code, 400)

    def test_student_signup_with_non_numeric_student_id_rejected(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Bad", "email": "bad-id@example.com",
            "role": "student", "password": DEFAULT_PASSWORD, "student_id": "abc"})
        self.assertEqual(res.status_code, 400)

    def test_email_is_normalised_before_storage(self):
        res = self.client.post("/api/auth/signup", json={
            "name": "Case", "email": "  MiXeD@Example.COM  ",
            "role": "student", "password": DEFAULT_PASSWORD})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["user"]["email"], "mixed@example.com")
        self.assertEqual(self.login("mixed@example.com").status_code, 200)


class TestLogin(AppTestCase):
    def setUp(self):
        super().setUp()
        self.make_user("faculty", "login@example.com")

    def test_valid_login(self):
        res = self.login("login@example.com")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["user"]["role"], "faculty")

    def test_wrong_password_rejected(self):
        res = self.login("login@example.com", "wrong-password")
        self.assertEqual(res.status_code, 401)

    def test_unknown_account_rejected(self):
        res = self.login("ghost@example.com")
        self.assertEqual(res.status_code, 401)

    def test_error_message_does_not_reveal_account_existence(self):
        """Same message for unknown account and wrong password."""
        unknown = self.login("ghost@example.com").get_json()["error"]
        wrong = self.login("login@example.com", "nope").get_json()["error"]
        self.assertEqual(unknown, wrong)

    def test_empty_credentials_rejected(self):
        res = self.client.post("/api/auth/login", json={"email": "", "password": ""})
        self.assertEqual(res.status_code, 401)

    def test_missing_json_body_is_a_client_error(self):
        """A request without a JSON object body is malformed -> 400 (not 401)."""
        res = self.client.post("/api/auth/login")
        self.assertEqual(res.status_code, 400)

    def test_sql_injection_attempt_does_not_authenticate(self):
        self.make_user("admin", "victim@example.com")
        for payload in ["' OR '1'='1", "victim@example.com' --", '" OR 1=1 --']:
            res = self.client.post(
                "/api/auth/login", json={"email": payload, "password": payload}
            )
            self.assertEqual(res.status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_does_not_log_or_return_password(self):
        res = self.login("login@example.com")
        self.assertNotIn(DEFAULT_PASSWORD, res.get_data(as_text=True))


class TestSessionLifecycle(AppTestCase):
    def test_me_requires_session(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_logout_clears_session(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.logout()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_logout_is_idempotent(self):
        self.assertEqual(self.logout().status_code, 200)
        self.assertEqual(self.logout().status_code, 200)

    def test_tampered_session_cookie_is_rejected(self):
        self.login_as("admin")
        cookie = self.client.get_cookie("session")
        value = cookie.value
        # Flip a character in the signature segment.
        head, _, sig = value.rpartition(".")
        tampered = f"{head}.{'A' if sig[:1] != 'A' else 'B'}{sig[1:]}"
        self.client.set_cookie("session", tampered)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


class TestProtectedPages(AppTestCase):
    def test_root_redirects_anonymous_to_login(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    def test_dashboard_redirects_anonymous_to_login(self):
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers["Location"])

    def test_dashboard_served_when_authenticated(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_login_page_is_public(self):
        self.assertEqual(self.client.get("/login").status_code, 200)


if __name__ == "__main__":
    unittest.main()
