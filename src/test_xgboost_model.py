"""
Test / Evaluate a Trained XGBoost Model
==========================================
Loads a saved model (from xgboost_dropout_model.json) and tests it in
two ways:
  1. On the held-out test set (to check real performance metrics)
  2. On a single new/hypothetical student (to see a live prediction)

Requires that you've already run train_xgboost_simple.py with the
"Save the trained model" step uncommented, so xgboost_dropout_model.json
exists on disk.
"""

import os
import sys
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import (
    classification_report, roc_auc_score, confusion_matrix,
    ConfusionMatrixDisplay
)

# Allow imports from the project root when run as `python src/test_xgboost_model.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocessing_pipeline import preprocess_v3


# ------------------------------------------------------------
# STEP 1: Rebuild the same test split used during training
# ------------------------------------------------------------
# preprocess_v3() is deterministic (fixed RANDOM_STATE), so calling it
# again reproduces the exact same train/test split and preprocessing —
# this guarantees we're testing on the same held-out rows the model
# never saw during training.
X_train, X_test, y_train, y_test, preprocessor = preprocess_v3()


# ------------------------------------------------------------
# STEP 2: Load the saved model from disk
# ------------------------------------------------------------
# We create an empty XGBClassifier first, then load the saved weights/
# structure into it — this avoids retraining from scratch.
model = XGBClassifier()
model.load_model("models/xgboost_dropout_model.json")
print("Model loaded successfully.\n")


# ------------------------------------------------------------
# STEP 3: Test on the held-out test set
# ------------------------------------------------------------
# This is the real test of how well the model generalizes — X_test was
# never seen during training.
y_pred = model.predict(X_test)               # hard 0/1 predictions
y_proba = model.predict_proba(X_test)[:, 1]   # probability of "Dropout"

print("=== Test Set Performance ===")
print(classification_report(y_test, y_pred, target_names=["No Dropout", "Dropout"]))
print("ROC-AUC:", round(roc_auc_score(y_test, y_proba), 4))

cm = confusion_matrix(y_test, y_pred)
print("\nConfusion Matrix:")
print(cm)
print("""
Reading the confusion matrix:
    [ [True Negative,  False Positive],
      [False Negative, True Positive] ]
- False Negatives = at-risk students the model MISSED (most costly error)
- False Positives = students flagged as at-risk who weren't (false alarm)
""")


# ------------------------------------------------------------
# STEP 4 (optional): Visualize the confusion matrix
# ------------------------------------------------------------
# Comment out if you don't have a display / are running headless.
try:
    import matplotlib.pyplot as plt
    disp = ConfusionMatrixDisplay(confusion_matrix=cm,
                                   display_labels=["No Dropout", "Dropout"])
    pass
except ImportError:
    print("(matplotlib not installed — skipping plot)")


# ------------------------------------------------------------
# STEP 5: Test on a single new/hypothetical student
# ------------------------------------------------------------
# This shows how you'd use the model on ONE new record rather than the
# whole test set — e.g. if a new student's data comes in and you want to
# score their dropout risk right now.
#
# IMPORTANT: the raw input must go through the SAME preprocessor that was
# fit on the training data (same imputer medians, same scaler mean/std,
# same one-hot categories) — never re-fit a new preprocessor on new data.

new_student = pd.DataFrame([{
    "Age": 20,
    "Family_Income": 32000,
    "Study_Hours_per_Day": 1.5,
    "Attendance_Rate": 62,
    "Assignment_Delay_Days": 6,
    "Travel_Time_Minutes": 45,
    "Stress_Index": 7,
    "GPA": 2.1,
    "Semester_GPA": 1.8,
    "CGPA": 2.0,
    "Gender": "Male",
    "Internet_Access": "Yes",
    "Part_Time_Job": "Yes",
    "Scholarship": "No",
    "Department": "CS",
    "Semester": 4,
    "Parental_Education": "High School",
}])

# Recreate the same engineered features used in preprocessing_pipeline.py
# (GPA_Decline, Low_Attendance_Flag, Engagement_Score) before transforming —
# skipping this step would mean the model sees different columns than it
# was trained on.
new_student["GPA_Decline"] = new_student["GPA"] - new_student["Semester_GPA"]
new_student["Low_Attendance_Flag"] = (new_student["Attendance_Rate"] < 75).astype(int)
new_student["Engagement_Score"] = (
    new_student["Study_Hours_per_Day"] - 0.1 * new_student["Assignment_Delay_Days"]
)

# Use transform() (NOT fit_transform()) — we're applying the preprocessor
# that was already fit on training data, not fitting a new one.
new_student_proc = preprocessor.transform(new_student)

risk_proba = model.predict_proba(new_student_proc)[:, 1][0]
risk_label = model.predict(new_student_proc)[0]

print("\n=== New Student Prediction ===")
print(f"Predicted class: {'Dropout risk' if risk_label == 1 else 'No dropout risk'}")
print(f"Dropout probability: {risk_proba:.2%}")
