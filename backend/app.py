"""
Flask Backend - Student Dropout Risk Prediction API

Authentication is provided by Firebase Authentication (verified server-side
with the Firebase Admin SDK) with the role read from Cloud Firestore. The
legacy SQLite-backed session store remains available as a fallback so the app
keeps working until Firebase credentials are provisioned - see
`backend/authorization.py` and the AUTH_BACKEND environment variable.
"""
import os
import re
import secrets
import sys
from functools import wraps
from pathlib import Path

# Load .env BEFORE any environment variable is read below.
from backend.env_loader import load_env

load_env()

from flask import Flask, jsonify, redirect, request, send_from_directory, session  # noqa: E402
from flask_cors import CORS  # noqa: E402

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import auth, authorization, firebase_admin_app as fb, interventions  # noqa: E402
from backend import firestore_service  # noqa: E402
from backend.authorization import (  # noqa: E402
    AuthError,
    authorize_student_access,
    current_identity,
    login_required,
    role_required,
    roles_required,
    using_firebase,
)
from backend.model_service import model_service  # noqa: E402
from backend.routes.analytics import analytics_bp, register_routes  # noqa: E402

app = Flask(__name__, static_folder=None)

# --------------------------------------------------------
# CORS
# --------------------------------------------------------
# Credentialed CORS with a wildcard/reflected origin lets any website issue
# authenticated requests with the visitor's session cookie and read the reply.
# The dashboard is served from the same origin, so CORS is off unless explicit
# origins are configured via ALLOWED_ORIGINS (comma separated).
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if ALLOWED_ORIGINS:
    CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)

# --------------------------------------------------------
# Session signing key
# --------------------------------------------------------
# A hardcoded fallback would let anyone who reads this file mint a valid
# "admin" session cookie. Prefer SECRET_KEY; otherwise generate a random
# per-process key so the app never runs with a publicly known secret.
_configured_secret = os.environ.get("SECRET_KEY", "").strip()
if not _configured_secret:
    _configured_secret = secrets.token_hex(32)
    print(
        "[app] WARNING: SECRET_KEY is not set. Generated a random ephemeral key; "
        "sessions will be invalidated on restart. Set SECRET_KEY in production."
    )
app.secret_key = _configured_secret


