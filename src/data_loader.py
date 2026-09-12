"""
Data Loader - Loads and validates raw CSV data against the pipeline config.
"""
import pandas as pd
import yaml
import os
from pathlib import Path


def load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def load_raw_data(config: dict) -> pd.DataFrame:
    raw_path = config["dataset"]["raw_path"]
    if not os.path.exists(raw_path):
        raise FileNotFoundError(
            f"Raw dataset not found at: {raw_path}\n"
            "Please ensure the file exists at the expected path."
        )

    df = pd.read_csv(raw_path)
    print(f"[DataLoader] Loaded dataset: {raw_path}")
    print(f"[DataLoader] Shape: {df.shape}")
    return df


def validate_data(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Checks schema, expected columns, and prints a missing-value summary."""
    target = config["target_column"]
    drop_cols = config.get("drop_columns", [])
    num_feats = config["numerical_features"]
    cat_feats = config["categorical_features"]

    expected_cols = set(num_feats + cat_feats + [target] + drop_cols)
    actual_cols = set(df.columns.tolist())

    missing_cols = expected_cols - actual_cols
    extra_cols = actual_cols - expected_cols

    if missing_cols:
        print(f"[DataLoader] WARNING: Expected columns not found: {missing_cols}")
    if extra_cols:
        print(f"[DataLoader] INFO: Extra columns found (will be ignored): {extra_cols}")

    if target not in df.columns:
        raise ValueError(f"Target column '{target}' not found in dataset!")

    # Print missing value summary
    print("\n[DataLoader] Missing Values Summary:")
    missing_summary = df.isnull().sum()
    missing_summary = missing_summary[missing_summary > 0]
    if len(missing_summary) == 0:
        print("  No missing values detected.")
    else:
        for col, count in missing_summary.items():
            pct = count / len(df) * 100
            print(f"  - {col}: {count} ({pct:.1f}%)")

    print(f"\n[DataLoader] Target distribution:")
    print(df[target].value_counts(normalize=True).round(3).to_string())

    return df
