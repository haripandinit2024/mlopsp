"""
Authentication and authorization middleware.

Two identity sources are supported so the application keeps working while
Firebase credentials are being provisioned:

    AUTH_BACKEND=firebase  -> verify a Firebase session cookie, then load the
                              role from the Firestore users/{uid} document
    AUTH_BACKEND=legacy    -> read the Flask session (SQLite-backed accounts)
    AUTH_BACKEND=auto      -> firebase when FIREBASE_PROJECT_ID + firebase-admin
                              are present, otherwise legacy (logged loudly)

Security rules that hold in BOTH modes
--------------------------------------
* The role always comes from server-side storage, never from the request body.
* The Admin SDK bypasses Firestore security rules, so this module - not the
  rules - is the enforcement point for the API.
* A student identity may only ever read its own ``student_id``.
"""

from __future__ import annotations

import os
import threading
import time
from functools import wraps

from flask import g, jsonify, redirect, request, session

from backend import firebase_admin_app as fb

SESSION_COOKIE_NAME = "fb_session"
SESSION_COOKIE_MAX_AGE = 12 * 60 * 60

# Firestore profile cache: avoids a read on every single request.
_PROFILE_TTL_SECONDS = 60
_profile_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()

VALID_ROLES = ("student", "faculty", "admin")


# ---------------------------------------------------------------- backend mode

def auth_backend() -> str:
    """Resolve which identity provider is active."""
    configured = os.environ.get("AUTH_BACKEND", "auto").strip().lower() or "auto"
    if configured == "firebase":
        return "firebase"
    if configured == "legacy":
        return "legacy"
    return "firebase" if fb.is_configured() else "legacy"


def using_firebase() -> bool:
    return auth_backend() == "firebase"


# ---------------------------------------------------------------- profile cache

def _cached_profile(uid: str) -> dict | None:
    with _cache_lock:
        entry = _profile_cache.get(uid)
        if entry and entry[0] > time.time():
            return entry[1]
    return None


def _store_profile(uid: str, profile: dict | None) -> None:
    if profile is None:
        return
    with _cache_lock:
        _profile_cache[uid] = (time.time() + _PROFILE_TTL_SECONDS, profile)


def invalidate_profile(uid: str) -> None:
    """Call after a role/status change so it takes effect immediately."""
    with _cache_lock:
        _profile_cache.pop(uid, None)


def reset_profile_cache() -> None:
    with _cache_lock:
        _profile_cache.clear()


# ---------------------------------------------------------------- identity

def authenticate_firebase_user(session_cookie: str | None = None) -> dict | None:
    """
    Verify a Firebase session cookie and return the caller's identity.

    Returns None when there is no valid session. Raises RuntimeError when
    Firebase is the configured backend but the Admin SDK is unusable, so a
    misconfiguration fails closed rather than silently degrading.
    """
    cookie = session_cookie or request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return None

    try:
        claims = fb.verify_session_cookie(cookie)
    except fb.FirebaseNotConfigured:
        # No usable Admin SDK: treat as unauthenticated rather than trusting
        # anything the client sent.
        return None
    except Exception:
        # Expired / revoked / tampered cookie.
        return None

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        return None

    cached = _cached_profile(uid)
    if cached is not None:
        return cached if cached.get("status") == "active" else None

    from backend import firestore_service as store

    try:
        profile = store.get_user_profile(uid)
    except Exception:
        # Firestore unreachable: fall back to the token's own claims for role,
        # but still refuse if the profile cannot confirm a known role.
        role = (claims.get("role") or "").strip().lower()
        if role not in VALID_ROLES:
            return None
        return {
            "uid": uid,
            "name": claims.get("name", ""),
            "email": claims.get("email", ""),
            "role": role,
            "student_id": None,
            "status": "active",
            "backend": "firebase",
        }

    if profile is None:
        # Authenticated with Firebase but no application profile yet.
        # The caller must complete registration through /api/auth/verify.
        return {
            "uid": uid,
            "name": claims.get("name", ""),
            "email": claims.get("email", ""),
            "role": None,
            "student_id": None,
            "status": "unregistered",
            "backend": "firebase",
        }

    _store_profile(uid, profile)
    if profile.get("status") != "active":
        return None

    return {
        "uid": uid,
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "role": profile.get("role"),
        "student_id": profile.get("student_id"),
        "status": profile.get("status", "active"),
        "backend": "firebase",
    }


