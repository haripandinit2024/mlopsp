"""Admin overview route."""
from flask import Blueprint, jsonify

from backend.services.model_service import model_service

overview_bp = Blueprint("overview", __name__)


@overview_bp.route("/api/overview")
def overview():
    result = model_service.get_overview()
    if "error" in result:
        return jsonify(result), 503
    return jsonify(result)
