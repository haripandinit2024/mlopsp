"""
Run only the model training stage.

Usage:
  python run_training.py
"""
import os
import sys


os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from src.pipeline import train_model


if __name__ == "__main__":
    train_model()