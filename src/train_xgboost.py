"""
XGBoost Training Script — Student Dropout Risk Prediction
============================================================
Builds on preprocessing_pipeline.py. Trains, tunes, and evaluates an
XGBoost classifier on either dataset (v3 or the UCI-style student_data.csv).

Usage:
    python train_xgboost.py --dataset v3
    python train_xgboost.py --dataset student_data
    python train_xgboost.py --dataset v3 --tune       # also run hyperparameter search
"""

import argparse
import os
import sys
import joblib
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
from sklearn.metrics import (
    classification_report, roc_auc_score, precision_recall_curve,
    confusion_matrix, RocCurveDisplay
)

# Allow imports from the project root when run as `python src/train_xgboost.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Reuse the exact same preprocessing used to build train/test splits,
# so there's no mismatch between how features were engineered/scaled here
# vs. wherever this model eventually gets deployed.
from src.preprocessing_pipeline import preprocess_v3, preprocess_student_data, RANDOM_STATE


# ------------------------------------------------------------
# Step 1: Get preprocessed, leakage-safe splits
# ------------------------------------------------------------
def load_data(dataset: str):
    """
    Calls the appropriate preprocessing function and returns:
        X_train, X_test  -> already imputed / scaled / encoded (numpy arrays)
        y_train, y_test  -> target labels (y_train is already SMOTE-resampled)
        preprocessor     -> the fitted ColumnTransformer (needed later for
                             feature names / inspecting importances)
    """
    if dataset == "v3":
        # Primary dataset: 10,000 rows, explicit "Dropout" column already exists.
        return preprocess_v3()
    elif dataset == "student_data":
        # UCI-style dataset: 395 rows, "Dropout" is a derived proxy from G3.
        return preprocess_student_data()
    else:
        # Fail loudly rather than silently defaulting — wrong dataset name
        # would otherwise be a very confusing bug to track down later.
        raise ValueError("dataset must be 'v3' or 'student_data'")


# ------------------------------------------------------------
# Step 2: Baseline XGBoost model
# ------------------------------------------------------------
def train_baseline(X_train, y_train):
    """
    Trains a reasonable "default" XGBoost model — not tuned, just sane
    starting values. Good for a first sanity check before spending time
    on a full hyperparameter search.

    NOTE: no scale_pos_weight here — SMOTE already balanced the training
    set upstream (see preprocessing_pipeline.py). Stacking both correction
    methods (SMOTE + class weighting) tends to overcorrect and hurts
    precision, so pick one, not both.
    """
    model = XGBClassifier(
        n_estimators=300,        # number of boosting rounds (trees)
        max_depth=5,             # tree depth — controls model complexity/overfitting
        learning_rate=0.05,      # shrinkage — smaller = more robust but needs more trees
        subsample=0.8,           # fraction of rows sampled per tree (reduces overfitting)
        colsample_bytree=0.8,    # fraction of columns sampled per tree (same reason)
        eval_metric="logloss",   # internal metric XGBoost tracks during training
        random_state=RANDOM_STATE,  # reproducibility
        n_jobs=-1,               # use all available CPU cores
    )
    model.fit(X_train, y_train)
    return model


# ------------------------------------------------------------
# Step 3: Evaluate (recall on the dropout/at-risk class matters most)
# ------------------------------------------------------------
def evaluate(model, X_test, y_test, label="baseline"):
    """
    Prints precision/recall/F1 per class, overall ROC-AUC, and the
    confusion matrix. Accuracy alone is misleading here — a model that
    just predicts "no dropout" for everyone could still score high
    accuracy while catching zero at-risk students, which defeats the
    whole point of building this model.
    """
    y_pred = model.predict(X_test)              # hard 0/1 predictions at default 0.5 threshold
    y_proba = model.predict_proba(X_test)[:, 1]  # probability of the "Dropout" class

    print(f"\n=== Evaluation ({label}) ===")
    # classification_report gives precision/recall/F1 for both classes —
    # watch "Dropout" recall closely, since missing an at-risk student is
    # usually more costly than a false alarm.
    print(classification_report(y_test, y_pred, target_names=["No Dropout", "Dropout"]))
    print("ROC-AUC:", round(roc_auc_score(y_test, y_proba), 4))
    print("Confusion matrix:\n", confusion_matrix(y_test, y_pred))
    return y_proba  # returned so it can be reused for threshold tuning later


