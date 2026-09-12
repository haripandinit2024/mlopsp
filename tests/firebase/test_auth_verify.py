"""POST /api/auth/verify — token verification, provisioning, session issuance."""
import unittest

from tests.firebase.fakes import FirebaseTestCase


class TestVerifyHappyPath(FirebaseTestCase):
    def test_valid_token_creates_profile_and_session(self):
        response = self.sign_in(uid="uid-100", email="new@example.com",
                               name="New Student", role="student")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["user"]["role"], "student")
        self.assertEqual(body["user"]["uid"], "uid-100")
        self.assertEqual(body["user"]["email"], "new@example.com")
        # A profile now exists in the (fake) Firestore.
        self.assertIn("uid-100", self.firebase.users)
        # And an audit record was written.
        self.assertTrue(any(e["action"] == "auth.provision" for e in self.firebase.audit))

    def test_session_cookie_is_issued_httponly(self):
        response = self.sign_in(uid="uid-101", email="cookie@example.com")
        raw = " ".join(response.headers.getlist("Set-Cookie"))
        self.assertIn("fb_session=", raw, "no Firebase session cookie was set")
        self.assertIn("HttpOnly", raw)
        self.assertIn("SameSite=Lax", raw)
        # Secure must not be set unconditionally, otherwise the cookie is
        # dropped on plain-HTTP local development.
        self.assertNotIn("Secure", raw)

    def test_second_verify_reuses_existing_profile(self):
        self.sign_in(uid="uid-102", email="repeat@example.com", role="student")
        provisions_before = sum(
            1 for e in self.firebase.audit if e["action"] == "auth.provision"
        )
        token = self.firebase.issue_id_token("uid-102", "repeat@example.com", role="student")
        response = self.client.post("/api/auth/verify", json={"id_token": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.firebase.users), 1, "profile was recreated")
        provisions_after = sum(
            1 for e in self.firebase.audit if e["action"] == "auth.provision"
        )
        self.assertEqual(provisions_after, provisions_before,
                         "an existing profile was provisioned again")

    def test_me_returns_the_verified_identity(self):
        self.sign_in(uid="uid-103", email="me@example.com", name="Me", role="student")
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        user = response.get_json()["user"]
        self.assertEqual(user["uid"], "uid-103")
        self.assertEqual(user["name"], "Me")