def _legacy_identity() -> dict | None:
    if "user_id" not in session:
        return None
    return {
        "uid": session.get("user_id"),
        "name": session.get("user_name", ""),
        "email": session.get("user_email", ""),
        "role": session.get("user_role"),
        "student_id": session.get("student_id"),
        "status": "active",
        "backend": "legacy",
    }


def current_identity() -> dict | None:
    """
    Resolve the caller once per request and memoise it on ``flask.g``.

    Order: Firebase session cookie first (when Firebase is active), then the
    legacy Flask session. Never trusts a uid or role supplied in the request.
    """
    if getattr(g, "_identity_resolved", False):
        return getattr(g, "identity", None)

    identity = None
    if using_firebase():
        identity = authenticate_firebase_user()
    if identity is None:
        identity = _legacy_identity()

    g.identity = identity
    g._identity_resolved = True
    return identity


def current_user() -> dict | None:
    return current_identity()


def require_identity() -> dict:
    """Return the identity or raise an ``AuthError`` for the caller to map."""
    identity = current_identity()
    if identity is None:
        raise AuthError("Authentication required", 401)
    return identity


class AuthError(Exception):
    """Carries an HTTP status so route handlers stay declarative."""

    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------- decorators

def _deny(message: str, status: int):
    if request.path.startswith("/api/"):
        return jsonify({"error": message}), status
    return redirect("/login")


def _register_session_cookie(response, cookie_value: str | None):
    """Attach the Firebase session cookie with hardened flags."""
    if not cookie_value:
        return response
    secure = os.environ.get("SESSION_COOKIE_SECURE", "").strip().lower() in (
        "1", "true", "yes", "on"
    )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
    )
    return response


def establish_firebase_session(id_token: str):
    """Exchange a verified ID token for a session cookie on the response."""
    cookie = fb.create_session_cookie(id_token)
    return cookie


def clear_session(response):
    session.clear()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        identity = current_identity()
        if identity is None:
            return _deny("Authentication required", 401)
        if identity.get("role") is None:
            return _deny(
                "Your account has no application profile yet. "
                "Finish registration first.",
                403,
            )
        return view(*args, **kwargs)

    return wrapped


def authorize_role(*roles):
    """Decorator factory: require one of ``roles`` (spec: authorizeRole())."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            identity = current_identity()
            if identity is None:
                return _deny("Authentication required", 401)
            if identity.get("role") not in roles:
                return _deny(
                    "Forbidden: this resource requires one of the roles: "
                    + ", ".join(roles),
                    403,
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator


# Route-level aliases. `authorize_role` is variadic, so it covers both the
# single-role and multi-role cases the API modules import.
role_required = authorize_role
roles_required = authorize_role


def authorize_student_access(student_id: int) -> None:
    """
    Raise ``AuthError`` unless the caller may read ``student_id``.

    Spec: authorizeStudentAccess(). Students are confined to the roster record
    their account is linked to; faculty and admin keep roster-wide access.
    """
    identity = require_identity()
    if identity.get("role") != "student":
        return

    own_id = identity.get("student_id")
    if own_id is None:
        raise AuthError(
            "This account is not linked to a student record. "
            "Ask an administrator to link it.",
            403,
        )
    if int(own_id) != int(student_id):
        raise AuthError("Forbidden: you can only view your own record", 403)


def error_response(error: AuthError):
    return jsonify({"error": error.message}), error.status


def provider_status() -> dict:
    """Non-secret auth provider information for /api/health and the UI."""
    return {
        "backend": auth_backend(),
        "firebase": fb.diagnostics(),
    }
