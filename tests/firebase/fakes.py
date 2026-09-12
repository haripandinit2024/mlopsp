"""
In-memory Firebase doubles.

The Firebase code paths must be testable without a live Firebase project, so
this module swaps the Admin SDK calls and the Firestore repositories for
in-memory equivalents. It deliberately does NOT change the application logic
under test - only the transport.
"""
import unittest
from unittest import mock

from backend import authorization, firebase_admin_app as fb, firestore_service


class FakeFirebaseUnavailable(Exception):
    """Stands in for an invalid/expired token."""


class FakeFirebase:
    """Minimal stand-in for Firebase Auth + Firestore."""

    def __init__(self):
        self.users = {}          # uid -> profile document
        self.id_tokens = {}      # id_token -> claims
        self.session_cookies = {}  # cookie -> claims
        self.audit = []
        self.predictions = []
        self.academic = []
        self._token_counter = 0
        self._next_record_id = 1

    # ---- token helpers used by the tests ----

    def issue_id_token(self, uid, email, name=None, role=None):
        self._token_counter += 1
        token = f"id-token-{uid}-{self._token_counter}"
        self.id_tokens[token] = {
            "uid": uid,
            "email": email,
            "name": name or email.split("@")[0],
            "role": role,
        }
        return token

    # ---- Admin SDK stand-ins ----

    def verify_id_token(self, id_token, check_revoked=True):
        if id_token not in self.id_tokens:
            raise FakeFirebaseUnavailable("invalid or expired token")
        return dict(self.id_tokens[id_token])

    def create_session_cookie(self, id_token, expires_in=None):
        cookie = f"session-cookie::{id_token}"
        self.session_cookies[cookie] = dict(self.id_tokens[id_token])
        return cookie

    def verify_session_cookie(self, cookie, check_revoked=True):
        if cookie not in self.session_cookies:
            raise FakeFirebaseUnavailable("invalid session cookie")
        return dict(self.session_cookies[cookie])

    def is_configured(self):
        return True

    # ---- Firestore stand-ins ----

    def get_user_profile(self, uid):
        # Must mirror the real service, which maps the Firestore document back
        # to the snake_case API shape before returning it.
        profile = self.users.get(uid)
        return firestore_service.to_api_user(profile) if profile else None

    def create_user_profile(self, uid, name, email, role, student_id=None):
        document = firestore_service.user_document(uid, name, email, role, student_id)
        self.users[uid] = document
        return firestore_service.to_api_user(document)

    def update_user_profile(self, uid, **fields):
        profile = self.users.setdefault(uid, {"uid": uid, "role": "student"})
        profile.update({k: v for k, v in fields.items() if k in {"name", "status"}})
        return firestore_service.to_api_user(profile)

    def record_prediction(self, **kwargs):
        record_id = f"pred-{self._next_record_id}"
        self._next_record_id += 1
        self.predictions.append(dict(kwargs, id=record_id))
        return record_id

    def list_predictions(self, student_id, limit=50):
        return [p for p in self.predictions if p.get("student_id") == student_id][:limit]

    def create_academic_record(self, payload):
        document = firestore_service._validate_academic(payload)
        record_id = f"acad-{self._next_record_id}"
        self._next_record_id += 1
        document["id"] = record_id
        self.academic.append(document)
        return record_id

    def list_academic_records(self, student_id, limit=100):
        return [r for r in self.academic if r.get("studentId") == student_id][:limit]

    def log_event(self, action, **kwargs):
        self.audit.append(dict(kwargs, action=action))

    # ---- patch context ----

    def patches(self):
        """Patch targets so the app talks to this fake instead of Firebase."""
        return [
            mock.patch.object(fb, "is_configured", self.is_configured),
            mock.patch.object(fb, "verify_id_token", self.verify_id_token),
            mock.patch.object(fb, "create_session_cookie", self.create_session_cookie),
            mock.patch.object(fb, "verify_session_cookie", self.verify_session_cookie),
            mock.patch.object(firestore_service, "get_user_profile", self.get_user_profile),
            mock.patch.object(firestore_service, "create_user_profile", self.create_user_profile),
            mock.patch.object(firestore_service, "update_user_profile", self.update_user_profile),
            mock.patch.object(firestore_service, "record_prediction", self.record_prediction),
            mock.patch.object(firestore_service, "list_predictions", self.list_predictions),
            mock.patch.object(firestore_service, "create_academic_record", self.create_academic_record),
            mock.patch.object(firestore_service, "list_academic_records", self.list_academic_records),
            mock.patch.object(firestore_service, "log_event", self.log_event),
            mock.patch.object(fb, "diagnostics", lambda: {
                "package_installed": True, "configured": True,
                "project_id": "test-project", "credential_source": "fake",
            }),
        ]


class FirebaseTestCase(unittest.TestCase):
    """
    Base class that runs the application against the Firebase fake.

    Sets AUTH_BACKEND=firebase so the Firebase code path is exercised even
    though no real credentials exist.
    """

    def setUp(self):
        import os

        from backend.app import app

        self.firebase = FakeFirebase()
        self._env = os.environ.get("AUTH_BACKEND")
        os.environ["AUTH_BACKEND"] = "firebase"

        self._patchers = self.firebase.patches()
        for patcher in self._patchers:
            patcher.start()
        authorization.reset_profile_cache()

        app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        import os

        for patcher in self._patchers:
            patcher.stop()
        if self._env is None:
            os.environ.pop("AUTH_BACKEND", None)
        else:
            os.environ["AUTH_BACKEND"] = self._env
        authorization.reset_profile_cache()

    # ---- helpers ----

    def sign_in(self, uid="uid-1", email="student@example.com", name="Test User",
                role="student", student_id=None, invite_code=None):
        """
        Full browser-like sign-in: get an ID token, exchange it for a session.
        Returns the /api/auth/verify response.
        """
        token = self.firebase.issue_id_token(uid, email, name, role)
        payload = {"id_token": token, "name": name, "role": role}
        if student_id is not None:
            payload["student_id"] = student_id
        if invite_code is not None:
            payload["invite_code"] = invite_code
        return self.client.post("/api/auth/verify", json=payload)
