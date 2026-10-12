from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np

@dataclass
class LiquiditySweepResult:
    has_sweep: bool
    direction: str  # "BULLISH_SWEEP" (SSL swept) or "BEARISH_SWEEP" (BSL swept) or "NONE"
    swept_level: float
    sweep_depth_pct: float
    rejection_wick_ratio: float
    invalidation_level: float  # Absolute extreme of the wick (Stop Loss)
    confidence: float

class LiquiditySweepDetector:
    """
    Detects institutional liquidity sweeps across key high/low reference points.
    Identifies false breakouts that take resting stops and immediately reject.
    """
    def __init__(self, min_wick_ratio: float = 1.2):
        self.min_wick_ratio = min_wick_ratio

    def analyze(self, df: pd.DataFrame, pdh: Optional[float] = None, pdl: Optional[float] = None) -> LiquiditySweepResult:
        if df.empty or len(df) < 5:
            return LiquiditySweepResult(False, "NONE", 0.0, 0.0, 0.0, 0.0, 0.0)

        latest = df.iloc[-1]
        prior_bars = df.iloc[-15:-1]

        swing_high = float(prior_bars["high"].max())
        swing_low = float(prior_bars["low"].min())

        c_open = float(latest["open"])
        c_high = float(latest["high"])
        c_low = float(latest["low"])
        c_close = float(latest["close"])

        body = abs(c_close - c_open)
        upper_wick = c_high - max(c_open, c_close)
        lower_wick = min(c_open, c_close) - c_low

        # 1. Bearish Buy-Side Liquidity (BSL) Sweep:
        # High pierced swing high (or PDH), but candle closed back inside the range with upper wick
        ref_high = pdh if pdh and abs(c_high - pdh) / pdh < 0.01 else swing_high
        if c_high > ref_high and c_close < ref_high:
            wick_ratio = upper_wick / (body + 1e-6)
            if wick_ratio >= self.min_wick_ratio:
                depth_pct = (c_high - ref_high) / ref_high * 100.0
                confidence = min(95.0, 70.0 + (wick_ratio * 5.0) + (depth_pct * 10.0))
                return LiquiditySweepResult(
                    has_sweep=True,
                    direction="BEARISH_SWEEP",
                    swept_level=round(ref_high, 2),
                    sweep_depth_pct=round(depth_pct, 3),
                    rejection_wick_ratio=round(wick_ratio, 2),
                    invalidation_level=round(c_high, 2),
                    confidence=round(confidence, 1)
                )

        # 2. Bullish Sell-Side Liquidity (SSL) Sweep:
        # Low pierced swing low (or PDL), but candle closed back inside the range with lower wick
        ref_low = pdl if pdl and abs(c_low - pdl) / pdl < 0.01 else swing_low
        if c_low < ref_low and c_close > ref_low:
            wick_ratio = lower_wick / (body + 1e-6)
            if wick_ratio >= self.min_wick_ratio:
                depth_pct = (ref_low - c_low) / ref_low * 100.0
                confidence = min(95.0, 70.0 + (wick_ratio * 5.0) + (depth_pct * 10.0))
                return LiquiditySweepResult(
                    has_sweep=True,
                    direction="BULLISH_SWEEP",
                    swept_level=round(ref_low, 2),
                    sweep_depth_pct=round(depth_pct, 3),
                    rejection_wick_ratio=round(wick_ratio, 2),
                    invalidation_level=round(c_low, 2),
                    confidence=round(confidence, 1)
                )

        return LiquiditySweepResult(False, "NONE", 0.0, 0.0, 0.0, 0.0, 0.0)
