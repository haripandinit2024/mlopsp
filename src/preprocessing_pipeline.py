"""
preprocessing_pipeline.py
==========================
Shared preprocessing for the Student Dropout Risk project.

Provides:
    preprocess_v3()            -> for student_dropout_dataset_v3.csv (10,000 rows)
    preprocess_student_data()  -> for student_data.csv (UCI-style, 395 rows)

Both return: X_train, X_test, y_train, y_test, preprocessor
    - X_train / X_test are numpy arrays (already imputed/scaled/encoded)
    - y_train is SMOTE-resampled (balanced), y_test is left untouched
      (we always test on the real, imbalanced distribution)
    - preprocessor is the fitted ColumnTransformer (needed later to
      transform new/single-student records, and to recover feature names
      for importance plots)
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.model_selection import train_test_split
from imblearn.over_sampling import SMOTE

RANDOM_STATE = 42
DATA_DIR = "dataset/raw"  # CSVs live in ./dataset/raw relative to wherever you run the scripts from


# ------------------------------------------------------------
# Dataset v3 (10,000 rows, explicit Dropout column)
# ------------------------------------------------------------
NUMERIC_COLS_V3 = [
    "Age", "Family_Income", "Study_Hours_per_Day", "Attendance_Rate",
    "Assignment_Delay_Days", "Travel_Time_Minutes", "Stress_Index",
    "GPA", "Semester_GPA", "CGPA",
    # engineered features
    "GPA_Decline", "Low_Attendance_Flag", "Engagement_Score",
]
CATEGORICAL_COLS_V3 = [
    "Gender", "Internet_Access", "Part_Time_Job", "Scholarship",
    "Department", "Semester", "Parental_Education",
]


def _engineer_features_v3(df: pd.DataFrame) -> pd.DataFrame:
    """Adds the 3 engineered features used by the model.
    Must match exactly what test_xgboost_model.py recreates for a single
    new student, or the model will see a different column layout.
    """
    df = df.copy()
    df["GPA_Decline"] = df["GPA"] - df["Semester_GPA"]
    df["Low_Attendance_Flag"] = (df["Attendance_Rate"] < 75).astype(int)
    df["Engagement_Score"] = (
        df["Study_Hours_per_Day"] - 0.1 * df["Assignment_Delay_Days"]
    )
    return df


def build_preprocessor_v3() -> ColumnTransformer:
    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, NUMERIC_COLS_V3),
        ("cat", categorical_pipe, CATEGORICAL_COLS_V3),
    ])


def preprocess_v3(csv_path: str = None, test_size: float = 0.2):
    csv_path = csv_path or f"{DATA_DIR}/student_dropout_dataset_v3.csv"
    df = pd.read_csv(csv_path)
    df = _engineer_features_v3(df)

    feature_cols = NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3
    X = df[feature_cols]
    y = df["Dropout"].astype(int)

    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_STATE, stratify=y
    )

    preprocessor = build_preprocessor_v3()
    X_train = preprocessor.fit_transform(X_train_raw)
    X_test = preprocessor.transform(X_test_raw)

    # Balance the TRAINING set only (test set must reflect real-world skew)
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train, y_train = smote.fit_resample(X_train, y_train)

    return X_train, X_test, y_train.to_numpy() if hasattr(y_train, "to_numpy") else y_train, \
        y_test.to_numpy(), preprocessor


# ------------------------------------------------------------
# Dataset student_data.csv (UCI-style, 395 rows, no Dropout column —
# derived as a proxy: G3 < 10 counts as "dropout risk")
# ------------------------------------------------------------
NUMERIC_COLS_STUDENT = [
    "age", "Medu", "Fedu", "traveltime", "studytime", "failures",
    "famrel", "freetime", "goout", "Dalc", "Walc", "health", "absences",
    "G1", "G2",
]
CATEGORICAL_COLS_STUDENT = [
    "school", "sex", "address", "famsize", "Pstatus", "Mjob", "Fjob",
    "reason", "guardian", "schoolsup", "famsup", "paid", "activities",
    "nursery", "higher", "internet", "romantic",
]


def build_preprocessor_student() -> ColumnTransformer:
    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, NUMERIC_COLS_STUDENT),
        ("cat", categorical_pipe, CATEGORICAL_COLS_STUDENT),
    ])


def preprocess_student_data(csv_path: str = None, test_size: float = 0.2):
    csv_path = csv_path or f"{DATA_DIR}/student_data.csv"
    df = pd.read_csv(csv_path)

    # G3 is final grade (0-20). G3 < 10 is a standard UCI "fail" proxy for
    # dropout risk in this dataset (it has no explicit dropout label).
    df["Dropout"] = (df["G3"] < 10).astype(int)

    feature_cols = NUMERIC_COLS_STUDENT + CATEGORICAL_COLS_STUDENT
    X = df[feature_cols]
    y = df["Dropout"]

    X_train_raw, X_test_raw, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=RANDOM_STATE, stratify=y
    )

    preprocessor = build_preprocessor_student()
    X_train = preprocessor.fit_transform(X_train_raw)
    X_test = preprocessor.transform(X_test_raw)

    smote = SMOTE(random_state=RANDOM_STATE)
    X_train, y_train = smote.fit_resample(X_train, y_train)

    return X_train, X_test, y_train, y_test.to_numpy(), preprocessor
