from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

class MarketRegimeDetector:
    def classify(
        self,
        candles_df: pd.DataFrame,
        imbalance: float = 0.0,
        buy_pressure: float = 0.5,
        cvd_direction: str = "FLAT"
    ) -> Dict[str, Any]:
        if candles_df.empty or len(candles_df) < 15:
            return {
                "regime": "UNCERTAIN",
                "volatility_state": "NORMAL",
                "trend_strength": 0.0,
                "atr": 0.0,
                "adx": 0.0
            }

        closes = candles_df["close"].values
        highs = candles_df["high"].values
        lows = candles_df["low"].values

        # Simple ATR calculation
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
            
        atr = float(np.mean(tr_list[-14:])) if len(tr_list) >= 14 else float(np.mean(tr_list))
        mean_price = float(np.mean(closes[-14:]))
        atr_pct = (atr / mean_price * 100.0) if mean_price > 0 else 0.0

        # Moving averages for slope
        ema_fast = float(pd.Series(closes).ewm(span=9).mean().iloc[-1])
        ema_slow = float(pd.Series(closes).ewm(span=21).mean().iloc[-1])
        ma_diff_pct = (ema_fast - ema_slow) / ema_slow if ema_slow > 0 else 0.0

        # Realized volatility (std of log returns)
        log_returns = np.diff(np.log(closes))
        realized_vol = float(np.std(log_returns[-14:]) * np.sqrt(1440)) if len(log_returns) >= 14 else 0.0

        # Volatility Classification
        if atr_pct > 0.40 or realized_vol > 0.035:
            vol_state = "HIGH_VOLATILITY"
        elif atr_pct < 0.10:
            vol_state = "LOW_VOLATILITY"
        else:
            vol_state = "NORMAL"

        # Regime determination
        if ma_diff_pct > 0.0015 and (imbalance > 0.15 or buy_pressure > 0.55 or cvd_direction == "UP"):
            if abs(closes[-1] - highs[-5:].max()) < atr * 0.2:
                regime = "BREAKOUT"
            else:
                regime = "TREND_UP"
        elif ma_diff_pct < -0.0015 and (imbalance < -0.15 or buy_pressure < 0.45 or cvd_direction == "DOWN"):
            if abs(closes[-1] - lows[-5:].min()) < atr * 0.2:
                regime = "BREAKDOWN"
            else:
                regime = "TREND_DOWN"
        elif vol_state == "HIGH_VOLATILITY":
            regime = "HIGH_VOLATILITY"
        elif vol_state == "LOW_VOLATILITY":
            regime = "LOW_VOLATILITY"
        else:
            regime = "RANGE"

        return {
            "regime": regime,
            "volatility_state": vol_state,
            "trend_strength": round(abs(ma_diff_pct) * 1000, 2),
            "atr": round(atr, 2),
            "atr_pct": round(atr_pct, 3),
            "realized_vol": round(realized_vol, 4)
        }
