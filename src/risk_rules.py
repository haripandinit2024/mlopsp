"""
Risk tier rules — single source of truth.
=========================================

The Low / Medium / High cutoffs were previously hardcoded as `0.243` in three
separate modules (backend/model_service.py, src/score_all_students.py,
src/dashboard.py). Any change had to be made in all three or the live
prediction API and the cached roster would silently disagree.

Import the tier helper from here instead of re-declaring the number:

    from src.risk_rules import risk_tier, MEDIUM_THRESHOLD, HIGH_THRESHOLD

Both thresholds can be overridden per deployment with environment variables,
which is useful when re-tuning for a different precision/recall target.
"""

import os

# Probability of the "Dropout" class at or above which a student is flagged.
#
# MEDIUM_THRESHOLD is the recall-oriented cutoff produced by
# `src/train_xgboost.py --tune` (find_best_threshold, min_recall=0.75). Lowering
# it catches more at-risk students at the cost of more false alarms.
HIGH_THRESHOLD = float(os.environ.get("RISK_HIGH_THRESHOLD", "0.5"))
MEDIUM_THRESHOLD = float(os.environ.get("RISK_MEDIUM_THRESHOLD", "0.243"))

TIERS = ("Low", "Medium", "High")


def risk_tier(probability: float) -> str:
    """Map a dropout probability in [0, 1] to a risk tier."""
    if probability >= HIGH_THRESHOLD:
        return "High"
    if probability >= MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"