# --------------------------------------------------------
# Debug policy
# --------------------------------------------------------
def _resolve_debug() -> bool:
    """Enable the Werkzeug debugger only on a loopback bind.

    The debugger exposes source, stack frames and an interactive console that
    can execute arbitrary code, so it must never be reachable on a public
    interface even if FLASK_DEBUG is left on in the environment.
    """
    requested = (os.environ.get("FLASK_DEBUG") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    host = (os.environ.get("FLASK_HOST") or "127.0.0.1").strip()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    return requested


app.config["DEBUG"] = _resolve_debug()

# --------------------------------------------------------
# Privileged registration
# --------------------------------------------------------
# Public signup is for students. faculty/admin accounts require an invite code
# so an anonymous visitor cannot self-provision administrative access.
PRIVILEGED_ROLES = ("faculty", "admin")
PRIVILEGED_INVITE_CODE = os.environ.get("ADMIN_INVITE_CODE", "").strip()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ``MODEL_DIR`` may be relative to the project root (as in .env).
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent
_configured_model_dir = os.environ.get("MODEL_DIR", "").strip()
MODEL_DIR_PATH = (
    (PROJECT_ROOT_DIR / _configured_model_dir)
    if _configured_model_dir and not Path(_configured_model_dir).is_absolute()
    else (Path(_configured_model_dir) if _configured_model_dir else PROJECT_ROOT_DIR / "models")
)

# --------------------------------------------------------
# Request validation helpers
# --------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

REQUIRED_PREDICT_FIELDS = ("GPA", "Attendance_Rate", "Stress_Index")

# field -> (min, max); None for max means "any finite number".
PREDICT_NUMERIC_RANGES = {
    "GPA": (0.0, 4.0),
    "Semester_GPA": (0.0, 4.0),
    "CGPA": (0.0, 4.0),
    "Attendance_Rate": (0.0, 100.0),
    "Stress_Index": (0.0, 10.0),
    "Age": (10.0, 100.0),
    "Family_Income": (0.0, None),
    "Study_Hours_per_Day": (0.0, 24.0),
    "Assignment_Delay_Days": (0.0, 365.0),
    "Travel_Time_Minutes": (0.0, 1440.0),
}


def _check_privileged_signup(role, invite_code):
    """Return an error message when a privileged signup is not allowed."""
    if role not in PRIVILEGED_ROLES:
        return None
    if not PRIVILEGED_INVITE_CODE:
        return (
            "Privileged signup is disabled. Set ADMIN_INVITE_CODE and create "
            "faculty/admin accounts with the invite code."
        )
    if not invite_code or not secrets.compare_digest(
        str(invite_code).strip(), PRIVILEGED_INVITE_CODE
    ):
        return "A valid invite code is required for this role"
    return None


def validate_predict_payload(data):
    """Return an error message, or None when the payload is acceptable.

    Guards the numeric contract explicitly so malformed values are rejected
    with 400 instead of being silently scored by the fallback heuristic (or
    raising a 500 out of the fallback as it previously did).
    """
    if not isinstance(data, dict):
        return "Request body must be a JSON object"

    for field in REQUIRED_PREDICT_FIELDS:
        if field not in data:
            return f"Missing required field: {field}"

    for field, (low, high) in PREDICT_NUMERIC_RANGES.items():
        if field not in data:
            continue
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{field} must be a number"
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return f"{field} must be a finite number"
        if number < low or (high is not None and number > high):
            return f"{field} must be between {low} and {high}"

    return None

# Ensure user DB and model service are ready even when the app is started via
# `python -c "from backend.app import app; app.run(...)"` (skips create_app/main).
auth.init_db()
interventions.init_db()
model_service.load()


# --------------------------------------------------------
# Auth decorators
# --------------------------------------------------------
# Defined once in backend/authorization.py so identity resolution, the
# Firebase/legacy switch and role checks are not duplicated per endpoint.
#
#   using_firebase()      -> verify a Firebase session cookie (role from Firestore)
#   login_required        -> any authenticated, provisioned identity
#   role_required(r)      -> exactly role r
#   roles_required(*rs)   -> one of roles rs
#
# (imported at the top of this module)


@app.errorhandler(AuthError)
def handle_auth_error(error):
    """Map authorization failures raised by authorize_student_access()."""
    return jsonify({"error": error.message}), error.status


# --------------------------------------------------------
# Baseline security headers
# --------------------------------------------------------
@app.after_request
def add_security_headers(response):
    """Defensive headers for a cookie-authenticated browser app.

    script-src keeps 'unsafe-inline' because the existing templates use inline
    event handlers; the policy still blocks third-party script origins and
    framing, which are the main exfiltration vectors.
    """
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https://www.gstatic.com https://images.google.com https://*.googleusercontent.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-hashes' https://www.gstatic.com https://www.google.com https://*.google.com https://*.firebaseapp.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "connect-src 'self' https://www.gstatic.com https://*.firebaseio.com https://*.firestore.googleapis.com https://firestore.googleapis.com https://*.googleapis.com https://*.google.com https://*.firebaseapp.com; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "frame-src https://accounts.google.com https://www.google.com https://*.firebaseapp.com https://*.firebaseio.com; "
        "child-src 'self' https://accounts.google.com https://www.google.com https://*.firebaseapp.com",
    )
    return response


# Register analytics routes
register_routes(app)


# --------------------------------------------------------
# Serve frontend
# --------------------------------------------------------
@app.route("/")
def index():
    if current_identity() is None:
        return redirect("/login")
    return redirect("/dashboard")


@app.route("/login")
def login():
    if current_identity() is not None:
        return redirect("/dashboard")
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return send_from_directory(str(FRONTEND_DIR), "dashboard.html")


@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(str(FRONTEND_DIR / "css"), filename)


@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(str(FRONTEND_DIR / "js"), filename)


@app.route("/favicon.svg")
def serve_favicon():
    return send_from_directory(str(FRONTEND_DIR), "favicon.svg", mimetype="image/svg+xml")


