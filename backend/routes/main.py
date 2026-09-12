"""Main routes: health check and static frontend serving."""
from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

main_bp = Blueprint("main", __name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@main_bp.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@main_bp.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(str(FRONTEND_DIR / "css"), filename)


@main_bp.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(str(FRONTEND_DIR / "js"), filename)


@main_bp.route("/api/health")
def health():
    return jsonify({"status": "ok", "message": "Student Dropout Risk API is running"})
