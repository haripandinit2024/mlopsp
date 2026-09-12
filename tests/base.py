"""
Shared test harness.

Uses only the standard library (unittest) plus what the project already
depends on, so the suite runs in the existing venv with no new packages.

Isolation strategy: `auth` and `interventions` both read their module-level
DB_PATH inside `_connect()`, so pointing that global at a fresh temp file
per test gives us a clean database without touching backend/users.db.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import auth, interventions  # noqa: E402
from backend.app import app  # noqa: E402

DEFAULT_PASSWORD = "password123"


class AppTestCase(unittest.TestCase):
    """Base class: isolated DB + test client + helpers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="dropout_test_")
        self.db_path = Path(self.tmpdir) / "test_users.db"

        self._orig_paths = (auth.DB_PATH, interventions.DB_PATH)
        auth.DB_PATH = self.db_path
        interventions.DB_PATH = self.db_path
        auth.init_db()
        interventions.init_db()

        # Observe real HTTP status codes instead of re-raised exceptions.
        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        self.client = app.test_client()

    def tearDown(self):
        auth.DB_PATH, interventions.DB_PATH = self._orig_paths
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---------------- helpers ----------------

    def make_user(self, role="student", email=None, name=None,
                  password=DEFAULT_PASSWORD, student_id=None):
        email = email or f"{role}@example.com"
        name = name or f"Test {role.title()}"
        return auth.create_user(name, email, role, password, student_id=student_id)

    def login(self, email, password=DEFAULT_PASSWORD):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def login_as(self, role, email=None, password=DEFAULT_PASSWORD, student_id=None):
        """Create (if needed) and log in as `role`. Returns the response."""
        email = email or f"{role}@example.com"
        try:
            auth.create_user(f"Test {role.title()}", email, role, password,
                             student_id=student_id)
        except ValueError:
            pass  # already exists
        return self.login(email, password)

    def logout(self):
        return self.client.post("/api/auth/logout")

    def forged_session_cookie(self, claims):
        """
        Sign an arbitrary session payload with the app's *current* secret key.
        Used to prove whether session integrity actually protects the app.
        """
        from flask.sessions import SecureCookieSessionInterface

        serializer = SecureCookieSessionInterface().get_signing_serializer(app)
        return serializer.dumps(claims)
