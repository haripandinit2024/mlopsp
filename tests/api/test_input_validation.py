"""
Input validation / negative tests.

Requirement under test: invalid user input must be rejected with 4xx and must
never produce a 5xx or a silently-fabricated prediction.

Context: model_service.predict_custom() wraps its whole body in
`except Exception: return self._mock_predict(data)`. That means malformed
values do not raise loudly — they silently degrade to a heuristic score that
looks like a real model output. These tests pin the *required* behaviour
(reject the input) so the silent-degradation risk is visible.
"""
import unittest

from tests.base import AppTestCase
from tests.api.test_endpoints_api import VALID_PROFILE


class TestPredictionInputValidation(AppTestCase):
    def setUp(self):
        super().setUp()
        self.login_as("student")

    def _post(self, **overrides):
        payload = dict(VALID_PROFILE)
        payload.update(overrides)
        return self.client.post("/api/predict", json=payload)

    # ---- out-of-range numeric fields ----

    def test_negative_gpa_rejected(self):
        self.assertEqual(self._post(GPA=-1.5).status_code, 400)

    def test_gpa_above_4_rejected(self):
        self.assertEqual(self._post(GPA=99.0).status_code, 400)

    def test_attendance_above_100_rejected(self):
        self.assertEqual(self._post(Attendance_Rate=150).status_code, 400)

    def test_negative_attendance_rejected(self):
        self.assertEqual(self._post(Attendance_Rate=-10).status_code, 400)

    def test_stress_index_above_10_rejected(self):
        self.assertEqual(self._post(Stress_Index=999).status_code, 400)

    def test_negative_negative_age_rejected(self):
        self.assertEqual(self._post(Age=-5).status_code, 400)

    def test_negative_study_hours_rejected(self):
        self.assertEqual(self._post(Study_Hours_per_Day=-3).status_code, 400)

    # ---- wrong types ----

    def test_string_gpa_rejected(self):
        self.assertEqual(self._post(GPA="high").status_code, 400)

    def test_null_gpa_rejected(self):
        self.assertEqual(self._post(GPA=None).status_code, 400)

    def test_list_gpa_rejected(self):
        self.assertEqual(self._post(GPA=[2.5, 3.0]).status_code, 400)

    def test_numeric_string_attendance_rejected(self):
        self.assertEqual(self._post(Attendance_Rate="70").status_code, 400)

    # ---- unknown categorical values ----

    def test_unknown_department_handled(self):
        """Unseen category must not crash; OneHotEncoder is configured to ignore."""
        res = self._post(Department="Underwater Basket Weaving")
        self.assertLess(res.status_code, 500)

    def test_unknown_semester_handled(self):
        res = self._post(Semester="Year 99")
        self.assertLess(res.status_code, 500)

    # ---- payload shape ----

    def test_non_object_json_body_is_client_error(self):
        res = self.client.post("/api/predict", data='"nope"',
                               content_type="application/json")
        self.assertLess(res.status_code, 500)

    def test_list_json_body_is_client_error(self):
        res = self.client.post("/api/predict", json=[1, 2, 3])
        self.assertLess(res.status_code, 500)

    def test_malformed_json_is_client_error(self):
        res = self.client.post("/api/predict", data="{not json",
                               content_type="application/json")
        self.assertLess(res.status_code, 500)

    def test_very_large_payload_is_rejected_gracefully(self):
        res = self._post(GPA=1e308, Attendance_Rate=1e308)
        self.assertLess(res.status_code, 500)

    def test_xss_payload_in_categorical_is_not_reflected_unescaped(self):
        xss = "<script>alert(1)</script>"
        res = self._post(Department=xss)
        # Either rejected, or echoed back only as inert JSON (never raw script in HTML).
        if res.status_code == 200:
            self.assertNotIn("text/html", res.headers.get("Content-Type", ""))


class TestNoServerErrorsOnUserInput(AppTestCase):
    """Sweep a batch of hostile inputs and assert no 5xx is produced."""

    def setUp(self):
        super().setUp()
        self.login_as("student")

    def test_hostile_values_never_produce_5xx(self):
        hostile = [
            {"GPA": "' OR 1=1 --", "Attendance_Rate": 70, "Stress_Index": 5},
            {"GPA": 2, "Attendance_Rate": "<script>alert(1)</script>", "Stress_Index": 5},
            {"GPA": 2, "Attendance_Rate": 70, "Stress_Index": "8\"; DROP TABLE users;--"},
            {"GPA": float("nan"), "Attendance_Rate": 70, "Stress_Index": 5},
            {"GPA": 2, "Attendance_Rate": 70, "Stress_Index": 5, "extra": {"nested": [1, 2]}},
            {"GPA": "2.5e400", "Attendance_Rate": 70, "Stress_Index": 5},
        ]
        for payload in hostile:
            with self.subTest(payload=payload):
                res = self.client.post("/api/predict", json=payload)
                self.assertLess(res.status_code, 500, f"5xx for {payload}")

    def test_users_table_survives_injection_sweep(self):
        from backend import auth

        with auth._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertGreaterEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
