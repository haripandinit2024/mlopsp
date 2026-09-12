"""Unit tests: risk-tier thresholds and cross-module consistency."""
import unittest

from tests.base import AppTestCase
from backend.model_service import model_service
from src.score_all_students import RISK_THRESHOLD as ROSTER_THRESHOLD


class TestRiskTiers(AppTestCase):
    """Boundary behaviour of the tier mapping in model_service._risk_tier."""

    def test_high_boundary_is_inclusive_at_0_5(self):
        self.assertEqual(model_service._risk_tier(0.5), "High")
        self.assertEqual(model_service._risk_tier(1.0), "High")

    def test_just_below_high_is_medium(self):
        self.assertEqual(model_service._risk_tier(0.4999), "Medium")

    def test_medium_boundary_is_inclusive_at_threshold(self):
        t = model_service.risk_threshold
        self.assertEqual(model_service._risk_tier(t), "Medium")

    def test_just_below_medium_is_low(self):
        t = model_service.risk_threshold
        self.assertEqual(model_service._risk_tier(t - 0.0001), "Low")

    def test_zero_is_low(self):
        self.assertEqual(model_service._risk_tier(0.0), "Low")

    def test_no_gaps_across_full_range(self):
        """Every probability in [0,1] must map to exactly one tier."""
        for i in range(0, 1001):
            p = i / 1000
            self.assertIn(model_service._risk_tier(p), {"Low", "Medium", "High"})


class TestThresholdConsistency(AppTestCase):
    """
    The same 0.243 cutoff is hardcoded in three places
    (model_service, score_all_students, dashboard). This guards against drift.
    """

    def test_risk_threshold_matches_roster_module(self):
        self.assertEqual(model_service.risk_threshold, ROSTER_THRESHOLD)

    def test_dashboard_threshold_matches(self):
        import importlib

        try:
            dashboard = importlib.import_module("src.dashboard")
        except ImportError as exc:  # `rich` is an optional dependency
            self.skipTest(f"dashboard deps unavailable: {exc}")
        self.assertEqual(dashboard.RISK_THRESHOLD, model_service.risk_threshold)


if __name__ == "__main__":
    unittest.main()
