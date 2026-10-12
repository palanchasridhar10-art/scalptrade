from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import pandas as pd

@dataclass
class FVGResult:
    has_fvg: bool
    direction: str  # "BULLISH_FVG" or "BEARISH_FVG" or "NONE"
    gap_top: float
    gap_bottom: float
    consequent_encroachment: float  # 50% midpoint of the FVG
    gap_size_pct: float
    is_mitigated: bool
    entry_level: float
    invalidation_level: float

class FairValueGapDetector:
    """
    Detects SMC 3-candle Fair Value Gaps (FVG) and price imbalances.
    """
    def __init__(self, min_gap_pct: float = 0.015):
        self.min_gap_pct = min_gap_pct

    def analyze(self, df: pd.DataFrame) -> FVGResult:
        if df.empty or len(df) < 3:
            return FVGResult(False, "NONE", 0.0, 0.0, 0.0, 0.0, True, 0.0, 0.0)

        # Inspect the most recent 3-candle sequence
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]  # Displacement candle
        c3 = df.iloc[-1]

        # 1. Bullish FVG: Candle 3 Low is strictly greater than Candle 1 High
        if float(c3["low"]) > float(c1["high"]):
            top = float(c3["low"])
            bottom = float(c1["high"])
            gap_size = top - bottom
            gap_pct = (gap_size / bottom) * 100.0

            if gap_pct >= self.min_gap_pct:
                ce = (top + bottom) / 2.0  # 50% Consequent Encroachment
                return FVGResult(
                    has_fvg=True,
                    direction="BULLISH_FVG",
                    gap_top=round(top, 2),
                    gap_bottom=round(bottom, 2),
                    consequent_encroachment=round(ce, 2),
                    gap_size_pct=round(gap_pct, 3),
                    is_mitigated=False,
                    entry_level=round(top, 2),
                    invalidation_level=round(bottom, 2)
                )

        # 2. Bearish FVG: Candle 3 High is strictly less than Candle 1 Low
        elif float(c3["high"]) < float(c1["low"]):
            top = float(c1["low"])
            bottom = float(c3["high"])
            gap_size = top - bottom
            gap_pct = (gap_size / top) * 100.0

            if gap_pct >= self.min_gap_pct:
                ce = (top + bottom) / 2.0
                return FVGResult(
                    has_fvg=True,
                    direction="BEARISH_FVG",
                    gap_top=round(top, 2),
                    gap_bottom=round(bottom, 2),
                    consequent_encroachment=round(ce, 2),
                    gap_size_pct=round(gap_pct, 3),
                    is_mitigated=False,
                    entry_level=round(bottom, 2),
                    invalidation_level=round(top, 2)
                )

        return FVGResult(False, "NONE", 0.0, 0.0, 0.0, 0.0, True, 0.0, 0.0)
