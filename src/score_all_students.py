"""
score_all_students.py
=======================
Runs the trained model over EVERY student in student_dropout_dataset_v3.csv
(not just the test split) and writes out a risk-scored roster used by the
Faculty and Admin terminal dashboards.

Run this once after train_xgboost.py --dataset v3 has produced:
    xgboost_dropout_model.json
    preprocessor.joblib

Output: student_risk_scores.csv
    Student_ID, Department, Semester, Gender, Attendance_Rate, GPA, CGPA,
    Stress_Index, Actual_Dropout, Risk_Probability, Risk_Tier
"""

import os
import sys
import joblib
import pandas as pd
from xgboost import XGBClassifier

# Allow imports from the project root when run as `python src/score_all_students.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocessing_pipeline import (
    _engineer_features_v3, NUMERIC_COLS_V3, CATEGORICAL_COLS_V3, DATA_DIR
)

# Tier cutoffs come from the shared rules module so the roster this script
# writes always agrees with the live prediction API.
from src.risk_rules import MEDIUM_THRESHOLD as RISK_THRESHOLD, risk_tier  # noqa: F401


def main():
    df = pd.read_csv(f"{DATA_DIR}/student_dropout_dataset_v3.csv")
    df_feat = _engineer_features_v3(df)

    preprocessor = joblib.load("models/preprocessor.joblib")
    model = XGBClassifier()
    model.load_model("models/xgboost_dropout_model.json")

    X = preprocessor.transform(df_feat[NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3])
    proba = model.predict_proba(X)[:, 1]

    out = df[[
        "Student_ID", "Department", "Semester", "Gender", "Attendance_Rate",
        "GPA", "CGPA", "Stress_Index", "Dropout"
    ]].copy()
    out.rename(columns={"Dropout": "Actual_Dropout"}, inplace=True)
    out["Risk_Probability"] = proba.round(4)
    out["Risk_Tier"] = out["Risk_Probability"].apply(risk_tier)

    out.to_csv("dataset/processed/student_risk_scores.csv", index=False)
    print(f"Scored {len(out)} students -> dataset/processed/student_risk_scores.csv")
    print(out["Risk_Tier"].value_counts())


if __name__ == "__main__":
    main()
