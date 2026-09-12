"""Faculty dashboard and reference-list routes."""
from flask import Blueprint, jsonify, request

from backend.services.model_service import model_service

faculty_bp = Blueprint("faculty", __name__)

DEPARTMENTS = ["CS", "Engineering", "Business", "Arts", "Science"]
SEMESTERS = ["Year 1", "Year 2", "Year 3", "Year 4"]


@faculty_bp.route("/api/faculty/<department>")
def faculty_list(department):
    semester = request.args.get("semester", "All")
    return jsonify(model_service.get_faculty_list(department, semester))


@faculty_bp.route("/api/departments")
def departments():
    return jsonify(DEPARTMENTS)


@faculty_bp.route("/api/semesters")
def semesters():
    return jsonify(SEMESTERS)
