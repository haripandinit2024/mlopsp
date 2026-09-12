"""
Trainer - Selects, trains, and evaluates the dropout prediction model.
"""
import pickle
import os
import json
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)
try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False


def build_model(config: dict):
    """Instantiate classifier based on config."""
    model_cfg = config["model"]
    mtype = model_cfg["type"]
    seed = model_cfg["random_state"]
    cw = model_cfg.get("class_weight", None)

    if mtype == "random_forest":
        model = RandomForestClassifier(
            n_estimators=model_cfg.get("n_estimators", 100),
            max_depth=model_cfg.get("max_depth", None),
            min_samples_split=model_cfg.get("min_samples_split", 2),
            class_weight=cw,
            random_state=seed,
            n_jobs=-1
        )
    elif mtype == "gradient_boosting":
        model = GradientBoostingClassifier(
            n_estimators=model_cfg.get("n_estimators", 100),
            max_depth=model_cfg.get("max_depth", 3),
            random_state=seed
        )
    elif mtype == "logistic_regression":
        model = LogisticRegression(
            class_weight=cw,
            random_state=seed,
            max_iter=1000
        )
    elif mtype == "xgboost":
        if not XGBOOST_AVAILABLE:
            raise ImportError("XGBoost not installed. Install with: pip install xgboost")
        scale_pos_weight = 1
        if cw == "balanced":
            # Calculate scale_pos_weight for class imbalance
            scale_pos_weight = (model_cfg.get("n_estimators", 100) * 2)  # Approximate adjustment
        model = XGBClassifier(
            n_estimators=model_cfg.get("n_estimators", 100),
            max_depth=model_cfg.get("max_depth", 6),
            learning_rate=model_cfg.get("learning_rate", 0.1),
            random_state=seed,
            scale_pos_weight=scale_pos_weight if cw == "balanced" else 1,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0
        )
    else:
        raise ValueError(f"Unknown model type: {mtype}. Supported: random_forest, gradient_boosting, logistic_regression, xgboost")

    return model


def train(model, X_train: pd.DataFrame, y_train: pd.Series) -> object:
    print(f"\n[Trainer] Training {type(model).__name__} ...")
    model.fit(X_train, y_train)
    print(f"[Trainer] Training complete.")
    return model


def evaluate(model, X: pd.DataFrame, y: pd.Series, split_name: str = "Val") -> dict:
    """Compute and print classification metrics."""
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else y_pred.astype(float)

    acc = accuracy_score(y, y_pred)
    prec = precision_score(y, y_pred, zero_division=0)
    rec = recall_score(y, y_pred, zero_division=0)
    f1 = f1_score(y, y_pred, zero_division=0)
    auc = roc_auc_score(y, y_prob)
    cm = confusion_matrix(y, y_pred).tolist()

    metrics = {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(auc, 4),
        "confusion_matrix": cm
    }

    print(f"\n[Trainer] {split_name} Metrics:")
    print(f"  Accuracy  : {acc:.4f}")
    print(f"  Precision : {prec:.4f}")
    print(f"  Recall    : {rec:.4f}")
    print(f"  F1 Score  : {f1:.4f}")
    print(f"  ROC-AUC   : {auc:.4f}")
    print(f"\n[Trainer] Classification Report ({split_name}):")
    print(classification_report(y, y_pred, target_names=["Enrolled", "Dropout"]))

    return metrics


def save_model(model, config: dict):
    out_cfg = config["output"]
    os.makedirs(out_cfg["model_dir"], exist_ok=True)
    path = os.path.join(out_cfg["model_dir"], out_cfg["model_filename"])
    with open(path, "wb") as f:
        pickle.dump(model, f)
    print(f"\n[Trainer] Model saved to: {path}")
    return path


def save_metrics(metrics_dict: dict, config: dict):
    out_cfg = config["output"]
    path = os.path.join(out_cfg["model_dir"], out_cfg["metrics_filename"])
    with open(path, "w") as f:
        json.dump(metrics_dict, f, indent=2)
    print(f"[Trainer] Metrics saved to: {path}")
