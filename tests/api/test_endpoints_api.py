"""API tests: data + prediction + dashboard + intervention endpoints."""
import unittest

from tests.base import AppTestCase

VALID_PROFILE = {
    "GPA": 2.5, "Attendance_Rate": 70, "Stress_Index": 8,
    "Study_Hours_per_Day": 2, "Semester_GPA": 3.0, "Assignment_Delay_Days": 6,
    "Age": 20, "Family_Income": 30000, "Travel_Time_Minutes": 30, "CGPA": 3.0,
    "Gender": "Male", "Internet_Access": "Yes", "Part_Time_Job": "No",
    "Scholarship": "No", "Department": "CS", "Semester": "Year 1",
    "Parental_Education": "Bachelor",
}


class TestStudentLookup(AppTestCase):
    """Roster-wide lookups are a staff capability; students see their own record."""

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/student/1").status_code, 401)

    def test_existing_student_returns_full_record(self):
        self.login_as("faculty")
        res = self.client.get("/api/student/1")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        for key in ("student_id", "department", "semester", "gpa",
                    "attendance_rate", "stress_index", "risk_probability",
                    "risk_tier", "recommendations"):
            self.assertIn(key, body)
        self.assertIn(body["risk_tier"], {"Low", "Medium", "High"})
        self.assertGreaterEqual(body["risk_probability"], 0.0)
        self.assertLessEqual(body["risk_probability"], 1.0)

    def test_linked_student_can_read_own_record(self):
        self.login_as("student", email="linked@example.com", student_id=1)
        res = self.client.get("/api/student/1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["student_id"], 1)

    def test_student_without_link_is_denied(self):
        self.login_as("student", email="unlinked@example.com")
        self.assertEqual(self.client.get("/api/student/1").status_code, 403)

    def test_unknown_student_returns_404(self):
        self.login_as("faculty")
        self.assertEqual(self.client.get("/api/student/999999").status_code, 404)

    def test_non_numeric_student_id_returns_404(self):
        self.login_as("faculty")
        self.assertEqual(self.client.get("/api/student/abc").status_code, 404)

    def test_zero_and_negative_ids_return_404(self):
        self.login_as("faculty")
        self.assertEqual(self.client.get("/api/student/0").status_code, 404)
        self.assertEqual(self.client.get("/api/student/-1").status_code, 404)

    def test_recommendations_are_non_empty(self):
        self.login_as("faculty")
        recs = self.client.get("/api/student/1").get_json()["recommendations"]
        self.assertTrue(recs)
        self.assertTrue(all(isinstance(r, str) and r for r in recs))


class TestPrediction(AppTestCase):
    def test_requires_authentication(self):
        self.assertEqual(self.client.post("/api/predict", json=VALID_PROFILE).status_code, 401)

    def test_valid_profile_returns_probability_and_tier(self):
        self.login_as("student")
        res = self.client.post("/api/predict", json=VALID_PROFILE)
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertGreaterEqual(body["risk_probability"], 0.0)
        self.assertLessEqual(body["risk_probability"], 1.0)
        self.assertIn(body["risk_tier"], {"Low", "Medium", "High"})

    def test_missing_required_fields_rejected(self):
        self.login_as("student")
        for field in ("GPA", "Attendance_Rate", "Stress_Index"):
            payload = {k: v for k, v in VALID_PROFILE.items() if k != field}
            res = self.client.post("/api/predict", json=payload)
            self.assertEqual(res.status_code, 400, f"{field} should be required")

    def test_empty_body_rejected(self):
        self.login_as("student")
        self.assertEqual(self.client.post("/api/predict", json={}).status_code, 400)

    def test_extra_fields_are_ignored(self):
        self.login_as("student")
        payload = dict(VALID_PROFILE, favorite_color="blue", __proto__="x")
        res = self.client.post("/api/predict", json=payload)
        self.assertEqual(res.status_code, 200)

    def test_prediction_is_deterministic(self):
        self.login_as("student")
        first = self.client.post("/api/predict", json=VALID_PROFILE).get_json()
        second = self.client.post("/api/predict", json=VALID_PROFILE).get_json()
        self.assertEqual(first["risk_probability"], second["risk_probability"])

    def test_method_not_allowed(self):
        self.login_as("student")
        self.assertEqual(self.client.put("/api/predict", json=VALID_PROFILE).status_code, 405)
        self.assertEqual(self.client.delete("/api/predict").status_code, 405)

    def test_unknown_route_returns_404(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/does-not-exist").status_code, 404)


class TestReferenceLists(AppTestCase):
    def test_departments_require_auth(self):
        self.assertEqual(self.client.get("/api/departments").status_code, 401)

    def test_departments_returned(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/departments").get_json(),
                         ["CS", "Engineering", "Business", "Arts", "Science"])

    def test_semesters_returned(self):
        self.login_as("student")
        self.assertEqual(self.client.get("/api/semesters").get_json(),
                         ["Year 1", "Year 2", "Year 3", "Year 4"])


class TestFacultyEndpoint(AppTestCase):
    def test_requires_faculty_role(self):
        self.assertIn(self.client.get("/api/faculty/CS").status_code, (401, 403))
        self.login_as("student")
        self.assertEqual(self.client.get("/api/faculty/CS").status_code, 403)

    def test_faculty_gets_sorted_at_risk_list(self):
        self.login_as("faculty")
        res = self.client.get("/api/faculty/CS")
        self.assertEqual(res.status_code, 200)
        rows = res.get_json()
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 25)
        probs = [r["risk_probability"] for r in rows]
        self.assertEqual(probs, sorted(probs, reverse=True))
        self.assertTrue(all(r["risk_tier"] in {"High", "Medium"} for r in rows))

    def test_unknown_department_returns_empty_list(self):
        self.login_as("faculty")
        res = self.client.get("/api/faculty/NotADepartment")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_semester_filter_applies(self):
        self.login_as("faculty")
        rows = self.client.get("/api/faculty/CS?semester=Year%201").get_json()
        self.assertTrue(rows)
        self.assertTrue(all(r["semester"] == "Year 1" for r in rows))

    def test_sql_injection_in_department_is_safe(self):
        self.login_as("faculty")
        res = self.client.get("/api/faculty/CS%27%3B%20DROP%20TABLE%20users%3B--")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])


