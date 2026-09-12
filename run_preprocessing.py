"""
Run only the preprocessing stage.

Usage:
  python run_preprocessing.py
"""
import os
import sys


os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from src.pipeline import preprocess_data


if __name__ == "__main__":
    preprocess_data()