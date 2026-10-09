from typing import List, Dict, Any
import numpy as np
import pandas as pd

class WalkForwardValidator:
    """Walk-Forward and Out-of-Sample Validation Engine"""
    def __init__(self, train_ratio: float = 0.70, num_folds: int = 4):
        self.train_ratio = train_ratio
        self.num_folds = num_folds

    def split_data(self, df: pd.DataFrame) -> List[Dict[str, pd.DataFrame]]:
        n = len(df)
        fold_size = n // self.num_folds
        splits = []

        for i in range(self.num_folds):
            start_idx = i * fold_size
            end_idx = min(n, (i + 1) * fold_size)
            fold_df = df.iloc[start_idx:end_idx]
            
            train_len = int(len(fold_df) * self.train_ratio)
            in_sample = fold_df.iloc[:train_len]
            out_of_sample = fold_df.iloc[train_len:]
            
            splits.append({
                "fold": i + 1,
                "in_sample": in_sample,
                "out_of_sample": out_of_sample
            })

        return splits
