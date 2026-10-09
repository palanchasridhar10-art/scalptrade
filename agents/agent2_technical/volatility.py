from typing import Dict, Any
import pandas as pd
import numpy as np

class VolatilityEngine:
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 15:
            return {
                "realized_vol": 0.0,
                "parkinson_vol": 0.0,
                "volatility_regime": "NORMAL",
                "volatility_score": 5.0
            }

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values

        # 1. Realized Volatility (Annualized standard deviation of log returns)
        log_ret = np.diff(np.log(closes))
        realized_vol = float(np.std(log_ret) * np.sqrt(365 * 1440))

        # 2. Parkinson Volatility (Uses High-Low range)
        hl_ratio = np.log(highs / (lows + 1e-9))
        parkinson_vol = float(np.sqrt((1.0 / (4.0 * len(df) * np.log(2.0))) * np.sum(hl_ratio ** 2)) * np.sqrt(365 * 1440))

        if realized_vol > 0.85:
            regime = "EXTREME_VOLATILITY"
            score = 2.0  # Hazardous for tight scalping
        elif realized_vol > 0.45:
            regime = "EXPANDING_VOLATILITY"
            score = 8.0  # Great for breakout scalping
        elif realized_vol < 0.15:
            regime = "COMPRESSED_VOLATILITY"
            score = 6.0  # Range / pre-breakout
        else:
            regime = "NORMAL"
            score = 7.0

        return {
            "realized_vol": round(realized_vol, 4),
            "parkinson_vol": round(parkinson_vol, 4),
            "volatility_regime": regime,
            "volatility_score": score
        }