class TestVerifyRejections(FirebaseTestCase):
    def test_missing_token_is_rejected(self):
        response = self.client.post("/api/auth/verify", json={})
        self.assertEqual(response.status_code, 400)

    def test_blank_token_is_rejected(self):
        response = self.client.post("/api/auth/verify", json={"id_token": "   "})
        self.assertEqual(response.status_code, 400)

    def test_invalid_token_is_401(self):
        response = self.client.post("/api/auth/verify", json={"id_token": "not-a-real-token"})
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(self.client.get_cookie("fb_session"))

    def test_forged_session_cookie_is_rejected(self):
        self.client.set_cookie("fb_session", "forged-cookie-value")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_non_object_body_is_rejected(self):
        response = self.client.post("/api/auth/verify", data='"nope"',
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_invalid_role_is_rejected(self):
        token = self.firebase.issue_id_token("uid-110", "role@example.com")
        response = self.client.post("/api/auth/verify", json={
            "id_token": token, "role": "superuser"})
        self.assertEqual(response.status_code, 400)

    def test_error_responses_never_leak_internals(self):
        response = self.client.post("/api/auth/verify", json={"id_token": "bad"})
        text = response.get_data(as_text=True)
        for leak in ("Traceback", "firebase_admin", "service_account", "private_key"):
            self.assertNotIn(leak, text)


class TestPrivilegedRoleProvisioning(FirebaseTestCase):
    """The client may REQUEST a role; only the server decides it."""

    def setUp(self):
        super().setUp()
        import backend.app as app_module

        self.app_module = app_module
        self._original_code = app_module.PRIVILEGED_INVITE_CODE
        app_module.PRIVILEGED_INVITE_CODE = "valid-invite-code"

    def tearDown(self):
        self.app_module.PRIVILEGED_INVITE_CODE = self._original_code
        super().tearDown()

    def test_admin_without_invite_code_is_denied(self):
        token = self.firebase.issue_id_token("uid-120", "atk@example.com")
        response = self.client.post("/api/auth/verify", json={
            "id_token": token, "role": "admin"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.firebase.users, {}, "profile was created anyway")
        self.assertIsNone(self.client.get_cookie("fb_session"))

    def test_admin_with_correct_invite_code_succeeds(self):
        token = self.firebase.issue_id_token("uid-121", "real-admin@example.com")
        response = self.client.post("/api/auth/verify", json={
            "id_token": token, "role": "admin", "invite_code": "valid-invite-code"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "admin")
        self.assertEqual(self.client.get("/api/overview").status_code, 200)

    def test_faculty_with_wrong_invite_code_is_denied(self):
        token = self.firebase.issue_id_token("uid-122", "f@example.com")
        response = self.client.post("/api/auth/verify", json={
            "id_token": token, "role": "faculty", "invite_code": "wrong"})
        self.assertEqual(response.status_code, 403)

    def test_role_from_token_claim_is_not_trusted(self):
        """A token claiming admin must not grant admin without the invite code."""
        token = self.firebase.issue_id_token("uid-123", "sneaky@example.com", role="admin")
        response = self.client.post("/api/auth/verify", json={
            "id_token": token, "role": "student"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "student")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)


class TestStudentLinking(FirebaseTestCase):
    def test_student_can_link_a_known_roster_id(self):
        response = self.sign_in(uid="uid-130", email="linked@example.com",
                               student_id=42)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["student_id"], 42)

    def test_unknown_roster_id_is_rejected(self):
        response = self.sign_in(uid="uid-131", email="ghost@example.com",
                               student_id=999999)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.firebase.users, {})

    def test_non_numeric_roster_id_is_rejected(self):
        response = self.sign_in(uid="uid-132", email="bad@example.com",
                               student_id="abc")
        self.assertEqual(response.status_code, 400)

    def test_staff_never_receives_a_student_link(self):
        import backend.app as app_module

        original = app_module.PRIVILEGED_INVITE_CODE
        app_module.PRIVILEGED_INVITE_CODE = "code"
        try:
            response = self.sign_in(uid="uid-133", email="staff@example.com",
                                    role="faculty", invite_code="code", student_id=7)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.get_json()["user"]["student_id"])
        finally:
            app_module.PRIVILEGED_INVITE_CODE = original


class TestDisabledAccounts(FirebaseTestCase):
    def test_disabled_account_cannot_establish_a_session(self):
        self.sign_in(uid="uid-140", email="disabled@example.com")
        self.firebase.users["uid-140"]["status"] = "suspended"
        from backend import authorization

        authorization.reset_profile_cache()
        token = self.firebase.issue_id_token("uid-140", "disabled@example.com")
        response = self.client.post("/api/auth/verify", json={"id_token": token})
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled", response.get_json()["error"].lower())


class TestLogout(FirebaseTestCase):
    def test_logout_clears_the_session(self):
        self.sign_in(uid="uid-150", email="logout@example.com")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_logout_emits_an_audit_record(self):
        self.sign_in(uid="uid-151", email="audit@example.com")
        self.client.post("/api/auth/logout")
        self.assertTrue(any(e["action"] == "auth.logout" for e in self.firebase.audit))


class TestLegacyEndpointsDisabledUnderFirebase(FirebaseTestCase):
    def test_signup_endpoint_refuses_in_firebase_mode(self):
        response = self.client.post("/api/auth/signup", json={
            "name": "X", "email": "x@example.com", "role": "student",
            "password": "password123"})
        self.assertEqual(response.status_code, 409)

    def test_login_endpoint_refuses_in_firebase_mode(self):
        response = self.client.post("/api/auth/login", json={
            "email": "x@example.com", "password": "password123"})
        self.assertEqual(response.status_code, 409)

    def test_password_reset_endpoint_does_not_handle_plaintext(self):
        response = self.client.post("/api/auth/password-reset",
                                    json={"email": "x@example.com"})
        self.assertEqual(response.status_code, 409)
        self.assertIn("client_call", response.get_json())


if __name__ == "__main__":
    unittest.main()
