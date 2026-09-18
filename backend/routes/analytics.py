"""
Analytics and Student Profile API endpoints.

Provides endpoints for:
- Student profiles
- Academic records
- Attendance
- Assessments
- Predictions history
- Current risk
- Analytics data
- Notifications
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Blueprint, jsonify, request
from backend.authorization import (
    AuthError,
    authorize_student_access,
    current_identity,
    login_required,
    role_required,
    roles_required,
)
from backend import firestore_service
from backend.services.risk_service import get_risk_service

# Create blueprint
analytics_bp = Blueprint("analytics", __name__)

# Get risk service instance
risk_service = get_risk_service()


# ---------------------------------------------------------------- student profile endpoints


@analytics_bp.route("/api/students/<int:student_id>/profile")
@login_required
def get_student_profile(student_id):
    """Get student profile."""
    authorize_student_access(student_id)
    try:
        profile = firestore_service.get_student_profile(student_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if profile is None:
        return jsonify({"error": "Student profile not found"}), 404

    # Remove sensitive fields if student is viewing their own record
    identity = current_identity()
    if identity.get("role") == "student" and identity.get("student_id") != student_id:
        # This shouldn't happen due to authorize_student_access, but be safe
        return jsonify({"error": "Forbidden"}), 403

    return jsonify({"student": profile})


@analytics_bp.route("/api/students/<int:student_id>/profile", methods=["PUT"])
@login_required
def update_student_profile(student_id):
    """Update student profile (staff only)."""
    authorize_student_access(student_id)

    identity = current_identity()
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff can update student profiles"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        profile = firestore_service.update_student_profile(student_id, **data)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if profile is None:
        return jsonify({"error": "Student profile not found"}), 404

    firestore_service.log_event(
        "student.update",
        actor_uid=identity.get("uid"),
        actor_role=identity.get("role"),
        target=str(student_id),
    )

    return jsonify({"student": profile})


# ---------------------------------------------------------------- academic endpoints


@analytics_bp.route("/api/students/<int:student_id>/academic", methods=["GET", "POST"])
@login_required
def academic_records(student_id):
    """Get or create academic records for a student."""
    authorize_student_access(student_id)

    if request.method == "GET":
        try:
            records = firestore_service.list_academic_records(student_id)
        except firestore_service.NotConfigured:
            return jsonify({"error": "Database unavailable"}), 503
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"records": records})

    # POST - create academic record
    identity = current_identity()
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff can create academic records"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # The record belongs to the student in the URL, never to a client-supplied
    # id - otherwise a staff member could write into another student's record.
    payload = dict(data)
    payload["studentId"] = student_id

    try:
        record_id = firestore_service.create_academic_record(payload)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    firestore_service.log_event(
        "academic.create",
        actor_uid=identity.get("uid"),
        actor_role=identity.get("role"),
        target=str(student_id),
    )

    return jsonify({"message": "Academic record created", "id": record_id}), 201


@analytics_bp.route("/api/academic/<record_id>", methods=["PUT"])
@login_required
def update_academic_record(record_id):
    """Update an academic record (staff only)."""
    identity = current_identity()
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        record = firestore_service.update_academic_record(record_id, **data)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if record is None:
        return jsonify({"error": "Academic record not found"}), 404

    firestore_service.log_event(
        "academic.update",
        actor_uid=identity.get("uid"),
        actor_role=identity.get("role"),
        target=record_id,
    )

    return jsonify({"record": record})


@analytics_bp.route("/api/academic/<record_id>", methods=["DELETE"])
@role_required("admin")
def delete_academic_record(record_id):
    """Delete an academic record (admin only)."""
    # Note: Firestore_service doesn't have delete_academic_record yet
    # This would need to be implemented if needed
    return jsonify({"error": "Not implemented"}), 501


# ---------------------------------------------------------------- attendance endpoints


@analytics_bp.route("/api/students/<int:student_id>/attendance")
@login_required
def get_attendance(student_id):
    """Get attendance records for a student."""
    authorize_student_access(student_id)

    try:
        records = firestore_service.get_attendance_records(student_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"records": records})


@analytics_bp.route("/api/students/<int:student_id>/attendance", methods=["POST"])
@login_required
def create_attendance(student_id):
    """Create attendance record (staff only)."""
    authorize_student_access(student_id)

    identity = current_identity()
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff can create attendance records"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        record_id = firestore_service.create_attendance_record(
            student_id=data.get("studentId", student_id),
            subject_code=data.get("subjectCode") or data.get("subject_code"),
            subject_name=data.get("subjectName") or data.get("subject_name"),
            semester=data.get("semester"),
            classes_attended=data.get("classesAttended") or data.get("classes_attended"),
            total_classes=data.get("totalClasses") or data.get("total_classes"),
            attendance_percentage=data.get("attendancePercentage") or data.get("attendance_percentage"),
        )
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    firestore_service.log_event(
        "attendance.create",
        actor_uid=identity.get("uid"),
        actor_role=identity.get("role"),
        target=str(student_id),
    )

    return jsonify({"message": "Attendance record created", "id": record_id}), 201


# ---------------------------------------------------------------- assessment endpoints


@analytics_bp.route("/api/students/<int:student_id>/assessments")
@login_required
def get_assessments(student_id):
    """Get assessment records for a student."""
    authorize_student_access(student_id)

    try:
        records = firestore_service.get_assessment_records(student_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"records": records})


@analytics_bp.route("/api/students/<int:student_id>/assessments", methods=["POST"])
@login_required
def create_assessment(student_id):
    """Create assessment record (staff only)."""
    authorize_student_access(student_id)

    identity = current_identity()
    if identity.get("role") not in ("faculty", "admin"):
        return jsonify({"error": "Forbidden: only staff can create assessment records"}), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        record_id = firestore_service.create_assessment_record(
            student_id=data.get("studentId", student_id),
            subject_code=data.get("subjectCode") or data.get("subject_code"),
            subject_name=data.get("subjectName") or data.get("subject_name"),
            assessment_type=data.get("assessmentType") or data.get("assessment_type"),
            marks=data.get("marks"),
            max_marks=data.get("maxMarks") or data.get("max_marks"),
            semester=data.get("semester"),
            assessment_date=data.get("assessmentDate") or data.get("assessment_date"),
        )
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    firestore_service.log_event(
        "assessment.create",
        actor_uid=identity.get("uid"),
        actor_role=identity.get("role"),
        target=str(student_id),
    )

    return jsonify({"message": "Assessment record created", "id": record_id}), 201


# ---------------------------------------------------------------- prediction history endpoints


@analytics_bp.route("/api/students/<int:student_id>/predictions")
@login_required
def get_predictions(student_id):
    """Get prediction history for a student."""
    authorize_student_access(student_id)

    try:
        records = firestore_service.list_predictions(student_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"predictions": records})


@analytics_bp.route("/api/students/<int:student_id>/risk")
@login_required
def get_current_risk(student_id):
    """Get current/latest risk assessment for a student."""
    authorize_student_access(student_id)

    try:
        records = firestore_service.list_predictions(student_id, limit=1)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not records:
        return jsonify({"error": "No predictions found for this student"}), 404

    # Return the latest prediction
    latest = records[0]
    risk_service = get_risk_service()
    try:
        score, level = risk_service.calculate_risk(latest.get("riskScore", 0))
    except ValueError:
        score = latest.get("riskScore", 0) * 100
        level = latest.get("riskLevel", "LOW")

    return jsonify({
        "studentId": student_id,
        "riskScore": score,
        "riskLevel": level,
        "modelVersion": latest.get("modelVersion", "unknown"),
        "createdAt": latest.get("predictionDate") or latest.get("createdAt"),
    })


# ---------------------------------------------------------------- analytics endpoint


@analytics_bp.route("/api/students/<int:student_id>/analytics")
@login_required
def get_analytics(student_id):
    """Get comprehensive analytics for a student."""
    authorize_student_access(student_id)

    try:
        analytics = firestore_service.get_student_analytics(student_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(analytics)


# ---------------------------------------------------------------- notification endpoints


@analytics_bp.route("/api/notifications")
@login_required
def get_notifications():
    """Get notifications for the current user."""
    identity = current_identity()
    user_uid = identity.get("uid")

    if not user_uid:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        notifications = firestore_service.get_user_notifications(user_uid)
        unread_count = firestore_service.get_unread_notification_count(user_uid)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "notifications": notifications,
        "unreadCount": unread_count,
    })


@analytics_bp.route("/api/notifications/unread-count")
@login_required
def get_unread_count():
    """Get unread notification count for the current user."""
    identity = current_identity()
    user_uid = identity.get("uid")

    if not user_uid:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        unread_count = firestore_service.get_unread_notification_count(user_uid)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"unreadCount": unread_count})


@analytics_bp.route("/api/notifications/<notification_id>/read", methods=["PUT"])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read."""
    identity = current_identity()
    user_uid = identity.get("uid")

    if not user_uid:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        notification = firestore_service.mark_notification_read(notification_id)
    except firestore_service.NotConfigured:
        return jsonify({"error": "Database unavailable"}), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if notification is None:
        return jsonify({"error": "Notification not found"}), 404

    # Verify the notification belongs to the user
    if notification.get("recipientUid") != user_uid:
        return jsonify({"error": "Forbidden"}), 403

    return jsonify({"notification": notification})


# ---------------------------------------------------------------- register blueprint


def register_routes(app):
    """Register analytics blueprint with the Flask app."""
    app.register_blueprint(analytics_bp)