# ------------------------------------------------------------
# Step 4: Hyperparameter tuning (CV on training data only)
# ------------------------------------------------------------
def tune_model(X_train, y_train):
    """
    Searches over a range of hyperparameters using randomized search +
    stratified k-fold cross-validation. Randomized (not exhaustive grid)
    search because the parameter space here is large — random sampling
    finds good regions much faster than trying every combination.

    Cross-validation happens entirely within X_train/y_train — the test
    set is never touched during tuning, which keeps the final evaluation
    honest.
    """
    param_dist = {
        "n_estimators": [200, 300, 500, 700],       # more trees = more capacity, slower
        "max_depth": [3, 4, 5, 6, 8],                # deeper trees = more complex splits
        "learning_rate": [0.01, 0.03, 0.05, 0.1],    # step size shrinkage per tree
        "subsample": [0.6, 0.8, 1.0],                 # row sampling ratio per tree
        "colsample_bytree": [0.6, 0.8, 1.0],          # column sampling ratio per tree
        "min_child_weight": [1, 3, 5],                # min samples needed in a leaf (regularization)
        "gamma": [0, 0.1, 0.3],                       # min loss reduction to allow a further split
    }

    base = XGBClassifier(
        eval_metric="logloss",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    # Stratified so each fold keeps the same class ratio as the full
    # training set — important since we're dealing with a minority class.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    search = RandomizedSearchCV(
        base,
        param_distributions=param_dist,
        n_iter=40,               # number of random parameter combinations to try
        scoring="roc_auc",       # good default for imbalanced binary classification
        cv=cv,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=1,               # prints progress so long searches aren't silent
    )
    search.fit(X_train, y_train)
    print("\nBest params:", search.best_params_)
    print("Best CV ROC-AUC:", round(search.best_score_, 4))
    return search.best_estimator_  # the refit model using the best found params


# ------------------------------------------------------------
# Step 5: Feature importance
# ------------------------------------------------------------
def show_feature_importance(model, preprocessor, top_n=15):
    """
    Prints the top_n most important features by XGBoost's built-in
    "gain"-based importance. Useful for explaining to stakeholders
    *why* a student is flagged as at-risk (e.g. attendance rate,
    GPA decline, etc.) rather than treating the model as a black box.
    """
    try:
        # get_feature_names_out() reconstructs names like "num__GPA_Decline"
        # or "nom__Department_CS" from the fitted ColumnTransformer, so
        # importances map back to human-readable column names.
        feature_names = preprocessor.get_feature_names_out()
    except Exception:
        # Fallback in case the sklearn version doesn't support this method.
        feature_names = [f"f{i}" for i in range(len(model.feature_importances_))]

    importances = model.feature_importances_
    # argsort ascending, then reverse to get descending order, then take top_n.
    order = np.argsort(importances)[::-1][:top_n]

    print(f"\n=== Top {top_n} Features ===")
    for idx in order:
        print(f"{feature_names[idx]:<40s} {importances[idx]:.4f}")


# ------------------------------------------------------------
# Step 6: Threshold tuning — optimize for recall on the at-risk class
# ------------------------------------------------------------
def find_best_threshold(y_test, y_proba, min_recall=0.75):
    """
    XGBoost's default classification threshold is 0.5, but that's rarely
    the right cutoff for an imbalanced, high-stakes problem like this one.

    Scans all thresholds along the precision-recall curve and picks the
    one that gives the BEST precision while still guaranteeing recall
    stays at or above min_recall (i.e. "catch at least 75% of at-risk
    students, and among the students we flag, be as precise as possible").

    Adjust min_recall based on real-world cost: if missing an at-risk
    student is very costly (e.g. they don't get an intervention), push
    min_recall higher, even if it costs some precision (more false alarms).
    """
    # precision_recall_curve returns arrays one longer for precision/recall
    # than for thresholds, hence the [:-1] slicing below to align them.
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
    best_thresh, best_precision = 0.5, -1  # sensible fallback if nothing qualifies

    for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds):
        # Only consider thresholds that meet the minimum recall requirement,
        # then among those, keep the one with the highest precision.
        if r >= min_recall and p > best_precision:
            best_precision, best_thresh = p, t

    print(f"\nBest threshold for recall >= {min_recall}: {best_thresh:.3f} "
          f"(precision at that point: {best_precision:.3f})")
    return best_thresh


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
if __name__ == "__main__":
    # --dataset chooses which of the two preprocessing pipelines to run.
    # --tune is optional and off by default since hyperparameter search
    # takes noticeably longer than just fitting the baseline model.
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["v3", "student_data"], default="v3")
    parser.add_argument("--tune", action="store_true", help="Run hyperparameter search (slower)")
    args = parser.parse_args()

    print(f"Loading and preprocessing '{args.dataset}' dataset...")
    X_train, X_test, y_train, y_test, preprocessor = load_data(args.dataset)

    print("\nTraining baseline XGBoost model...")
    baseline_model = train_baseline(X_train, y_train)
    y_proba = evaluate(baseline_model, X_test, y_test, label="baseline")

    # Start with the baseline as the "final" model; overwrite it with the
    # tuned version only if --tune was passed.
    final_model = baseline_model
    if args.tune:
        print("\nRunning hyperparameter search (this can take a few minutes)...")
        final_model = tune_model(X_train, y_train)
        y_proba = evaluate(final_model, X_test, y_test, label="tuned")

    # These two run regardless of whether tuning happened, using whichever
    # model ended up in final_model.
    show_feature_importance(final_model, preprocessor)
    find_best_threshold(y_test, y_proba, min_recall=0.75)

    final_model.save_model("models/xgboost_dropout_model.json")
    joblib.dump(preprocessor, "models/preprocessor.joblib")
    print("\nModel saved to models/xgboost_dropout_model.json")
    print("Preprocessor saved to models/preprocessor.joblib")
