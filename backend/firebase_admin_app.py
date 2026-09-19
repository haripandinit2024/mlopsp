"""
Firebase Admin SDK integration (Authentication + Cloud Firestore only).

Deliberately NOT initialised:
  * Firebase Storage / Cloud Storage
  * Realtime Database

Credentials are resolved in this order and are never logged:

  1. ``FIREBASE_SERVICE_ACCOUNT_JSON``  - the service-account JSON inline
  2. ``FIREBASE_SERVICE_ACCOUNT_FILE``  - path to the JSON file
  3. Application Default Credentials    - ``GOOGLE_APPLICATION_CREDENTIALS``
                                          or the ambient metadata server

Every entry point imports ``firebase_admin`` lazily so that the rest of the
application (and the test suite) still imports cleanly when the package is
absent. Callers must check :func:`is_configured` or be prepared to catch
:class:`FirebaseNotConfigured`.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Optional

# --- session cookie lifetime -------------------------------------------------
# Firebase allows 5 minutes .. 14 days.
MIN_SESSION_SECONDS = 5 * 60
MAX_SESSION_SECONDS = 14 * 24 * 60 * 60


class FirebaseNotConfigured(RuntimeError):
    """Raised when a Firebase operation is attempted without configuration."""


_lock = threading.Lock()
_app: Any = None
_initialised = False
_import_error: Optional[str] = None


def package_available() -> bool:
    """True when the `firebase-admin` package can be imported."""
    try:
        import firebase_admin  # noqa: F401
    except ImportError as exc:
        global _import_error
        _import_error = str(exc)
        return False
    return True


def _service_account_certificate() -> Optional[dict]:
    """Return a credentials dict, or None to fall back to ADC."""
    inline = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if inline:
        try:
            return json.loads(inline)
        except json.JSONDecodeError as exc:
            raise FirebaseNotConfigured(
                "FIREBASE_SERVICE_ACCOUNT_JSON is set but is not valid JSON"
            ) from exc

    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", "").strip()
    if path:
        if not os.path.exists(path):
            raise FirebaseNotConfigured(
                f"FIREBASE_SERVICE_ACCOUNT_FILE points to a missing file: {path}"
            )
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    return None


def web_config() -> dict:
    """
    The PUBLIC Firebase web configuration shipped to the browser.

    These values are not secrets - they identify the project and are protected
    by Firebase's own API-key restrictions plus Firestore security rules.
    ``storageBucket`` is intentionally omitted: Firebase Storage is not used.
    """
    return {
        "apiKey": os.environ.get("FIREBASE_API_KEY", "").strip(),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", "").strip(),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", "").strip(),
        "appId": os.environ.get("FIREBASE_APP_ID", "").strip(),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "").strip(),
    }


def is_configured() -> bool:
    """
    True when Firebase is the intended auth backend.

    Requires the package plus a project id. Credential *validity* is not
    checked here (that needs a network round-trip); a bad/missing credential
    surfaces as a clear error at first use rather than as a silent downgrade
    to the legacy auth store, which would be a security surprise.
    """
    if not package_available():
        return False
    return bool(os.environ.get("FIREBASE_PROJECT_ID", "").strip())


def get_app():
    """Initialise (once) and return the Firebase app."""
    global _app, _initialised

    if _initialised and _app is not None:
        return _app

    with _lock:
        if _initialised and _app is not None:
            return _app

        if not package_available():
            raise FirebaseNotConfigured(
                "firebase-admin is not installed. Run: pip install firebase-admin"
            )

        import firebase_admin
        from firebase_admin import credentials

        project_id = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
        options = {"projectId": project_id} if project_id else None

        try:
            _app = firebase_admin.get_app()
        except ValueError:
            certificate = _service_account_certificate()
            if certificate is not None:
                _app = firebase_admin.initialize_app(
                    credentials.Certificate(certificate), options
                )
            else:
                # Application Default Credentials.
                _app = firebase_admin.initialize_app(
                    credentials.ApplicationDefault(), options
                )

        _initialised = True
        return _app


def get_auth():
    get_app()
    from firebase_admin import auth

    return auth


def get_firestore():
    """Cloud Firestore client. Never touches Storage or Realtime Database."""
    get_app()
    from firebase_admin import firestore

    return firestore.client()


def _session_expires_in() -> int:
    raw = os.environ.get("FIREBASE_SESSION_EXPIRES_IN", "").strip()
    try:
        value = int(raw) if raw else 12 * 60 * 60
    except ValueError:
        value = 12 * 60 * 60
    return max(MIN_SESSION_SECONDS, min(MAX_SESSION_SECONDS, value))


# ---------------------------------------------------------------- token flow

def verify_id_token(id_token: str) -> dict:
    """
    Verify a Firebase ID token server-side.

    ``check_revoked=True`` also rejects tokens whose user has been disabled or
    signed out, which is what makes account suspension effective immediately.

    ``clock_skew_seconds=60`` absorbs up to a minute of drift between the
    issuing Google server and this host; without it, a Google sign-in minted
    earlier by a few seconds fails with "Token used too early".
    """
    if not id_token:
        raise FirebaseNotConfigured("No ID token supplied")
    auth = get_auth()
    return auth.verify_id_token(
        id_token, check_revoked=True, clock_skew_seconds=60
    )


def create_session_cookie(id_token: str, expires_in: Optional[int] = None) -> str:
    """Exchange a freshly-verified ID token for a long-lived session cookie."""
    auth = get_auth()
    return auth.create_session_cookie(
        id_token, expires_in=expires_in or _session_expires_in()
    )


def verify_session_cookie(session_cookie: str) -> dict:
    """Verify a Firebase session cookie. Returns the decoded claims."""
    if not session_cookie:
        raise FirebaseNotConfigured("No session cookie supplied")
    auth = get_auth()
    return auth.verify_session_cookie(
        session_cookie, check_revoked=True, clock_skew_seconds=60
    )


def revoke_refresh_tokens(uid: str) -> None:
    """Invalidate every existing session/token for a user (logout everywhere)."""
    get_auth().revoke_refresh_tokens(uid)


def set_user_disabled(uid: str, disabled: bool) -> None:
    get_auth().update_user(uid, disabled=disabled)


def session_cookie_expires_in() -> int:
    return _session_expires_in()


def diagnostics() -> dict:
    """Non-secret status information for /api/health and the startup log."""
    return {
        "package_installed": package_available(),
        "package_error": _import_error,
        "configured": is_configured(),
        "project_id": os.environ.get("FIREBASE_PROJECT_ID", "").strip() or None,
        "credential_source": (
            "service_account_json"
            if os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
            else "service_account_file"
            if os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE", "").strip()
            else "application_default"
        ),
    }
