"""Custom prediction route."""
from flask import Blueprint, jsonify, request

from backend.services.model_service import model_service

predict_bp = Blueprint("predict", __name__)

REQUIRED_FIELDS = ["GPA", "Attendance_Rate", "Stress_Index"]


@predict_bp.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    for field in REQUIRED_FIELDS:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    return jsonify(model_service.predict_custom(data))
