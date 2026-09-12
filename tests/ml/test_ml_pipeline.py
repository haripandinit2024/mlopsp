"""
ML pipeline tests: artifacts, preprocessing/inference parity, determinism,
edge cases and roster consistency.
"""
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from tests.base import AppTestCase, PROJECT_ROOT
from backend.model_service import ModelService

MODELS = PROJECT_ROOT / "models"
MODEL_PATH = MODELS / "xgboost_dropout_model.json"
PREP_PATH = MODELS / "preprocessor.joblib"
ROSTER = PROJECT_ROOT / "dataset" / "processed" / "student_risk_scores.csv"

BASE_PROFILE = {
    "GPA": 2.5, "Attendance_Rate": 70, "Stress_Index": 8,
    "Study_Hours_per_Day": 2, "Semester_GPA": 3.0, "Assignment_Delay_Days": 6,
    "Age": 20, "Family_Income": 30000, "Travel_Time_Minutes": 30, "CGPA": 3.0,
    "Gender": "Male", "Internet_Access": "Yes", "Part_Time_Job": "No",
    "Scholarship": "No", "Department": "CS", "Semester": "Year 1",
    "Parental_Education": "Bachelor",
}


class TestArtifacts(unittest.TestCase):
    def test_model_and_preprocessor_exist(self):
        self.assertTrue(MODEL_PATH.exists(), f"missing {MODEL_PATH}")
        self.assertTrue(PREP_PATH.exists(), f"missing {PREP_PATH}")

    def test_model_loads_and_exposes_classes(self):
        model = XGBClassifier()
        model.load_model(str(MODEL_PATH))
        self.assertEqual(list(model.classes_), [0, 1])

    def test_preprocessor_has_feature_names(self):
        prep = joblib.load(str(PREP_PATH))
        names = prep.get_feature_names_out()
        self.assertGreater(len(names), 0)
        self.assertTrue(any(n.startswith("num__") for n in names))
        self.assertTrue(any(n.startswith("cat__") for n in names))


class TestInferenceParity(AppTestCase):
    """
    The exact pipeline used at training time must be the one used at
    inference time, otherwise predictions are meaningless.
    """

    def _service(self):
        svc = ModelService()
        svc.load()
        return svc

    def test_service_uses_real_model_not_mock(self):
        svc = self._service()
        self.assertIsNotNone(svc.model, "model not loaded -> falling back to mock")
        self.assertIsNotNone(svc.preprocessor)

    def test_service_output_matches_direct_model_call(self):
        from src.preprocessing_pipeline import (
            NUMERIC_COLS_V3, CATEGORICAL_COLS_V3,
        )

        svc = self._service()
        profile = dict(BASE_PROFILE)

        # Expected value computed independently from the service.
        df = pd.DataFrame([profile])
        df["GPA_Decline"] = df["GPA"] - df["Semester_GPA"]
        df["Low_Attendance_Flag"] = (df["Attendance_Rate"] < 75).astype(int)
        df["Engagement_Score"] = df["Study_Hours_per_Day"] - 0.1 * df["Assignment_Delay_Days"]
        X = svc.preprocessor.transform(df[NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3])
        expected = float(svc.model.predict_proba(X)[:, 1][0])

        actual = svc.predict_custom(profile)["risk_probability"]
        self.assertAlmostEqual(actual, expected, places=6)

    def test_mock_fallback_is_not_silently_returned_for_valid_input(self):
        """The heuristic fallback returns a 4-dp rounded value; the real model does not."""
        svc = self._service()
        real = svc.predict_custom(dict(BASE_PROFILE))["risk_probability"]
        mock = svc._mock_predict(dict(BASE_PROFILE))["risk_probability"]
        self.assertNotAlmostEqual(real, mock, places=4,
                                  msg="valid profile returned the mock heuristic")

    def test_malformed_input_never_raises(self):
        """
        Required behaviour: malformed input must either be rejected or degrade
        safely. It must never propagate an exception out of predict_custom.
        Currently the mock fallback itself does arithmetic on the raw value and
        raises TypeError for non-numeric input.
        """
        svc = self._service()
        for bad in ("not-a-number", None, [1, 2], {"x": 1}):
            with self.subTest(gpa=bad):
                try:
                    result = svc.predict_custom(dict(BASE_PROFILE, GPA=bad))
                except Exception as exc:  # noqa: BLE001 - that is the defect
                    self.fail(f"predict_custom raised {type(exc).__name__}: {exc}")
                self.assertIn(result["risk_tier"], {"Low", "Medium", "High"})


