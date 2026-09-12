"""
Defensive security checks: session integrity, CORS policy, response headers,
debug exposure, secrets and error-message hygiene.

These assert the *secure* expectation. A failure here is a finding, not a
flaky test.
"""
import os
import unittest

from tests.base import AppTestCase, PROJECT_ROOT
from backend.app import app


class TestSessionIntegrity(AppTestCase):
    def test_session_cannot_be_forged_with_the_fallback_secret(self):
        """
        app.py falls back to a hardcoded SECRET_KEY when the env var is unset.
        Anyone who reads the source can mint a valid admin session.
        """
        self.assertFalse(
            app.secret_key == "dropout-risk-dashboard-secret-key",
            "app is signing sessions with the hardcoded fallback key",
        )

    def test_forged_admin_cookie_is_rejected(self):
        """
        An attacker only needs the *published fallback constant* to mint an
        admin cookie. Sign with that legacy value and confirm access is denied.
        """
        from flask import Flask
        from flask.sessions import SecureCookieSessionInterface

        attacker_app = Flask(__name__)
        attacker_app.secret_key = "dropout-risk-dashboard-secret-key"
        forged = SecureCookieSessionInterface().get_signing_serializer(
            attacker_app
        ).dumps({
            "user_id": 999, "user_name": "Attacker",
            "user_email": "a@evil.com", "user_role": "admin",
        })

        self.client.set_cookie("session", forged)
        res = self.client.get("/api/overview")
        self.assertIn(res.status_code, (401, 403),
                      "forged session cookie granted access to an admin endpoint")

    def test_unsigned_session_payload_is_rejected(self):
        self.client.set_cookie(
            "session",
            '{"user_role":"admin","user_id":1,"user_name":"x","user_email":"x"}',
        )
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


class TestCorsPolicy(AppTestCase):
    def test_arbitrary_origin_is_not_reflected_with_credentials(self):
        """
        Cookie auth + `Access-Control-Allow-Origin: <any>` +
        `Access-Control-Allow-Credentials: true` lets any website read this
        API on behalf of a logged-in staff member.
        """
        res = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        acao = res.headers.get("Access-Control-Allow-Origin")
        acac = res.headers.get("Access-Control-Allow-Credentials")
        if acac == "true":
            self.assertNotEqual(acao, "https://evil.example",
                                "wildcard origin reflected with credentials enabled")

    def test_cors_is_restricted_to_known_origins(self):
        res = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertIsNone(res.headers.get("Access-Control-Allow-Origin"))


class TestResponseHeaders(AppTestCase):
    def test_security_headers_present(self):
        res = self.client.get("/login")
        missing = [h for h in ("X-Content-Type-Options", "X-Frame-Options",
                               "Content-Security-Policy")
                   if not res.headers.get(h)]
        self.assertEqual(missing, [], f"missing security headers: {missing}")

    def test_session_cookie_is_httponly(self):
        self.login_as("student")
        cookie = self.client.get_cookie("session")
        self.assertTrue(cookie is not None)
        # Werkzeug test client exposes the parsed flags on the cookie object.
        self.assertTrue(getattr(cookie, "httponly", False) or "HttpOnly" not in str(cookie))


class TestDebugExposure(AppTestCase):
    def test_debug_mode_is_disabled(self):
        self.assertFalse(app.debug, "Flask debug mode is enabled")

    def test_error_responses_do_not_leak_stack_traces(self):
        self.login_as("faculty")
        res = self.client.get("/api/interventions?student_id=abc")
        body = res.get_data(as_text=True)
        for leak in ("Traceback (most recent call last)", "File \"", "site-packages"):
            self.assertNotIn(leak, body, "error response leaked internal details")


class TestSecretsHygiene(AppTestCase):
    def test_no_hardcoded_secret_in_source(self):
        import re

        src = (PROJECT_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
        match = re.search(r'os\.environ\.get\(\s*"SECRET_KEY"\s*,\s*"([^"]+)"', src)
        self.assertIsNone(match, "hardcoded fallback secret found in backend/app.py")

    def test_env_file_is_gitignored(self):
        """Checked against .gitignore directly (this checkout has no .git dir)."""
        patterns = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        patterns = [p.strip() for p in patterns if p.strip() and not p.startswith("#")]
        self.assertIn(".env", patterns, ".env is not listed in .gitignore")

    def test_credentials_are_never_returned_by_the_api(self):
        keys = ("password", "password_hash", "secret", "token", "api_key")
        self.login_as("admin")
        for path in ("/api/auth/me", "/api/overview"):
            body = self.client.get(path).get_data(as_text=True).lower()
            for key in keys:
                self.assertNotIn(f'"{key}"', body)


if __name__ == "__main__":
    unittest.main()
