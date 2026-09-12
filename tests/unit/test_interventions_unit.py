"""Unit tests: backend/interventions.py validation and state transitions."""
import unittest

from tests.base import AppTestCase
from backend import interventions


class TestInterventionValidation(AppTestCase):
    def test_missing_student_id_rejected(self):
        with self.assertRaises(ValueError):
            interventions.create(None, "X", "Counseling", "", "tester")

    def test_blank_student_id_rejected(self):
        with self.assertRaises(ValueError):
            interventions.create("", "X", "Counseling", "", "tester")

    def test_missing_type_rejected(self):
        with self.assertRaises(ValueError):
            interventions.create(1, "X", "", "", "tester")

    def test_unknown_type_rejected(self):
        with self.assertRaises(ValueError):
            interventions.create(1, "X", "Expulsion", "", "tester")

    def test_every_declared_type_is_accepted(self):
        for i, t in enumerate(interventions.INTERVENTION_TYPES):
            item = interventions.create(100 + i, "Student", t, "note", "tester")
            self.assertEqual(item["intervention_type"], t)

    def test_non_numeric_student_id_raises_value_error(self):
        """Must be a ValueError (not TypeError/OverflowError) so the API can map it to 400."""
        with self.assertRaises(ValueError):
            interventions.create("abc", "X", "Counseling", "", "tester")

    def test_new_intervention_defaults_to_open(self):
        item = interventions.create(7, "Student Seven", "Tutoring", "needs help", "prof")
        self.assertEqual(item["status"], "Open")
        self.assertEqual(item["created_by"], "prof")
        self.assertIn("created_at", item)


class TestInterventionStatusFlow(AppTestCase):
    def test_valid_status_transitions(self):
        item = interventions.create(1, "S", "Mentorship", "", "t")
        for status in interventions.STATUSES:
            updated = interventions.update_status(item["id"], status)
            self.assertEqual(updated["status"], status)

    def test_invalid_status_rejected(self):
        item = interventions.create(1, "S", "Mentorship", "", "t")
        with self.assertRaises(ValueError):
            interventions.update_status(item["id"], "Cancelled")

    def test_update_missing_record_returns_none(self):
        self.assertIsNone(interventions.update_status(999999, "Resolved"))

    def test_delete_missing_record_returns_false(self):
        self.assertFalse(interventions.delete(999999))

    def test_delete_removes_record(self):
        item = interventions.create(1, "S", "Mentorship", "", "t")
        self.assertTrue(interventions.delete(item["id"]))
        self.assertIsNone(interventions.get(item["id"]))


class TestInterventionQueries(AppTestCase):
    def test_filter_by_status(self):
        a = interventions.create(1, "A", "Tutoring", "", "t")
        b = interventions.create(2, "B", "Tutoring", "", "t")
        interventions.update_status(b["id"], "Resolved")
        open_items = interventions.list_interventions(status="Open")
        self.assertEqual([i["id"] for i in open_items], [a["id"]])

    def test_filter_by_student_id(self):
        interventions.create(11, "A", "Tutoring", "", "t")
        interventions.create(22, "B", "Tutoring", "", "t")
        items = interventions.list_interventions(student_id=11)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["student_id"], 11)

    def test_term_search_does_not_allow_sql_injection(self):
        interventions.create(1, "Normal Student", "Tutoring", "fine", "t")
        for payload in ["'; DROP TABLE interventions; --", "%' OR '1'='1", "' UNION SELECT * FROM users --"]:
            result = interventions.list_interventions(term=payload)
            self.assertEqual(result, [], f"payload matched unexpectedly: {payload}")
        # Table must survive and still contain the original row.
        self.assertEqual(len(interventions.list_interventions()), 1)

    def test_list_with_non_numeric_student_id_raises_value_error(self):
        """
        Documents current behaviour: list_interventions casts with int() and
        lets ValueError escape. The API layer must translate this to 400.
        """
        with self.assertRaises(ValueError):
            interventions.list_interventions(student_id="abc")


if __name__ == "__main__":
    unittest.main()