class TestDeterminismAndSanity(AppTestCase):
    def setUp(self):
        super().setUp()
        self.svc = ModelService()
        self.svc.load()

    def test_repeated_predictions_are_identical(self):
        values = {self.svc.predict_custom(dict(BASE_PROFILE))["risk_probability"]
                  for _ in range(5)}
        self.assertEqual(len(values), 1)

    def test_strong_profile_scores_lower_than_weak_profile(self):
        strong = dict(BASE_PROFILE, GPA=3.9, Semester_GPA=3.9, CGPA=3.9,
                      Attendance_Rate=98, Stress_Index=1,
                      Study_Hours_per_Day=7, Assignment_Delay_Days=0)
        weak = dict(BASE_PROFILE, GPA=1.0, Semester_GPA=3.0, CGPA=1.1,
                    Attendance_Rate=45, Stress_Index=10,
                    Study_Hours_per_Day=1, Assignment_Delay_Days=10)
        r_strong = self.svc.predict_custom(strong)["risk_probability"]
        r_weak = self.svc.predict_custom(weak)["risk_probability"]
        self.assertLess(r_strong, r_weak,
                        "model does not rank a weak profile as riskier")

    def test_probability_always_within_unit_interval(self):
        profiles = [
            dict(BASE_PROFILE),
            dict(BASE_PROFILE, GPA=0.0, Attendance_Rate=0),
            dict(BASE_PROFILE, GPA=4.0, Attendance_Rate=100),
            dict(BASE_PROFILE, GPA=2.0, Attendance_Rate=75, Stress_Index=0),
        ]
        for p in profiles:
            with self.subTest(p=p):
                prob = self.svc.predict_custom(p)["risk_probability"]
                self.assertGreaterEqual(prob, 0.0)
                self.assertLessEqual(prob, 1.0)

    def test_unseen_categorical_value_does_not_crash(self):
        p = dict(BASE_PROFILE, Department="Unknown Dept", Semester="Year 42",
                 Parental_Education="Doctorate", Internet_Access="Maybe")
        self.assertLessEqual(self.svc.predict_custom(p)["risk_probability"], 1.0)

    def test_boundary_values_are_accepted(self):
        p = dict(BASE_PROFILE, GPA=0.0, Attendance_Rate=0, Stress_Index=0,
                 Study_Hours_per_Day=0, Assignment_Delay_Days=0)
        self.assertLessEqual(self.svc.predict_custom(p)["risk_probability"], 1.0)


class TestRosterConsistency(AppTestCase):
    def test_roster_file_present_and_well_formed(self):
        self.assertTrue(ROSTER.exists())
        df = pd.read_csv(ROSTER)
        self.assertEqual(len(df), 10000)
        for col in ("Student_ID", "Department", "Semester", "Attendance_Rate",
                    "GPA", "Stress_Index", "Actual_Dropout",
                    "Risk_Probability", "Risk_Tier"):
            self.assertIn(col, df.columns)
        self.assertFalse(df["Risk_Probability"].isna().any())
        self.assertTrue(df["Risk_Probability"].between(0, 1).all())

    def test_roster_tier_labels_match_thresholds(self):
        df = pd.read_csv(ROSTER)
        threshold = 0.243

        def expected(p):
            return "High" if p >= 0.5 else ("Medium" if p >= threshold else "Low")

        mismatches = (df["Risk_Tier"] != df["Risk_Probability"].map(expected)).sum()
        self.assertEqual(mismatches, 0,
                         f"{mismatches} roster rows have inconsistent tier labels")

    def test_roster_probabilities_match_current_model(self):
        """
        The roster is a cached artifact. If it was produced by a different
        model version than the one serving live predictions, student detail
        views and the manual-prediction form will disagree.
        """
        from src.preprocessing_pipeline import (
            _engineer_features_v3, NUMERIC_COLS_V3, CATEGORICAL_COLS_V3, DATA_DIR,
        )

        model = XGBClassifier()
        model.load_model(str(MODEL_PATH))
        prep = joblib.load(str(PREP_PATH))

        raw = pd.read_csv(f"{DATA_DIR}/student_dropout_dataset_v3.csv").head(200)
        raw = _engineer_features_v3(raw)
        probs = model.predict_proba(prep.transform(raw[NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3]))[:, 1]
        roster = pd.read_csv(ROSTER).set_index("Student_ID")
        cached = roster.loc[raw["Student_ID"], "Risk_Probability"].to_numpy()
        max_delta = float(np.abs(probs - cached).max())
        self.assertLess(max_delta, 0.01,
                        f"roster is stale vs the deployed model (max delta {max_delta:.3f})")


