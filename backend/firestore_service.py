"""
Cloud Firestore data access for the platform.

Scope
-----
Firestore replaces SQLite for *application* data:

    users, students, academic_records, attendance, assessments,
    predictions, interventions, notifications, model_versions, audit_logs

The 10,000-row ML roster and the model artifacts intentionally stay on disk
(CSV/JSON) so ``model_service`` behaviour is unchanged.

Conventions
-----------
* Firestore documents use camelCase (idiomatic).
* Returned dicts are mapped back to the snake_case API contract the existing
  dashboard already consumes, so no frontend field names change.
* Every write goes through a validator. The backend uses the Admin SDK, which
  BYPASSES Firestore security rules, so validation here is the real gate.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Optional

from backend import firebase_admin_app as fb

# ---------------------------------------------------------------- collections
USERS = "users"
STUDENTS = "students"
ACADEMIC_RECORDS = "academic_records"
ATTENDANCE = "attendance"
ASSESSMENTS = "assessments"
PREDICTIONS = "predictions"
INTERVENTIONS = "interventions"
NOTIFICATIONS = "notifications"
MODEL_VERSIONS = "model_versions"
AUDIT_LOGS = "audit_logs"

VALID_ROLES = ("student", "faculty", "admin")
VALID_STATUSES = ("active", "suspended")
VALID_INTERVENTION_STATUSES = ("Open", "In Progress", "Resolved")
VALID_PRIORITIES = ("Low", "Medium", "High")

INTERVENTION_TYPES = (
    "Academic counseling",
    "Remedial classes",
    "Attendance improvement",
    "Mentor meeting",
    "Parent communication",
    "Follow-up",
    # retained for data migrated from the legacy store
    "Counseling",
    "Tutoring",
    "Attendance Support",
    "Financial Aid Check",
    "Mentorship",
    "Other",
)


class NotConfigured(RuntimeError):
    """Firestore is not available in this environment."""


def _db():
    if not fb.is_configured():
        raise NotConfigured(
            "Cloud Firestore is not configured. Set FIREBASE_PROJECT_ID and "
            "provide service-account credentials."
        )
    return fb.get_firestore()


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _require_str(value: Any, field: str, max_length: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return value


def _require_number(value: Any, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a finite number")
    if number < low or number > high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return number


def _optional_int(value: Any, field: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer") from None


def _require_student_id(value: Any) -> int:
    student_id = _optional_int(value, "studentId")
    if student_id is None or student_id < 1:
        raise ValueError("studentId is required and must be a positive integer")
    return student_id


# ---------------------------------------------------------------- users

def user_document(uid: str, name: str, email: str, role: str,
                  student_id: Optional[int] = None, status: str = "active") -> dict:
    """Build a users/{uid} document payload. Never contains a password."""
    role = (role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")
    if role != "student":
        student_id = None
    now = utcnow()
    return {
        "uid": uid,
        "name": _require_str(name, "name", 200),
        "email": _require_str(email, "email", 320).lower(),
        "role": role,
        "studentId": student_id,
        "status": status,
        "createdAt": now,
        "updatedAt": now,
    }


def create_user_profile(uid: str, name: str, email: str, role: str,
                        student_id: Optional[int] = None) -> dict:
    document = user_document(uid, name, email, role, student_id)
    _db().collection(USERS).document(uid).set(document)
    return to_api_user(document)


def get_user_profile(uid: str) -> Optional[dict]:
    snapshot = _db().collection(USERS).document(uid).get()
    if not snapshot.exists:
        return None
    return to_api_user(snapshot.to_dict())


def update_user_profile(uid: str, **fields) -> dict:
    """Update only the whitelisted, non-privileged profile fields."""
    allowed = {"name", "updatedAt", "status"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if "name" in payload:
        payload["name"] = _require_str(payload["name"], "name", 200)
    if "status" in payload and payload["status"] not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")
    payload["updatedAt"] = utcnow()
    _db().collection(USERS).document(uid).update(payload)
    return get_user_profile(uid) or {}


def set_user_role(uid: str, role: str, student_id: Optional[int] = None) -> dict:
    """Admin-only role change. Deliberately separate from update_user_profile."""
    role = (role or "").strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of: {', '.join(VALID_ROLES)}")
    payload = {
        "role": role,
        "studentId": student_id if role == "student" else None,
        "updatedAt": utcnow(),
    }
    _db().collection(USERS).document(uid).set(payload, merge=True)
    return get_user_profile(uid) or {}


def to_api_user(document: dict) -> dict:
    """Map a Firestore user document to the existing API shape."""
    return {
        "uid": document.get("uid"),
        "id": document.get("uid"),           # legacy field kept for the frontend
        "name": document.get("name"),
        "email": document.get("email"),
        "role": document.get("role"),
        "student_id": document.get("studentId"),
        "status": document.get("status", "active"),
    }


# ---------------------------------------------------------------- students

def get_student(student_id: int) -> Optional[dict]:
    snapshot = _db().collection(STUDENTS).document(str(student_id)).get()
    if not snapshot.exists:
        return None
    return snapshot.to_dict()


def list_students(department: Optional[str] = None,
                  semester: Optional[str] = None,
                  limit: int = 25) -> list[dict]:
    query = _db().collection(STUDENTS)
    if department:
        query = query.where("department", "==", department)
    if semester and semester != "All":
        query = query.where("semester", "==", semester)
    return [doc.to_dict() for doc in query.limit(max(1, min(limit, 500))).stream()]


def upsert_student(student_id: int, name: str, department: str,
                   semester: Optional[str] = None, year: Optional[int] = None,
                   email: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    student_id = _require_student_id(student_id)
    payload = {
        "studentId": student_id,
        "name": _require_str(name, "name", 200),
        "department": _require_str(department, "department", 120),
        "semester": semester,
        "year": _optional_int(year, "year"),
        "email": (email or "").strip().lower() or None,
        "userId": user_id,
        "updatedAt": utcnow(),
    }
    reference = _db().collection(STUDENTS).document(str(student_id))
    payload["createdAt"] = utcnow()
    reference.set(payload, merge=True)
    return payload


# ---------------------------------------------------------------- academic

def _validate_academic(payload: dict) -> dict:
    student_id = _require_student_id(payload.get("studentId") or payload.get("student_id"))
    document = {
        "studentId": student_id,
        "userId": payload.get("userId") or payload.get("user_id"),
        "subject": _require_str(payload.get("subject"), "subject", 200),
        "semester": payload.get("semester"),
        "academicYear": payload.get("academicYear") or payload.get("academic_year"),
        # Marks and attendance are constrained to their real-world ranges.
        "internalMarks": _require_number(
            payload.get("internalMarks", payload.get("internal_marks")),
            "internalMarks", 0, 100),
        "assignmentMarks": _require_number(
            payload.get("assignmentMarks", payload.get("assignment_marks")),
            "assignmentMarks", 0, 100),
        "attendance": _require_number(payload.get("attendance"), "attendance", 0, 100),
        "backlog": _optional_int(payload.get("backlog"), "backlog") or 0,
        "grade": payload.get("grade"),
        "updatedAt": utcnow(),
    }
    if document["backlog"] < 0:
        raise ValueError("backlog cannot be negative")
    return document


def create_academic_record(payload: dict) -> str:
    document = _validate_academic(payload)
    document["createdAt"] = utcnow()
    _, reference = _db().collection(ACADEMIC_RECORDS).add(document)
    return reference.id


def list_academic_records(student_id: int, limit: int = 100) -> list[dict]:
    student_id = _require_student_id(student_id)
    query = (_db().collection(ACADEMIC_RECORDS)
             .where("studentId", "==", student_id)
             .limit(max(1, min(limit, 500))))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    return records


# ---------------------------------------------------------------- predictions

def record_prediction(student_id: int, risk_score: float, risk_level: str,
                      predicted_class: str, model_version: str,
                      contributing_factors: Iterable[str] | None = None,
                      user_id: Optional[str] = None,
                      department: Optional[str] = None,
                      source: str = "api") -> str:
    """
    Persist a prediction so the decision is auditable.

    Students can never call this: the endpoint requires staff, and the write
    happens with the Admin SDK which bypasses client-facing rules.
    """
    document = {
        "studentId": _require_student_id(student_id),
        "userId": user_id,
        "riskScore": _require_number(risk_score, "riskScore", 0, 1),
        "riskLevel": risk_level if risk_level in ("Low", "Medium", "High") else "Low",
        "predictedClass": predicted_class,
        "modelVersion": _require_str(model_version, "modelVersion", 120),
        "contributingFactors": list(contributing_factors or []),
        "department": department,
        "source": source,
        "predictionDate": utcnow(),
    }
    _, reference = _db().collection(PREDICTIONS).add(document)
    return reference.id


def list_predictions(student_id: int, limit: int = 50) -> list[dict]:
    student_id = _require_student_id(student_id)
    query = (_db().collection(PREDICTIONS)
             .where("studentId", "==", student_id)
             .limit(max(1, min(limit, 200))))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("predictionDate") or "", reverse=True)
    return records


# ---------------------------------------------------------------- interventions

def create_intervention(student_id: Any, intervention_type: str, reason: str = "",
                        description: str = "", priority: str = "Medium",
                        assigned_to: Optional[str] = None,
                        student_name: str = "",
                        created_by: str = "") -> dict:
    student_id = _require_student_id(student_id)
    if intervention_type not in INTERVENTION_TYPES:
        raise ValueError(
            "invalid intervention_type. Expected one of: "
            + ", ".join(INTERVENTION_TYPES)
        )
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
    now = utcnow()
    document = {
        "studentId": student_id,
        "studentName": (student_name or "").strip(),
        "type": intervention_type,
        "reason": (reason or "").strip()[:2000],
        "description": (description or "").strip()[:2000],
        "priority": priority,
        "assignedTo": assigned_to,
        "status": "Open",
        "createdBy": created_by,
        "createdAt": now,
        "updatedAt": now,
    }
    _, reference = _db().collection(INTERVENTIONS).add(document)
    document["id"] = reference.id
    return to_api_intervention(document)


def list_interventions(status: Optional[str] = None,
                       student_id: Optional[int] = None,
                       limit: int = 200) -> list[dict]:
    query = _db().collection(INTERVENTIONS)
    if status:
        if status not in VALID_INTERVENTION_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(VALID_INTERVENTION_STATUSES)}")
        query = query.where("status", "==", status)
    if student_id is not None:
        query = query.where("studentId", "==", _require_student_id(student_id))
    records = []
    for doc in query.limit(max(1, min(limit, 500))).stream():
        data = doc.to_dict()
        data["id"] = doc.id
        records.append(to_api_intervention(data))
    records.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return records


def update_intervention_status(intervention_id: str, status: str) -> Optional[dict]:
    if status not in VALID_INTERVENTION_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(VALID_INTERVENTION_STATUSES)}")
    reference = _db().collection(INTERVENTIONS).document(intervention_id)
    if not reference.get().exists:
        return None
    reference.update({"status": status, "updatedAt": utcnow()})
    data = reference.get().to_dict()
    data["id"] = intervention_id
    return to_api_intervention(data)


def delete_intervention(intervention_id: str) -> bool:
    reference = _db().collection(INTERVENTIONS).document(intervention_id)
    if not reference.get().exists:
        return False
    reference.delete()
    return True


def to_api_intervention(document: dict) -> dict:
    """Map a Firestore intervention to the legacy API shape the UI expects."""
    return {
        "id": document.get("id"),
        "student_id": document.get("studentId"),
        "student_name": document.get("studentName", ""),
        "intervention_type": document.get("type"),
        "reason": document.get("reason", ""),
        "description": document.get("description", ""),
        "priority": document.get("priority", "Medium"),
        "assigned_to": document.get("assignedTo"),
        "status": document.get("status"),
        "created_by": document.get("createdBy", ""),
        "created_at": document.get("createdAt", ""),
        "updated_at": document.get("updatedAt", ""),
    }


# ---------------------------------------------------------------- model versions

def register_model_version(version: str, metrics: dict | None = None,
                           dataset_version: str | None = None,
                           features: Iterable[str] | None = None,
                           notes: str = "") -> str:
    document = {
        "version": _require_str(version, "version", 120),
        "metrics": metrics or {},
        "datasetVersion": dataset_version,
        "features": list(features or []),
        "notes": notes,
        "createdAt": utcnow(),
    }
    _db().collection(MODEL_VERSIONS).document(version).set(document, merge=True)
    return version


def get_current_model_version() -> Optional[dict]:
    query = (_db().collection(MODEL_VERSIONS)
             .limit(50))
    records = [doc.to_dict() for doc in query.stream()]
    if not records:
        return None
    records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    return records[0]


# ---------------------------------------------------------------- audit trail

def log_event(action: str, actor_uid: Optional[str] = None,
              actor_role: Optional[str] = None,
              target: Optional[str] = None,
              outcome: str = "success",
              detail: Optional[dict] = None) -> None:
    """
    Append an audit record.

    Never pass secrets, tokens or passwords in ``detail`` - this collection is
    readable by admins.
    """
    try:
        _db().collection(AUDIT_LOGS).add({
            "action": action,
            "actorUid": actor_uid,
            "actorRole": actor_role,
            "target": target,
            "outcome": outcome,
            "detail": detail or {},
            "createdAt": utcnow(),
        })
    except Exception:
        # Auditing must never take the request down with it.
        pass


# ---------------------------------------------------------------- attendance

def create_attendance_record(student_id: int, subject_code: str, subject_name: str,
                             semester: str, classes_attended: int, total_classes: int,
                             attendance_percentage: Optional[float] = None) -> str:
    """
    Create an attendance record.
    
    If attendance_percentage is not provided, it will be calculated from
    classes_attended and total_classes.
    """
    student_id = _require_student_id(student_id)
    subject_code = _require_str(subject_code, "subjectCode", 100)
    subject_name = _require_str(subject_name, "subjectName", 200)
    semester = _require_str(semester, "semester", 50)
    
    classes_attended = _optional_int(classes_attended, "classesAttended") or 0
    total_classes = _optional_int(total_classes, "totalClasses") or 0
    
    if classes_attended < 0 or total_classes < 0:
        raise ValueError("classesAttended and totalClasses must be non-negative")
    
    if classes_attended > total_classes and total_classes > 0:
        raise ValueError("classesAttended cannot exceed totalClasses")
    
    # Calculate attendance percentage if not provided
    if attendance_percentage is None and total_classes > 0:
        attendance_percentage = (classes_attended / total_classes) * 100
    elif attendance_percentage is None:
        attendance_percentage = 0.0
    
    # Validate attendance percentage
    attendance_percentage = _require_number(attendance_percentage, "attendancePercentage", 0, 100)
    
    document = {
        "studentId": student_id,
        "subjectCode": subject_code,
        "subjectName": subject_name,
        "semester": semester,
        "classesAttended": classes_attended,
        "totalClasses": total_classes,
        "attendancePercentage": attendance_percentage,
        "updatedAt": utcnow(),
    }
    
    reference = _db().collection(ATTENDANCE).document(f"{student_id}_{subject_code}_{semester}")
    document["createdAt"] = utcnow()
    reference.set(document, merge=True)
    return reference.id


def get_attendance_records(student_id: int, limit: int = 100) -> list[dict]:
    """Get attendance records for a student."""
    student_id = _require_student_id(student_id)
    query = (_db().collection(ATTENDANCE)
             .where("studentId", "==", student_id)
             .limit(max(1, min(limit, 500))))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("updatedAt") or "", reverse=True)
    return records


def update_attendance_record(record_id: str, classes_attended: Optional[int] = None,
                             total_classes: Optional[int] = None) -> Optional[dict]:
    """Update an attendance record."""
    reference = _db().collection(ATTENDANCE).document(record_id)
    if not reference.get().exists:
        return None
    
    update_data = {"updatedAt": utcnow()}
    
    if classes_attended is not None:
        classes_attended = _optional_int(classes_attended, "classesAttended") or 0
        if classes_attended < 0:
            raise ValueError("classesAttended must be non-negative")
        update_data["classesAttended"] = classes_attended
    
    if total_classes is not None:
        total_classes = _optional_int(total_classes, "totalClasses") or 0
        if total_classes < 0:
            raise ValueError("totalClasses must be non-negative")
        update_data["totalClasses"] = total_classes
    
    # Recalculate attendance percentage if both values are provided
    if "classesAttended" in update_data and "totalClasses" in update_data:
        if update_data["totalClasses"] > 0:
            update_data["attendancePercentage"] = (
                update_data["classesAttended"] / update_data["totalClasses"]) * 100
        else:
            update_data["attendancePercentage"] = 0.0
        update_data["attendancePercentage"] = _require_number(
            update_data["attendancePercentage"], "attendancePercentage", 0, 100)
    
    reference.update(update_data)
    return reference.get().to_dict()


# ---------------------------------------------------------------- assessments

def create_assessment_record(student_id: int, subject_code: str, subject_name: str,
                            assessment_type: str, marks: float, max_marks: float,
                            semester: str, assessment_date: Optional[str] = None) -> str:
    """Create an assessment record."""
    student_id = _require_student_id(student_id)
    subject_code = _require_str(subject_code, "subjectCode", 100)
    subject_name = _require_str(subject_name, "subjectName", 200)
    assessment_type = _require_str(assessment_type, "assessmentType", 50)
    semester = _require_str(semester, "semester", 50)
    
    # Validate assessment type
    valid_types = ("internal", "assignment", "quiz", "model_exam", "practical")
    if assessment_type not in valid_types:
        raise ValueError(f"assessmentType must be one of: {', '.join(valid_types)}")
    
    marks = _require_number(marks, "marks", 0, max_marks)
    max_marks = _require_number(max_marks, "maxMarks", 0.01, 1000)
    
    if assessment_date:
        assessment_date = _require_str(assessment_date, "assessmentDate", 100)
    else:
        assessment_date = utcnow()
    
    document = {
        "studentId": student_id,
        "subjectCode": subject_code,
        "subjectName": subject_name,
        "assessmentType": assessment_type,
        "marks": marks,
        "maxMarks": max_marks,
        "semester": semester,
        "assessmentDate": assessment_date,
        "createdAt": utcnow(),
        "updatedAt": utcnow(),
    }
    
    _, reference = _db().collection(ASSESSMENTS).add(document)
    return reference.id


def get_assessment_records(student_id: int, limit: int = 100) -> list[dict]:
    """Get assessment records for a student."""
    student_id = _require_student_id(student_id)
    query = (_db().collection(ASSESSMENTS)
             .where("studentId", "==", student_id)
             .limit(max(1, min(limit, 500))))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("assessmentDate") or "", reverse=True)
    return records


def update_assessment_record(record_id: str, marks: Optional[float] = None) -> Optional[dict]:
    """Update an assessment record."""
    reference = _db().collection(ASSESSMENTS).document(record_id)
    if not reference.get().exists:
        return None
    
    update_data = {"updatedAt": utcnow()}
    
    if marks is not None:
        existing = reference.get().to_dict()
        max_marks = existing.get("maxMarks", 100)
        marks = _require_number(marks, "marks", 0, max_marks)
        update_data["marks"] = marks
    
    reference.update(update_data)
    return reference.get().to_dict()


# ---------------------------------------------------------------- model versions

def get_model_version(version: str) -> Optional[dict]:
    """Get a specific model version."""
    reference = _db().collection(MODEL_VERSIONS).document(version)
    if not reference.get().exists:
        return None
    return reference.get().to_dict()


def list_model_versions(limit: int = 50) -> list[dict]:
    """List all model versions."""
    query = _db().collection(MODEL_VERSIONS).limit(max(1, min(limit, 100)))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    return records


# ---------------------------------------------------------------- notifications

def create_notification(recipient_uid: str, notification_type: str, title: str,
                       message: str) -> str:
    """Create a notification for a user."""
    recipient_uid = _require_str(recipient_uid, "recipientUid", 100)
    notification_type = _require_str(notification_type, "type", 50)
    title = _require_str(title, "title", 200)
    message = _require_str(message, "message", 1000)
    
    valid_types = ("risk_alert", "attendance_warning", "academic_warning",
                   "intervention_assigned", "intervention_completed", "recommendation")
    if notification_type not in valid_types:
        raise ValueError(f"notification type must be one of: {', '.join(valid_types)}")
    
    document = {
        "recipientUid": recipient_uid,
        "type": notification_type,
        "title": title,
        "message": message,
        "read": False,
        "createdAt": utcnow(),
    }
    
    _, reference = _db().collection(NOTIFICATIONS).add(document)
    return reference.id


def get_user_notifications(user_uid: str, limit: int = 50) -> list[dict]:
    """Get notifications for a user."""
    user_uid = _require_str(user_uid, "userUid", 100)
    query = (_db().collection(NOTIFICATIONS)
             .where("recipientUid", "==", user_uid)
             .limit(max(1, min(limit, 200))))
    records = [doc.to_dict() for doc in query.stream()]
    records.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
    return records


def mark_notification_read(notification_id: str) -> Optional[dict]:
    """Mark a notification as read."""
    reference = _db().collection(NOTIFICATIONS).document(notification_id)
    if not reference.get().exists:
        return None
    reference.update({
        "read": True,
        "updatedAt": utcnow(),
    })
    return reference.get().to_dict()


def get_unread_notification_count(user_uid: str) -> int:
    """Get count of unread notifications for a user."""
    user_uid = _require_str(user_uid, "userUid", 100)
    query = (_db().collection(NOTIFICATIONS)
             .where("recipientUid", "==", user_uid)
             .where("read", "==", False)
             .limit(1000))
    return len(list(query.stream()))


# ---------------------------------------------------------------- extended student profile

def create_student_profile(student_id: int, uid: str, name: str, email: str,
                          department: str, program: Optional[str] = None,
                          year: Optional[int] = None, semester: Optional[str] = None,
                          admission_score: Optional[float] = None,
                          current_gpa: Optional[float] = None,
                          previous_gpa: Optional[float] = None,
                          backlogs: Optional[int] = None,
                          scholarship_status: Optional[str] = None,
                          financial_aid_status: Optional[str] = None,
                          study_hours_per_day: Optional[float] = None) -> dict:
    """Create or update a student profile."""
    student_id = _require_student_id(student_id)
    uid = _require_str(uid, "uid", 100)
    name = _require_str(name, "name", 200)
    email = _require_str(email, "email", 320).lower()
    department = _require_str(department, "department", 120)
    
    if program:
        program = _require_str(program, "program", 100)
    if semester:
        semester = _require_str(semester, "semester", 50)
    if scholarship_status:
        scholarship_status = _require_str(scholarship_status, "scholarshipStatus", 50)
    if financial_aid_status:
        financial_aid_status = _require_str(financial_aid_status, "financialAidStatus", 50)
    
    # Validate numeric fields
    if current_gpa is not None:
        current_gpa = _require_number(current_gpa, "currentGPA", 0, 10)
    if previous_gpa is not None:
        previous_gpa = _require_number(previous_gpa, "previousGPA", 0, 10)
    if admission_score is not None:
        admission_score = _require_number(admission_score, "admissionScore", 0, 100)
    if study_hours_per_day is not None:
        study_hours_per_day = _require_number(study_hours_per_day, "studyHoursPerDay", 0, 24)
    
    document = {
        "studentId": student_id,
        "uid": uid,
        "name": name,
        "email": email,
        "department": department,
        "program": program,
        "year": _optional_int(year, "year"),
        "semester": semester,
        "admissionScore": admission_score,
        "currentGPA": current_gpa,
        "previousGPA": previous_gpa,
        "backlogs": _optional_int(backlogs, "backlogs"),
        "scholarshipStatus": scholarship_status,
        "financialAidStatus": financial_aid_status,
        "studyHoursPerDay": study_hours_per_day,
        "createdAt": utcnow(),
        "updatedAt": utcnow(),
    }
    
    reference = _db().collection(STUDENTS).document(str(student_id))
    reference.set(document, merge=True)
    return document


def get_student_profile(student_id: int) -> Optional[dict]:
    """Get a student profile."""
    student_id = _require_student_id(student_id)
    snapshot = _db().collection(STUDENTS).document(str(student_id)).get()
    if not snapshot.exists:
        return None
    return snapshot.to_dict()


def update_student_profile(student_id: int, **fields) -> Optional[dict]:
    """Update a student profile with whitelisted fields."""
    student_id = _require_student_id(student_id)
    reference = _db().collection(STUDENTS).document(str(student_id))
    
    if not reference.get().exists:
        return None
    
    allowed_fields = {
        "currentGPA", "previousGPA", "backlogs", "studyHoursPerDay",
        "scholarshipStatus", "financialAidStatus", "program", "year", "semester"
    }
    
    update_data = {"updatedAt": utcnow()}
    
    for key, value in fields.items():
        if key in allowed_fields:
            if key in ("currentGPA", "previousGPA"):
                value = _require_number(value, key, 0, 10)
            elif key == "studyHoursPerDay":
                value = _require_number(value, key, 0, 24)
            elif key == "backlogs":
                value = _optional_int(value, key) or 0
                if value < 0:
                    raise ValueError(f"{key} cannot be negative")
            elif key in ("scholarshipStatus", "financialAidStatus", "program"):
                value = _require_str(value, key, 100)
            elif key in ("year",):
                value = _optional_int(value, key)
            update_data[key] = value
    
    reference.update(update_data)
    return reference.get().to_dict()


# ---------------------------------------------------------------- analytics helpers

def get_student_analytics(student_id: int) -> dict:
    """Get comprehensive analytics for a student."""
    student_id = _require_student_id(student_id)
    
    # Get academic records
    academic_records = list_academic_records(student_id, limit=200)
    
    # Get attendance records
    attendance_records = get_attendance_records(student_id, limit=200)
    
    # Get assessment records
    assessment_records = get_assessment_records(student_id, limit=200)
    
    # Calculate analytics
    analytics = {
        "gpaTrend": [],  # Will be populated from academic records
        "attendanceTrend": [],
        "subjectPerformance": [],
        "assignmentPerformance": [],
        "backlogs": 0,
        "averageAttendance": 0.0,
        "averageGPA": 0.0,
    }
    
    # Calculate average attendance
    if attendance_records:
        total_attendance = sum(r.get("attendancePercentage", 0) for r in attendance_records)
        analytics["averageAttendance"] = round(total_attendance / len(attendance_records), 2)
    
    # Calculate subject performance
    if academic_records:
        subjects = {}
        for record in academic_records:
            subject = record.get("subject", record.get("subjectName", "Unknown"))
            if subject not in subjects:
                subjects[subject] = {
                    "totalMarks": 0,
                    "maxMarks": 0,
                    "count": 0,
                    "assignments": [],
                }
            internal = record.get("internalMarks", 0)
            assignment = record.get("assignmentMarks", 0)
            subjects[subject]["totalMarks"] += internal + assignment
            subjects[subject]["maxMarks"] += 100 + 100  # Assuming max 100 each
            subjects[subject]["count"] += 1
            subjects[subject]["assignments"].append(assignment)
        
        analytics["subjectPerformance"] = [
            {
                "subject": subject,
                "averageScore": round(data["totalMarks"] / data["count"], 2) if data["count"] > 0 else 0,
                "assignmentAverage": round(sum(data["assignments"]) / len(data["assignments"]), 2) if data["assignments"] else 0,
                "recordCount": data["count"],
            }
            for subject, data in subjects.items()
        ]
    
    return analytics

