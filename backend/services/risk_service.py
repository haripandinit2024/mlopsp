"""
Risk Level Service - Centralized risk classification logic.

This service provides a single source of truth for risk level calculation.
All endpoints should use this service to ensure consistency.

Thresholds are configurable via environment variables or use sensible defaults.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple


class RiskService:
    """Centralized risk level classification service."""

    # Default thresholds (percentage 0-100)
    # Configurable via environment variables
    LOW_MAX = 25
    MEDIUM_MAX = 50
    HIGH_MAX = 75

    def __init__(self):
        """Initialize risk service with configurable thresholds."""
        self._load_thresholds()

    def _load_thresholds(self):
        """Load thresholds from environment variables."""
        try:
            self.LOW_MAX = int(os.environ.get("RISK_LOW_MAX", "25"))
            self.MEDIUM_MAX = int(os.environ.get("RISK_MEDIUM_MAX", "50"))
            self.HIGH_MAX = int(os.environ.get("RISK_HIGH_MAX", "75"))
        except ValueError:
            # Use defaults if env vars are invalid
            pass

        # Validate thresholds
        if not (0 <= self.LOW_MAX < self.MEDIUM_MAX < self.HIGH_MAX <= 100):
            # Reset to defaults if invalid
            self.LOW_MAX = 25
            self.MEDIUM_MAX = 50
            self.HIGH_MAX = 75

    def calculate_risk_level(self, risk_score: float) -> str:
        """
        Calculate risk level from a score (0-100).

        Args:
            risk_score: Risk score from 0-100

        Returns:
            Risk level string: LOW, MEDIUM, HIGH, or CRITICAL

        Raises:
            ValueError: If risk_score is not in valid range (0-100)
        """
        risk_score = self._validate_score(risk_score)

        if risk_score <= self.LOW_MAX:
            return "LOW"
        elif risk_score <= self.MEDIUM_MAX:
            return "MEDIUM"
        elif risk_score <= self.HIGH_MAX:
            return "HIGH"
        else:
            return "CRITICAL"

    def _validate_score(self, score: float) -> float:
        """Validate and normalize risk score."""
        if not isinstance(score, (int, float)):
            raise ValueError("Risk score must be a number")
        if isinstance(score, bool):
            raise ValueError("Risk score must be a number, not boolean")
        score = float(score)
        if score != score or score in (float("inf"), float("-inf")):
            raise ValueError("Risk score must be a finite number")
        if score < 0 or score > 100:
            raise ValueError("Risk score must be between 0 and 100")
        return score

    def convert_probability_to_score(self, probability: float) -> float:
        """
        Convert a probability (0-1) to a percentage score (0-100).

        Args:
            probability: Probability value from 0-1

        Returns:
            Percentage score from 0-100
        """
        if not isinstance(probability, (int, float)):
            raise ValueError("Probability must be a number")
        if isinstance(probability, bool):
            raise ValueError("Probability must be a number, not boolean")
        probability = float(probability)
        if probability != probability or probability in (float("inf"), float("-inf")):
            raise ValueError("Probability must be a finite number")
        if probability < 0 or probability > 1:
            raise ValueError("Probability must be between 0 and 1")
        return probability * 100

    def calculate_risk(self, probability: float) -> Tuple[float, str]:
        """
        Convert probability to score and calculate risk level in one step.

        Args:
            probability: Probability value from 0-1

        Returns:
            Tuple of (score, level) where:
            - score: Percentage from 0-100
            - level: Risk level string (LOW, MEDIUM, HIGH, CRITICAL)
        """
        score = self.convert_probability_to_score(probability)
        level = self.calculate_risk_level(score)
        return score, level

    def get_thresholds(self) -> dict:
        """Return current threshold configuration."""
        return {
            "low_max": self.LOW_MAX,
            "medium_max": self.MEDIUM_MAX,
            "high_max": self.HIGH_MAX,
            "critical_min": self.HIGH_MAX + 1,
        }

    def explain_risk_level(self, risk_score: float) -> dict:
        """
        Provide explanation for a risk level.

        Args:
            risk_score: Risk score from 0-100

        Returns:
            Dict with risk level info and thresholds
        """
        risk_score = self._validate_score(risk_score)
        level = self.calculate_risk_level(risk_score)
        thresholds = self.get_thresholds()

        return {
            "risk_score": risk_score,
            "risk_level": level,
            "thresholds": thresholds,
            "interpretation": self._get_interpretation(level),
        }

    def _get_interpretation(self, level: str) -> str:
        """Get human-readable interpretation of risk level."""
        interpretations = {
            "LOW": "Student is at low risk of dropout. Continue monitoring.",
            "MEDIUM": "Student shows some risk factors. Consider preventive interventions.",
            "HIGH": "Student is at significant risk. Recommend intervention planning.",
            "CRITICAL": "Student is at critical risk. Immediate intervention required.",
        }
        return interpretations.get(level, "Unknown risk level")


# Singleton instance
risk_service = RiskService()


def get_risk_service() -> RiskService:
    """Get the singleton risk service instance."""
    return risk_service
