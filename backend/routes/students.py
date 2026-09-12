"""Student lookup routes."""
from flask import Blueprint, jsonify

from backend.services.model_service import model_service

students_bp = Blueprint("students", __name__)


@students_bp.route("/api/student/<int:student_id>")
def get_student(student_id):
    result = model_service.predict_student(student_id)
    if "error" in result:
        return jsonify(result), 404
    return jsonify(result)
