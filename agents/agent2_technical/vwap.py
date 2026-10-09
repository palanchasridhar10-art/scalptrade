from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

class VWAPEngine:
    def calculate_vwap(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or "volume" not in df.columns or len(df) < 5:
            return {
                "vwap": 0.0,
                "upper_band_1": 0.0,
                "lower_band_1": 0.0,
                "upper_band_2": 0.0,
                "lower_band_2": 0.0,
                "position": "AT_VWAP",
                "distance_pct": 0.0
            }

        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        volume = df["volume"]

        cum_tp_vol = (typical_price * volume).cumsum()
        cum_vol = volume.cumsum()
        
        vwap_series = cum_tp_vol / (cum_vol + 1e-9)
        current_vwap = float(vwap_series.iloc[-1])

        # Standard deviation bands
        squared_diff = ((typical_price - vwap_series) ** 2) * volume
        variance = squared_diff.cumsum() / (cum_vol + 1e-9)
        std_dev = np.sqrt(np.maximum(0.0, variance)).iloc[-1]

        cur_price = float(df["close"].iloc[-1])
        up_1 = current_vwap + float(std_dev)
        low_1 = current_vwap - float(std_dev)
        up_2 = current_vwap + (2.0 * float(std_dev))
        low_2 = current_vwap - (2.0 * float(std_dev))

        dist_pct = (cur_price - current_vwap) / current_vwap if current_vwap > 0 else 0.0

        if dist_pct > 0.001:
            position = "ABOVE"
        elif dist_pct < -0.001:
            position = "BELOW"
        else:
            position = "AT_VWAP"

        return {
            "vwap": round(current_vwap, 2),
            "upper_band_1": round(up_1, 2),
            "lower_band_1": round(low_1, 2),
            "upper_band_2": round(up_2, 2),
            "lower_band_2": round(low_2, 2),
            "position": position,
            "distance_pct": round(dist_pct * 100.0, 3)
        }
