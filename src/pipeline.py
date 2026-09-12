"""
Pipeline - Main orchestrator that runs the full MLOps pipeline:
  Load -> Validate -> Preprocess -> Train -> Evaluate -> Save
"""
import os
import sys
import time
import pandas as pd

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_loader import load_config, load_raw_data, validate_data
from src.preprocess import DropoutPreprocessor
from src.train import build_model, train, evaluate, save_model, save_metrics

BANNER = """
╔══════════════════════════════════════════════════════════╗
║       Student Dropout Prediction - MLOps Pipeline        ║
╚══════════════════════════════════════════════════════════╝
"""


def load_pipeline_config(config_path: str = "config/config.yaml") -> dict:
    """Load and print the configuration once for every stage."""
    print(BANNER)
    print("=" * 60)
    print("STEP 1: Loading configuration")
    print("=" * 60)
    config = load_config(config_path)
    print(f"  Config loaded from: {config_path}")
    print(f"  Model type: {config['model']['type']}")
    print(f"  Target column: {config['target_column']}")
    return config


def preprocess_data(config_path: str = "config/config.yaml"):
    """Load raw data, preprocess it, and persist processed artifacts."""
    start = time.time()
    config = load_pipeline_config(config_path)

    print("\n" + "=" * 60)
    print("STEP 2: Loading and validating data")
    print("=" * 60)
    df = load_raw_data(config)
    df = validate_data(df, config)

    print("\n" + "=" * 60)
    print("STEP 3: Preprocessing data")
    print("=" * 60)
    preprocessor = DropoutPreprocessor(config)
    train_split, val_split, test_split = preprocessor.fit_transform(df)

    X_train, y_train = train_split
    X_val, y_val = val_split
    X_test, y_test = test_split

    processed_dir = config["dataset"]["processed_dir"]
    os.makedirs(processed_dir, exist_ok=True)
    train_frame = X_train.copy()
    train_frame[config["target_column"]] = y_train.values
    val_frame = X_val.copy()
    val_frame[config["target_column"]] = y_val.values
    test_frame = X_test.copy()
    test_frame[config["target_column"]] = y_test.values

    train_frame.to_csv(f"{processed_dir}/train.csv", index=False)
    val_frame.to_csv(f"{processed_dir}/val.csv", index=False)
    test_frame.to_csv(f"{processed_dir}/test.csv", index=False)
    print(f"\n[Pipeline] Saved processed splits to: {processed_dir}/")

    preprocessor_path = os.path.join(
        config["output"]["model_dir"],
        config["output"]["preprocessor_filename"]
    )
    preprocessor.save(preprocessor_path)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"✅ Preprocessing complete in {elapsed:.1f}s")
    print(f"{'='*60}")

    return config


def _load_processed_split(path: str) -> tuple[pd.DataFrame, pd.Series]:
    frame = pd.read_csv(path)
    y = frame.pop("Dropout")
    return frame, y


def train_model(config_path: str = "config/config.yaml"):
    """Load processed splits, train the model, evaluate it, and save artifacts."""
    start = time.time()
    config = load_pipeline_config(config_path)

    processed_dir = config["dataset"]["processed_dir"]
    train_path = f"{processed_dir}/train.csv"
    val_path = f"{processed_dir}/val.csv"
    test_path = f"{processed_dir}/test.csv"

    print("\n" + "=" * 60)
    print("STEP 2: Loading processed splits")
    print("=" * 60)
    X_train, y_train = _load_processed_split(train_path)
    X_val, y_val = _load_processed_split(val_path)
    X_test, y_test = _load_processed_split(test_path)
    print(f"  Train shape: {X_train.shape}")
    print(f"  Val shape:   {X_val.shape}")
    print(f"  Test shape:  {X_test.shape}")

    print("\n" + "=" * 60)
    print("STEP 3: Training model")
    print("=" * 60)
    model = build_model(config)
    model = train(model, X_train, y_train)

    print("\n" + "=" * 60)
    print("STEP 4: Evaluating model")
    print("=" * 60)
    train_metrics = evaluate(model, X_train, y_train, "Train")
    val_metrics = evaluate(model, X_val, y_val, "Validation")
    test_metrics = evaluate(model, X_test, y_test, "Test")

    all_metrics = {
        "train": train_metrics,
        "validation": val_metrics,
        "test": test_metrics,
    }

    print("\n" + "=" * 60)
    print("STEP 5: Saving artifacts")
    print("=" * 60)
    save_model(model, config)
    save_metrics(all_metrics, config)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"✅ Training complete in {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"\nSummary:")
    print(f"  Train Accuracy : {train_metrics['accuracy']:.4f}")
    print(f"  Val   Accuracy : {val_metrics['accuracy']:.4f}")
    print(f"  Test  Accuracy : {test_metrics['accuracy']:.4f}")
    print(f"  Test  F1 Score : {test_metrics['f1_score']:.4f}")
    print(f"  Test  ROC-AUC  : {test_metrics['roc_auc']:.4f}")
    print(f"\nArtifacts saved in: {config['output']['model_dir']}/")


def run_pipeline(config_path: str = "config/config.yaml"):
    """Run preprocessing followed by model training."""
    preprocess_data(config_path)
    train_model(config_path)


if __name__ == "__main__":
    run_pipeline()
