"""
Preprocessor - Handles missing values, encoding, scaling, and train/val/test splits.
Fits ONLY on train data to prevent leakage.
"""
import pandas as pd
import numpy as np
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder
from sklearn.impute import SimpleImputer


class DropoutPreprocessor:
    def __init__(self, config: dict):
        self.config = config
        self.num_features = config["numerical_features"]
        self.cat_features = config["categorical_features"]
        self.target = config["target_column"]
        self.drop_cols = config.get("drop_columns", [])
        self.scaler_type = config["preprocessing"]["scaler"]
        self.num_imputer = None
        self.cat_imputer = None
        self.scaler = None
        self.encoded_columns = None   # list of all columns after OHE
        self.label_encoders = {}      # for binary cat columns

    def _drop_and_select(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop irrelevant columns and keep only configured features + target."""
        cols_to_keep = self.num_features + self.cat_features + [self.target]
        cols_available = [c for c in cols_to_keep if c in df.columns]
        df = df[cols_available]
        return df

    def _impute_numerical(self, df: pd.DataFrame, fit: bool = False):
        strategy = self.config["preprocessing"]["impute_numerical_strategy"]
        existing_num = [c for c in self.num_features if c in df.columns]
        if fit:
            self.num_imputer = SimpleImputer(strategy=strategy)
            df[existing_num] = self.num_imputer.fit_transform(df[existing_num])
        else:
            df[existing_num] = self.num_imputer.transform(df[existing_num])
        return df

    def _impute_categorical(self, df: pd.DataFrame, fit: bool = False):
        strategy = self.config["preprocessing"]["impute_categorical_strategy"]
        existing_cat = [c for c in self.cat_features if c in df.columns]
        if fit:
            self.cat_imputer = SimpleImputer(strategy=strategy)
            df[existing_cat] = self.cat_imputer.fit_transform(df[existing_cat])
        else:
            df[existing_cat] = self.cat_imputer.transform(df[existing_cat])
        return df

    def _encode_categorical(self, df: pd.DataFrame, fit: bool = False):
        existing_cat = [c for c in self.cat_features if c in df.columns]
        # Use one-hot encoding for all categorical columns
        df = pd.get_dummies(df, columns=existing_cat, drop_first=False, dtype=float)
        if fit:
            self.encoded_columns = df.columns.tolist()
        else:
            # Align columns to training set schema
            for c in self.encoded_columns:
                if c not in df.columns:
                    df[c] = 0.0
            df = df[self.encoded_columns]
        return df

    def _scale_numerical(self, df: pd.DataFrame, fit: bool = False):
        existing_num = [c for c in self.num_features if c in df.columns]
        if fit:
            if self.scaler_type == "minmax":
                self.scaler = MinMaxScaler()
            else:
                self.scaler = StandardScaler()
            df[existing_num] = self.scaler.fit_transform(df[existing_num].astype(float))
        else:
            df[existing_num] = self.scaler.transform(df[existing_num].astype(float))
        return df

    def split(self, df: pd.DataFrame):
        """Stratified train / val / test split."""
        split_cfg = self.config["split"]
        val_ratio = split_cfg["val_ratio"]
        test_ratio = split_cfg["test_ratio"]
        seed = split_cfg["random_state"]

        X = df.drop(columns=[self.target])
        y = df[self.target]

        test_size = test_ratio
        val_size = val_ratio / (1 - test_size)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=seed
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=val_size, stratify=y_train, random_state=seed
        )

        print(f"\n[Preprocessor] Split sizes:")
        print(f"  Train: {len(X_train)} ({len(X_train)/len(df)*100:.1f}%)")
        print(f"  Val:   {len(X_val)}   ({len(X_val)/len(df)*100:.1f}%)")
        print(f"  Test:  {len(X_test)}  ({len(X_test)/len(df)*100:.1f}%)")

        return (X_train, y_train), (X_val, y_val), (X_test, y_test)

    def fit_transform(self, df: pd.DataFrame):
        """Process and split the full dataset. Returns processed splits.

        Every fitted transformer (imputers, encoder column set, scaler) is fit
        on the training split ONLY. Imputation used to run before split(),
        which leaked the test set's median/mode into training.
        """
        df = self._drop_and_select(df)

        # Split first, so nothing is fitted on data the model will be tested on.
        train_split, val_split, test_split = self.split(df)

        X_train, y_train = train_split
        X_val, y_val = val_split
        X_test, y_test = test_split

        X_train = pd.DataFrame(X_train)
        X_val = pd.DataFrame(X_val)
        X_test = pd.DataFrame(X_test)

        # Impute - FIT ON TRAIN ONLY, then apply to val/test
        X_train = self._impute_numerical(X_train, fit=True)
        X_val = self._impute_numerical(X_val, fit=False)
        X_test = self._impute_numerical(X_test, fit=False)

        X_train = self._impute_categorical(X_train, fit=True)
        X_val = self._impute_categorical(X_val, fit=False)
        X_test = self._impute_categorical(X_test, fit=False)

        # Encode + scale - FIT ON TRAIN ONLY
        X_train = self._encode_categorical(X_train, fit=True)
        X_train = self._scale_numerical(X_train, fit=True)

        X_val = self._encode_categorical(X_val, fit=False)
        X_val = self._scale_numerical(X_val, fit=False)

        X_test = self._encode_categorical(X_test, fit=False)
        X_test = self._scale_numerical(X_test, fit=False)

        print(f"\n[Preprocessor] Feature matrix shape after preprocessing: {X_train.shape}")
        print(f"[Preprocessor] Columns: {list(X_train.columns)}")

        return (X_train, y_train), (X_val, y_val), (X_test, y_test)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply trained transformers to new data (inference)."""
        df = self._drop_and_select(df)
        # Drop target if present
        if self.target in df.columns:
            df = df.drop(columns=[self.target])
        df = self._impute_numerical(df, fit=False)
        df = self._impute_categorical(df, fit=False)
        df = self._encode_categorical(df, fit=False)
        df = self._scale_numerical(df, fit=False)
        return df

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        print(f"[Preprocessor] Saved preprocessor to: {path}")

    @staticmethod
    def load(path: str):
        with open(path, "rb") as f:
            return pickle.load(f)