class TestOverviewEndpoint(AppTestCase):
    def test_requires_admin(self):
        self.assertIn(self.client.get("/api/overview").status_code, (401, 403))
        self.login_as("faculty")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)
        self.login_as("student", email="student@example.com")
        self.assertEqual(self.client.get("/api/overview").status_code, 403)

    def test_admin_gets_consistent_totals(self):
        self.login_as("admin")
        res = self.client.get("/api/overview")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["total_students"], 10000)
        dist = body["risk_distribution"]
        self.assertEqual(sum(dist.values()), body["total_students"])
        self.assertAlmostEqual(body["dropout_rate"], 0.2354, places=3)
        self.assertTrue(body["risk_by_department"])
        self.assertTrue(body["risk_by_year"])

    def test_overview_shape_is_stable(self):
        self.login_as("admin")
        body = self.client.get("/api/overview").get_json()
        self.assertEqual(set(body),
                         {"total_students", "dropout_rate", "risk_distribution",
                          "risk_by_department", "risk_by_year"})


class TestInterventionEndpoints(AppTestCase):
    def test_requires_faculty_or_admin(self):
        self.assertIn(self.client.get("/api/interventions").status_code, (401, 403))
        self.login_as("student")
        self.assertEqual(self.client.get("/api/interventions").status_code, 403)

    def test_create_and_list(self):
        self.login_as("faculty")
        res = self.client.post("/api/interventions", json={
            "student_id": 42, "student_name": "Student 42",
            "intervention_type": "Tutoring", "description": "Weekly sessions",
        })
        self.assertEqual(res.status_code, 201)
        new_id = res.get_json()["id"]
        listed = self.client.get("/api/interventions").get_json()["interventions"]
        self.assertIn(new_id, [i["id"] for i in listed])

    def test_create_missing_fields_rejected(self):
        self.login_as("faculty")
        res = self.client.post("/api/interventions", json={"student_name": "no id"})
        self.assertEqual(res.status_code, 400)

    def test_create_invalid_type_rejected(self):
        self.login_as("faculty")
        res = self.client.post("/api/interventions", json={
            "student_id": 1, "intervention_type": "Expulsion"})
        self.assertEqual(res.status_code, 400)

    def test_create_with_non_numeric_student_id_is_client_error(self):
        self.login_as("faculty")
        res = self.client.post("/api/interventions", json={
            "student_id": "abc", "intervention_type": "Tutoring"})
        self.assertEqual(res.status_code, 400)

    def test_filter_with_non_numeric_student_id_is_client_error(self):
        """A bad query parameter must be a 4xx, never a 500."""
        self.login_as("faculty")
        res = self.client.get("/api/interventions?student_id=abc")
        self.assertLess(res.status_code, 500)

    def test_update_status(self):
        self.login_as("faculty")
        iid = self.client.post("/api/interventions", json={
            "student_id": 5, "intervention_type": "Mentorship"}).get_json()["id"]
        res = self.client.patch(f"/api/interventions/{iid}", json={"status": "Resolved"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "Resolved")

    def test_update_invalid_status_rejected(self):
        self.login_as("faculty")
        iid = self.client.post("/api/interventions", json={
            "student_id": 5, "intervention_type": "Mentorship"}).get_json()["id"]
        res = self.client.patch(f"/api/interventions/{iid}", json={"status": "Cancelled"})
        self.assertEqual(res.status_code, 400)

    def test_update_missing_record_returns_404(self):
        self.login_as("faculty")
        res = self.client.patch("/api/interventions/999999", json={"status": "Resolved"})
        self.assertEqual(res.status_code, 404)

    def test_delete_requires_admin(self):
        self.login_as("faculty")
        iid = self.client.post("/api/interventions", json={
            "student_id": 5, "intervention_type": "Mentorship"}).get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/interventions/{iid}").status_code, 403)

    def test_admin_can_delete(self):
        self.login_as("admin")
        iid = self.client.post("/api/interventions", json={
            "student_id": 5, "intervention_type": "Mentorship"}).get_json()["id"]
        self.assertEqual(self.client.delete(f"/api/interventions/{iid}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/interventions/{iid}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
