from typing import Dict, Any, List
import pandas as pd
import numpy as np

class MarketProfileEngine:
    def analyze(self, df_5m: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        if df_5m.empty or len(df_5m) < 12:
            return {
                "initial_balance_high": current_price,
                "initial_balance_low": current_price,
                "ib_extension": "NONE",
                "single_prints_detected": False,
                "profile_balance": "BALANCED"
            }

        # First 1 hour of trading session (12 x 5m candles) = Initial Balance (IB)
        ib_candles = df_5m.iloc[:12]
        ib_high = float(ib_candles["high"].max())
        ib_low = float(ib_candles["low"].min())
        ib_range = ib_high - ib_low

        # Check IB Extension
        if current_price > ib_high + (ib_range * 0.5):
            ib_extension = "BULLISH_EXTENSION"
        elif current_price < ib_low - (ib_range * 0.5):
            ib_extension = "BEARISH_EXTENSION"
        else:
            ib_extension = "WITHIN_IB"

        # Check Single Prints (rapid displacement creating price vacuums with only 1 TPO)
        single_prints = ib_range > (current_price * 0.015)

        return {
            "initial_balance_high": round(ib_high, 2),
            "initial_balance_low": round(ib_low, 2),
            "ib_range": round(ib_range, 2),
            "ib_extension": ib_extension,
            "single_prints_detected": single_prints,
            "profile_balance": "IMBALANCED" if ib_extension != "WITHIN_IB" else "BALANCED"
        }
