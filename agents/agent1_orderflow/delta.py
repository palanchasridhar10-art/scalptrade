from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

class CVDAnalyzer:
    def __init__(self, lookback_bars: int = 20):
        self.lookback_bars = lookback_bars

    def analyze(self, cvd_df: pd.DataFrame, candles_df: pd.DataFrame) -> Dict[str, Any]:
        if cvd_df.empty or len(cvd_df) < 5:
            return {
                "latest_delta": 0.0,
                "current_cvd": 0.0,
                "cvd_direction": "FLAT",
                "divergence": "NONE",
                "score_bias": "NEUTRAL"
            }

        recent_cvd = cvd_df.tail(self.lookback_bars)
        current_cvd = float(recent_cvd["cvd"].iloc[-1])
        first_cvd = float(recent_cvd["cvd"].iloc[0])
        latest_delta = float(recent_cvd["delta"].iloc[-1])

        cvd_change = current_cvd - first_cvd
        if cvd_change > 5.0:
            cvd_direction = "UP"
        elif cvd_change < -5.0:
            cvd_direction = "DOWN"
        else:
            cvd_direction = "FLAT"

        # Check Divergence against price
        divergence = "NONE"
        score_bias = "NEUTRAL"

        if len(candles_df) >= 10:
            recent_candles = candles_df.tail(min(self.lookback_bars, len(candles_df)))
            price_start = recent_candles["close"].iloc[0]
            price_end = recent_candles["close"].iloc[-1]
            price_change_pct = (price_end - price_start) / price_start if price_start > 0 else 0.0

            # Price down but CVD up => Bullish Divergence
            if price_change_pct < -0.0015 and cvd_change > 2.0:
                divergence = "BULLISH_DIV"
                score_bias = "BULLISH"
            # Price up but CVD down => Bearish Divergence
            elif price_change_pct > 0.0015 and cvd_change < -2.0:
                divergence = "BEARISH_DIV"
                score_bias = "BEARISH"
            # Price up + CVD up => Trend confirmation
            elif price_change_pct > 0.001 and cvd_direction == "UP":
                score_bias = "BULLISH"
            # Price down + CVD down => Trend confirmation
            elif price_change_pct < -0.001 and cvd_direction == "DOWN":
                score_bias = "BEARISH"

        return {
            "latest_delta": round(latest_delta, 4),
            "current_cvd": round(current_cvd, 4),
            "cvd_direction": cvd_direction,
            "divergence": divergence,
            "score_bias": score_bias
        }