# --------------------------------------------------------
# Auth API
# --------------------------------------------------------
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    # Firebase deployments create accounts client-side (see /api/auth/verify).
    if using_firebase():
        return jsonify({
            "error": "This deployment uses Firebase Authentication. "
                     "Create the account from the login page."
        }), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    role = (data.get("role") or "").strip().lower()
    password = data.get("password") or ""
    invite_code = data.get("invite_code")
    student_id = data.get("student_id")

    if not name or not email or not password:
        return jsonify({"error": "Name, email and password are required"}), 400
    if role not in auth.VALID_ROLES:
        return jsonify({"error": "Role must be one of: student, faculty, admin"}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    privileged_error = _check_privileged_signup(role, invite_code)
    if privileged_error:
        return jsonify({"error": privileged_error}), 403

    if role == "student" and student_id not in (None, ""):
        roster = model_service.roster
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            return jsonify({"error": "student_id must be an integer"}), 400
        known_ids = None if roster is None else set(roster["Student_ID"].tolist())
        if known_ids is not None and student_id not in known_ids:
            return jsonify({"error": f"Unknown student_id: {student_id}"}), 400
    else:
        student_id = None

    try:
        user = auth.create_user(name, email, role, password, student_id=student_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["student_id"] = user["student_id"]
    return jsonify({"message": "Account created", "user": user}), 201


@app.route("/api/auth/login", methods=["POST"])
def login_api():
    if using_firebase():
        return jsonify({
            "error": "This deployment uses Firebase Authentication. "
                     "Sign in from the login page."
        }), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    user = auth.authenticate(data.get("email", ""), data.get("password", ""))
    if user is None:
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    session["user_email"] = user["email"]
    session["user_role"] = user["role"]
    session["student_id"] = user["student_id"]
    return jsonify({"message": "Logged in", "user": user})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """Clear the server session and the Firebase session cookie."""
    identity = current_identity()
    session.clear()
    response = jsonify({"message": "Logged out"})
    response.delete_cookie(authorization.SESSION_COOKIE_NAME, path="/")
    if identity is not None:
        firestore_service.log_event(
            "auth.logout",
            actor_uid=identity.get("uid"),
            actor_role=identity.get("role"),
        )
    return response


@app.route("/api/auth/me")
def auth_me():
    identity = current_identity()
    if identity is None or identity.get("role") is None:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({
        "user": {
            "uid": identity.get("uid"),
            "id": identity.get("uid"),
            "name": identity.get("name"),
            "email": identity.get("email"),
            "role": identity.get("role"),
            "student_id": identity.get("student_id"),
        }
    })


# --------------------------------------------------------
# Firebase Authentication
# --------------------------------------------------------
def _provision_profile(uid, claims, data):
    """
    Create a Firestore profile for a first-time Firebase user.

    The role is *requested* by the client but decided here: privileged roles
    require the server-side invite code and only a student may link a roster id.
    """
    email = (claims.get("email") or "").strip().lower()
    name = (data.get("name") or claims.get("name") or email.split("@")[0]
            or "User").strip()
    role = (data.get("role") or "student").strip().lower()

    if role not in firestore_service.VALID_ROLES:
        return jsonify({
            "error": "role must be one of: " + ", ".join(firestore_service.VALID_ROLES)
        }), 400

    privileged_error = _check_privileged_signup(role, data.get("invite_code"))
    if privileged_error:
        return jsonify({"error": privileged_error}), 403

    student_id = None
    if role == "student" and data.get("student_id") not in (None, ""):
        try:
            student_id = int(data["student_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "student_id must be an integer"}), 400
        roster = model_service.roster
        known_ids = None if roster is None else set(roster["Student_ID"].tolist())
        if known_ids is not None and student_id not in known_ids:
            return jsonify({"error": f"Unknown student_id: {student_id}"}), 400

    try:
        return firestore_service.create_user_profile(
            uid, name, email, role, student_id
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "Could not create the user profile"}), 503


@app.route("/api/auth/verify", methods=["POST"])
def auth_verify():
    """
    Exchange a Firebase ID token for a server session.

    The token is verified with the Admin SDK (revocation checked), the role is
    read from Firestore, and an HttpOnly session cookie is issued. Nothing the
    client sends about identity is trusted beyond the signed token itself.
    """
    if not using_firebase():
        return jsonify({
            "error": "Firebase authentication is not enabled on this deployment"
        }), 409

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    id_token = (data.get("id_token") or "").strip()
    if not id_token:
        return jsonify({"error": "Missing required field: id_token"}), 400

    try:
        claims = fb.verify_id_token(id_token)
    except fb.FirebaseNotConfigured:
        return jsonify({"error": "Authentication service unavailable"}), 503
    except Exception:
        return jsonify({"error": "Invalid or expired authentication token"}), 401

    uid = claims.get("uid") or claims.get("sub")
    if not uid:
        return jsonify({"error": "Invalid authentication token"}), 401

    try:
        profile = firestore_service.get_user_profile(uid)
    except Exception:
        return jsonify({"error": "User directory unavailable"}), 503

    if profile is None:
        profile = _provision_profile(uid, claims, data)
        if isinstance(profile, tuple):
            # _provision_profile returned a (response, status) error tuple.
            firestore_service.log_event(
                "auth.provision", actor_uid=uid, outcome="denied"
            )
            return profile
        firestore_service.log_event(
            "auth.provision", actor_uid=uid, actor_role=profile.get("role")
        )

    if profile.get("status") != "active":
        return jsonify({"error": "This account is disabled"}), 403

    try:
        cookie = authorization.establish_firebase_session(id_token)
    except Exception:
        return jsonify({"error": "Could not establish a session"}), 503

    response = jsonify({"message": "Session established", "user": profile})
    authorization._register_session_cookie(response, cookie)
    firestore_service.log_event(
        "auth.verify", actor_uid=uid, actor_role=profile.get("role")
    )
    return response


@app.route("/api/auth/password-reset", methods=["POST"])
def auth_password_reset():
    """
    Password reset is handled entirely by Firebase.

    The browser calls `sendPasswordResetEmail()` from the Firebase JS SDK; this
    endpoint exists only to document the flow and to refuse plaintext handling.
    """
    return jsonify({
        "message": "Password reset is handled by Firebase Authentication on the client.",
        "client_call": "sendPasswordResetEmail(auth, email)",
    }), 409


# --------------------------------------------------------
# API Routes
# --------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "message": "Student Dropout Risk API is running",
        # Non-secret provider status; never includes credentials.
        "auth": authorization.provider_status(),
        "model_loaded": model_service.model is not None,
    })


@app.route("/api/student/<int:student_id>")
@login_required
def get_student(student_id):
    """Look up a student's risk score by ID.

    Students may only read the record their account is linked to; faculty and
    admin keep roster-wide access. Without this check the sequential Student_ID
    space (1..10000) is trivially enumerable by any logged-in user.
    """
    identity = current_identity()
    role = identity.get("role")
    # Raises AuthError (mapped to 403) when a student reaches outside their own
    # record. Staff keep roster-wide access.
    authorize_student_access(student_id)

    result = model_service.predict_student(student_id)
    if "error" in result:
        return jsonify(result), 404

    # The training label is ground truth; only staff may see it.
    if role == "student":
        result.pop("actual_dropout", None)

    return jsonify(result)


@app.route("/api/predict", methods=["POST"])
@login_required
def predict():
    """Predict risk for a custom student profile."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "No data provided"}), 400

    error = validate_predict_payload(data)
    if error:
        return jsonify({"error": error}), 400

    result = model_service.predict_custom(data)
    return jsonify(result)


@app.route("/api/overview")
@role_required("admin")
def overview():
    """Admin dashboard overview statistics."""
    result = model_service.get_overview()
    if "error" in result:
        return jsonify(result), 503
    return jsonify(result)


@app.route("/api/faculty/<department>")
@role_required("faculty")
def faculty_list(department):
    """Get at-risk students for a department."""
    semester = request.args.get("semester", "All")
    result = model_service.get_faculty_list(department, semester)
    return jsonify(result)


@app.route("/api/departments")
@login_required
def departments():
    """List available departments."""
    return jsonify(["CS", "Engineering", "Business", "Arts", "Science"])


@app.route("/api/semesters")
@login_required
def semesters():
    """List available semesters/years."""
    return jsonify(["Year 1", "Year 2", "Year 3", "Year 4"])


# --------------------------------------------------------
# Intervention API (faculty & admin)
# --------------------------------------------------------
@app.route("/api/interventions", methods=["GET", "POST"])
@roles_required("faculty", "admin")
def interventions_api():
    if request.method == "GET":
        student_id = request.args.get("student_id") or None
        if student_id is not None:
            try:
                student_id = int(student_id)
            except (TypeError, ValueError):
                return jsonify({"error": "student_id must be an integer"}), 400
        items = interventions.list_interventions(
            status=request.args.get("status") or None,
            student_id=student_id,
            term=request.args.get("term") or None,
        )
        return jsonify({"interventions": items})

    data = request.get_json(silent=True) or {}
    try:
        item = interventions.create(
            student_id=data.get("student_id"),
            student_name=data.get("student_name"),
            intervention_type=data.get("intervention_type"),
            description=data.get("description"),
            created_by=(current_identity() or {}).get("name", ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    firestore_service.log_event(
        "intervention.create",
        actor_uid=(current_identity() or {}).get("uid"),
        actor_role=(current_identity() or {}).get("role"),
        target=str(item.get("student_id")),
    )
    return jsonify(item), 201


@app.route("/api/interventions/<int:iid>", methods=["PATCH", "DELETE"])
@roles_required("faculty", "admin")
def intervention_item(iid):
    if request.method == "DELETE":
        identity = current_identity() or {}
        if identity.get("role") != "admin":
            return jsonify({"error": "Only admins can delete interventions"}), 403
        if not interventions.delete(iid):
            return jsonify({"error": "Intervention not found"}), 404
        return jsonify({"message": "Intervention deleted"})

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if not status:
        return jsonify({"error": "Missing required field: status"}), 400
    try:
        item = interventions.update_status(iid, status)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if item is None:
        return jsonify({"error": "Intervention not found"}), 404
    return jsonify(item)


# --------------------------------------------------------
# Profile + Firestore-backed student endpoints
# --------------------------------------------------------
def _model_version() -> str:
    """Identifier for the deployed model, recorded on every prediction."""
    explicit = os.environ.get("MODEL_VERSION", "").strip()
    if explicit:
        return explicit
    model_path = MODEL_DIR_PATH / "xgboost_dropout_model.json"
    try:
        stat = model_path.stat()
        return f"xgboost-{int(stat.st_mtime)}"
    except OSError:
        return "xgboost-unknown"


def _firestore_unavailable():
    return jsonify({"error": "The user directory is unavailable"}), 503


@app.route("/api/users/me")
@login_required
def users_me():
    """The caller's own profile. Identity always comes from the token/session."""
    identity = current_identity()
    return jsonify({
        "user": {
            "uid": identity.get("uid"),
            "id": identity.get("uid"),
            "name": identity.get("name"),
            "email": identity.get("email"),
            "role": identity.get("role"),
            "student_id": identity.get("student_id"),
        }
    })


@app.route("/api/students/me")
@login_required
def students_me():
    """The caller's own student record. Students cannot reach anyone else's."""
    identity = current_identity()
    if identity.get("role") != "student":
        return jsonify({
            "error": "Only student accounts have a personal student record. "
                     "Use /api/students/<id>."
        }), 403

    own_id = identity.get("student_id")
    if own_id is None:
        return jsonify({
            "error": "This account is not linked to a student record. "
                     "Ask an administrator to link it."
        }), 403

    result = model_service.predict_student(int(own_id))
    if "error" in result:
        return jsonify(result), 404
    return jsonify({"student": result})


@app.route("/api/students/<int:student_id>")
@login_required
def students_detail(student_id):
    """Roster record for a student. Students are scoped to their own id."""
    authorize_student_access(student_id)
    result = model_service.predict_student(student_id)
    if "error" in result:
        return jsonify(result), 404
    if (current_identity() or {}).get("role") == "student":
        result.pop("actual_dropout", None)
    return jsonify({"student": result})


@app.route("/api/students/<int:student_id>/academic", methods=["GET", "POST"])
@login_required
def students_academic(student_id):
    """Academic records from Firestore. Reads are scoped; writes are staff-only."""
    authorize_student_access(student_id)

    if request.method == "GET":
        try:
            records = firestore_service.list_academic_records(student_id)
        except firestore_service.NotConfigured:
            return _firestore_unavailable()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"records": records})

    if (current_identity() or {}).get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff may record academic data"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    payload = dict(data)
    payload["studentId"] = student_id

    try:
        record_id = firestore_service.create_academic_record(payload)
    except firestore_service.NotConfigured:
        return _firestore_unavailable()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    identity = current_identity() or {}
    firestore_service.log_event(
        "academic.create", actor_uid=identity.get("uid"),
        actor_role=identity.get("role"), target=str(student_id),
    )
    return jsonify({"message": "Academic record created", "id": record_id}), 201


