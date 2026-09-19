"""
Model Service - Loads trained model and provides prediction capabilities.
"""
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Shared tier cutoffs, so the API and the cached roster can never drift apart.
sys.path.insert(0, str(BASE_DIR))
from src.risk_rules import MEDIUM_THRESHOLD, risk_tier  # noqa: E402


def _safe_number(value, default: float = 0.0) -> float:
    """Coerce a value to a finite float, falling back to `default`.

    The fallback heuristic does arithmetic on raw request values. Without this
    guard a single non-numeric field raises TypeError out of `_mock_predict`
    and surfaces as an HTTP 500 instead of a usable prediction.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _optional_number(value, default=None):
    """Coerce a value to a finite float, or `default` when missing/NaN.

    Roster rows can carry NaN (e.g. unrecorded Stress_Index). Flask's JSON
    provider serializes NaN as a bare `NaN` token, which browsers reject in
    `response.json()`, so any field that may be NaN must become null instead.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


class ModelService:
    """Singleton service for model predictions."""

    def __init__(self):
        self.model = None
        self.preprocessor = None
        self.roster = None
        self.risk_threshold = MEDIUM_THRESHOLD
        self._loaded = False

    def load(self):
        """Load model, preprocessor, and risk scores."""
        if self._loaded:
            return

        scores_path = BASE_DIR / "dataset" / "processed" / "student_risk_scores.csv"

        if scores_path.exists():
            self.roster = pd.read_csv(str(scores_path))

        try:
            from xgboost import XGBClassifier
            import joblib

            model_path = BASE_DIR / "models" / "xgboost_dropout_model.json"
            preprocessor_path = BASE_DIR / "models" / "preprocessor.joblib"

            if not model_path.exists() or not preprocessor_path.exists():
                print("[ModelService] Model files not found. Using mock predictions.")
                self._loaded = True
                return

            self.model = XGBClassifier()
            self.model.load_model(str(model_path))
            self.preprocessor = joblib.load(str(preprocessor_path))
            self._loaded = True

            print("[ModelService] Model loaded successfully.")
        except Exception as e:
            print(f"[ModelService] Error loading model: {e}")
            self._loaded = True

    def predict_student(self, student_id: int) -> dict:
        """Look up a student by ID from the pre-computed risk scores."""
        if self.roster is None:
            return {"error": "Risk scores not loaded"}

        match = self.roster[self.roster["Student_ID"] == student_id]
        if match.empty:
            return {"error": f"Student {student_id} not found"}

        row = match.iloc[0]
        return {
            "student_id": int(row["Student_ID"]),
            "department": row["Department"],
            "semester": row["Semester"],
            "gender": row["Gender"],
            "attendance_rate": _safe_number(row["Attendance_Rate"]),
            "gpa": _safe_number(row["GPA"]),
            "cgpa": _safe_number(row["CGPA"]),
            "stress_index": _optional_number(row["Stress_Index"]),
            "actual_dropout": int(row["Actual_Dropout"]),
            "risk_probability": _safe_number(row["Risk_Probability"]),
            "risk_tier": row["Risk_Tier"],
            "recommendations": self._get_recommendations(row),
        }

    def predict_custom(self, data: dict) -> dict:
        """Predict risk for a custom student profile."""
        if self.model is None or self.preprocessor is None:
            return self._mock_predict(data)

        try:
            student_df = pd.DataFrame([data])

            # Add engineered features
            student_df["GPA_Decline"] = student_df["GPA"] - student_df["Semester_GPA"]
            student_df["Low_Attendance_Flag"] = (student_df["Attendance_Rate"] < 75).astype(int)
            student_df["Engagement_Score"] = (
                student_df["Study_Hours_per_Day"] - 0.1 * student_df["Assignment_Delay_Days"]
            )

            from src.preprocessing_pipeline import NUMERIC_COLS_V3, CATEGORICAL_COLS_V3
            X = self.preprocessor.transform(student_df[NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3])
            proba = self.model.predict_proba(X)[:, 1][0]

            return {
                "risk_probability": float(proba),
                "risk_tier": self._risk_tier(proba),
                "recommendations": self._get_recommendations(data),
            }
        except Exception as e:
            return self._mock_predict(data)

    def _mock_predict(self, data) -> dict:
        """Fallback mock prediction when model isn't loaded."""
        if not isinstance(data, dict):
            data = {}
        gpa = _safe_number(data.get("GPA"), 3.0)
        attendance = _safe_number(data.get("Attendance_Rate"), 85.0)
        stress = _safe_number(data.get("Stress_Index"), 5.0)

        # Simple heuristic
        risk = 0.5
        risk -= (gpa - 2.0) * 0.15
        risk -= (attendance - 50) * 0.005
        risk += (stress - 5) * 0.03
        risk = max(0.0, min(1.0, risk))

        return {
            "risk_probability": round(risk, 4),
            "risk_tier": self._risk_tier(risk),
            "recommendations": self._get_recommendations(data),
        }

    def _risk_tier(self, proba: float) -> str:
        return risk_tier(proba)

    def _get_recommendations(self, row) -> list:
        def value(key, default):
            if not hasattr(row, "get"):
                return default
            return _safe_number(row.get(key), default)

        recs = []
        if value("Attendance_Rate", 100.0) < 75:
            recs.append("Attendance below 75% - flag for an advising check-in.")
        if value("GPA", 4.0) < 2.0:
            recs.append("Low GPA - recommend tutoring / academic support referral.")
        if value("Stress_Index", 0.0) >= 7:
            recs.append("High stress index - suggest counseling / wellness resources.")
        if value("Assignment_Delay_Days", 0.0) >= 5:
            recs.append("Frequent late assignments - check in on workload/time management.")
        if not recs:
            recs.append("No major red flags detected - continue routine monitoring.")
        return recs

    def get_overview(self) -> dict:
        """Admin overview statistics."""
        if self.roster is None:
            return {"error": "Risk scores not loaded"}

        df = self.roster
        total = len(df)
        dropout_rate = float(df["Actual_Dropout"].mean())

        tier_counts = df["Risk_Tier"].value_counts().to_dict()
        by_dept = df.groupby("Department")["Risk_Probability"].mean().to_dict()
        by_year = df.groupby("Semester")["Risk_Probability"].mean().to_dict()

        return {
            "total_students": total,
            "dropout_rate": round(dropout_rate, 4),
            "risk_distribution": {
                "High": tier_counts.get("High", 0),
                "Medium": tier_counts.get("Medium", 0),
                "Low": tier_counts.get("Low", 0),
            },
            "risk_by_department": by_dept,
            "risk_by_year": by_year,
        }

    def get_faculty_list(self, department: str, semester: str = None) -> list:
        """Get at-risk students for a department."""
        if self.roster is None:
            return []

        df = self.roster[self.roster["Department"] == department]
        if semester and semester != "All":
            df = df[df["Semester"] == semester]

        at_risk = df[df["Risk_Tier"].isin(["High", "Medium"])].sort_values(
            "Risk_Probability", ascending=False
        ).head(25)

        return [
            {
                "student_id": int(r["Student_ID"]),
                "semester": r["Semester"],
                "attendance": _safe_number(r["Attendance_Rate"]),
                "gpa": _safe_number(r["GPA"]),
                "stress": _optional_number(r["Stress_Index"]),
                "risk_probability": _safe_number(r["Risk_Probability"]),
                "risk_tier": r["Risk_Tier"],
            }
            for _, r in at_risk.iterrows()
        ]

    def get_faculty_summary(self, department: str, semester: str = None) -> dict:
        """Risk-tier counts for a whole department (optionally one year).

        The watchlist table is capped at the top 25 at-risk students, so its
        length cannot drive the stats row without under-reporting. This mirrors
        the same filters and counts every tier.
        """
        if self.roster is None:
            return {
                "total_students": 0, "high": 0, "medium": 0, "low": 0, "at_risk": 0,
            }

        df = self.roster[self.roster["Department"] == department]
        if semester and semester != "All":
            df = df[df["Semester"] == semester]

        tiers = df["Risk_Tier"].value_counts().to_dict()
        high = int(tiers.get("High", 0))
        medium = int(tiers.get("Medium", 0))
        low = int(tiers.get("Low", 0))
        return {
            "total_students": int(len(df)),
            "high": high,
            "medium": medium,
            "low": low,
            "at_risk": high + medium,
        }


# Singleton instance
model_service = ModelService()