class TestDataQuality(unittest.TestCase):
    def setUp(self):
        self.df = pd.read_csv(PROJECT_ROOT / "dataset/raw/student_dropout_dataset_v3.csv")

    def test_no_duplicate_student_ids(self):
        self.assertEqual(int(self.df["Student_ID"].duplicated().sum()), 0)

    def test_no_duplicate_records(self):
        self.assertEqual(int(self.df.drop(columns=["Student_ID"]).duplicated().sum()), 0)

    def test_target_is_binary(self):
        self.assertEqual(sorted(self.df["Dropout"].unique().tolist()), [0, 1])

    def test_target_imbalance_is_documented(self):
        rate = self.df["Dropout"].mean()
        self.assertGreater(rate, 0.15)
        self.assertLess(rate, 0.35)

    def test_domain_ranges_are_valid(self):
        """Range checks ignore NULLs (which are legitimate and imputed downstream)."""
        self.assertTrue(self.df["Attendance_Rate"].dropna().between(0, 100).all())
        self.assertTrue(self.df["GPA"].dropna().between(0, 4).all())
        self.assertTrue(self.df["Stress_Index"].dropna().between(0, 10).all())

    def test_missing_values_exist_and_are_bounded(self):
        missing_pct = self.df.isna().mean()
        self.assertGreater(missing_pct.max(), 0, "expected some missing values")
        self.assertLess(missing_pct.max(), 0.10, "missing rate unexpectedly high")


class TestLeakage(unittest.TestCase):
    def test_engineered_features_contain_no_target(self):
        from src.preprocessing_pipeline import (
            NUMERIC_COLS_V3, CATEGORICAL_COLS_V3, _engineer_features_v3,
        )

        df = _engineer_features_v3(pd.read_csv(
            PROJECT_ROOT / "dataset/raw/student_dropout_dataset_v3.csv").head(500))
        for col in NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3:
            self.assertNotIn(col, ("Dropout", "Student_ID"))
            self.assertIn(col, df.columns)

    def test_no_row_overlap_between_train_and_test(self):
        from src.preprocessing_pipeline import (
            NUMERIC_COLS_V3, CATEGORICAL_COLS_V3, _engineer_features_v3,
            RANDOM_STATE,
        )
        from sklearn.model_selection import train_test_split

        df = _engineer_features_v3(pd.read_csv(
            PROJECT_ROOT / "dataset/raw/student_dropout_dataset_v3.csv"))
        feat = NUMERIC_COLS_V3 + CATEGORICAL_COLS_V3
        Xtr, Xte = train_test_split(df[feat], test_size=0.2,
                                    random_state=RANDOM_STATE, stratify=df["Dropout"])[:2]
        tr = set(map(tuple, Xtr.fillna("__NA__").astype(str).values))
        overlap = sum(1 for r in Xte.fillna("__NA__").astype(str).values
                      if tuple(r) in tr)
        self.assertEqual(overlap, 0, "identical rows appear in train and test")

    def test_nothing_is_fitted_before_the_split(self):
        """
        Requirement: no transformer may be fitted on data that ends up in the
        test split. The config-driven DropoutPreprocessor previously imputed
        the whole dataframe before calling split(), leaking test-set medians
        into training.
        """
        import inspect

        from src.preprocess import DropoutPreprocessor

        src_text = inspect.getsource(DropoutPreprocessor.fit_transform)
        split_pos = src_text.index("self.split(")
        fit_pos = src_text.index("fit=True")
        self.assertGreater(fit_pos, split_pos,
                           "a transformer is fitted before the train/test split (leakage)")

    def test_val_and_test_are_only_transformed(self):
        """After splitting, val/test must use fit=False for imputation."""
        import inspect

        from src.preprocess import DropoutPreprocessor

        src_text = inspect.getsource(DropoutPreprocessor.fit_transform)
        split_pos = src_text.index("self.split(")
        after = src_text[split_pos:]
        self.assertIn("_impute_numerical(X_val, fit=False)", after)
        self.assertIn("_impute_numerical(X_test, fit=False)", after)
        self.assertIn("_impute_categorical(X_val, fit=False)", after)
        self.assertIn("_impute_categorical(X_test, fit=False)", after)

    def test_config_pipeline_train_and_test_are_disjoint(self):
        """End-to-end: the persisted splits must not share feature rows."""
        import pandas as pd

        train = pd.read_csv(PROJECT_ROOT / "dataset/processed/train.csv")
        test = pd.read_csv(PROJECT_ROOT / "dataset/processed/test.csv")
        common = [c for c in train.columns if c in test.columns]
        tr = set(map(tuple, train[common].round(6).astype(str).values))
        overlap = sum(1 for r in test[common].round(6).astype(str).values
                      if tuple(r) in tr)
        self.assertEqual(overlap, 0, "train/test splits share rows")


if __name__ == "__main__":
    unittest.main()