@app.route("/api/students/<int:student_id>/prediction")
@login_required
def students_prediction(student_id):
    """Prediction history for a student, read from Firestore."""
    authorize_student_access(student_id)
    try:
        records = firestore_service.list_predictions(student_id)
    except firestore_service.NotConfigured:
        return _firestore_unavailable()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"predictions": records})


@app.route("/api/predictions", methods=["POST"])
@login_required
def create_prediction():
    """
    Score a student and persist the result.

    Staff only: a student must never be able to write or alter a prediction,
    and the write happens through the Admin SDK which bypasses client rules.
    """
    identity = current_identity() or {}
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff may record predictions"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    student_id = data.get("student_id")
    try:
        student_id = int(student_id) if student_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "student_id must be an integer"}), 400

    profile = data.get("profile")
    if isinstance(profile, dict):
        error = validate_predict_payload(profile)
        if error:
            return jsonify({"error": error}), 400
        result = model_service.predict_custom(profile)
        source = "model"
    elif student_id is not None:
        result = model_service.predict_student(student_id)
        if "error" in result:
            return jsonify(result), 404
        source = "roster"
    else:
        return jsonify({
            "error": "Provide either a 'profile' object or a 'student_id'"
        }), 400

    if student_id is None and isinstance(profile, dict):
        student_id = profile.get("Student_ID") or profile.get("student_id")
        try:
            student_id = int(student_id) if student_id not in (None, "") else None
        except (TypeError, ValueError):
            student_id = None

    if student_id is None:
        return jsonify({
            "error": "A prediction must be attached to a student_id"
        }), 400

    probability = float(result.get("risk_probability", 0.0))
    tier = result.get("risk_tier", "Low")
    try:
        prediction_id = firestore_service.record_prediction(
            student_id=student_id,
            risk_score=probability,
            risk_level=tier,
            predicted_class="Dropout" if tier == "High" else "No Dropout",
            model_version=_model_version(),
            contributing_factors=result.get("recommendations", []),
            user_id=identity.get("uid"),
            department=result.get("department"),
            source=source,
        )
    except firestore_service.NotConfigured:
        return _firestore_unavailable()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    firestore_service.log_event(
        "prediction.record", actor_uid=identity.get("uid"),
        actor_role=identity.get("role"), target=str(student_id),
    )
    return jsonify({
        "id": prediction_id,
        "student_id": student_id,
        "risk_probability": probability,
        "risk_tier": tier,
        "model_version": _model_version(),
        "source": source,
    }), 201


@app.route("/api/students/<int:student_id>/interventions")
@login_required
def students_interventions(student_id):
    """Interventions for one student. Scoped reads, staff-only writes."""
    authorize_student_access(student_id)
    if not using_firebase():
        try:
            items = interventions.list_interventions(student_id=student_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"interventions": items})
    try:
        items = firestore_service.list_interventions(student_id=student_id)
    except firestore_service.NotConfigured:
        return _firestore_unavailable()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"interventions": items})


# --------------------------------------------------------
# Init and run
# --------------------------------------------------------
def create_app():
    auth.init_db()
    model_service.load()
    return app


if __name__ == "__main__":
    auth.init_db()
    model_service.load()
    print("\n" + "=" * 60)
    print("  Student Dropout Risk — Web Dashboard")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 60 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
