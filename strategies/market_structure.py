from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np

@dataclass
class MarketStructureResult:
    structure: str  # "BULLISH_BOS", "BEARISH_BOS", "BULLISH_CHOCH", "BEARISH_CHOCH", "RANGING"
    trend: str  # "BULLISH", "BEARISH", "NEUTRAL"
    swing_high: float
    swing_low: float
    equilibrium_price: float
    valuation_zone: str  # "PREMIUM", "DISCOUNT", "EQUILIBRIUM"
    order_block: Optional[Dict[str, Any]]
    confidence: float

class MarketStructureAnalyzer:
    """
    Analyzes Smart Money Concepts (SMC) market structure:
    Break of Structure (BOS), Change of Character (CHoCH), Order Blocks, and Premium/Discount zones.
    """
    def __init__(self, pivot_lookback: int = 5):
        self.pivot_lookback = pivot_lookback

    def find_pivots(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        if len(df) < (self.pivot_lookback * 2 + 1):
            return [], []

        highs = df["high"].values
        lows = df["low"].values
        swing_highs = []
        swing_lows = []

        k = self.pivot_lookback
        for i in range(k, len(df) - k):
            if all(highs[i] > highs[i - j] for j in range(1, k + 1)) and all(highs[i] >= highs[i + j] for j in range(1, k + 1)):
                swing_highs.append(float(highs[i]))
            if all(lows[i] < lows[i - j] for j in range(1, k + 1)) and all(lows[i] <= lows[i + j] for j in range(1, k + 1)):
                swing_lows.append(float(lows[i]))

        return swing_highs, swing_lows

    def analyze(self, df: pd.DataFrame) -> MarketStructureResult:
        if df.empty or len(df) < 15:
            return MarketStructureResult("RANGING", "NEUTRAL", 0.0, 0.0, 0.0, "EQUILIBRIUM", None, 50.0)

        swing_highs, swing_lows = self.find_pivots(df)
        
        last_close = float(df["close"].iloc[-1])
        last_high = float(df["high"].iloc[-1])
        last_low = float(df["low"].iloc[-1])

        sh = swing_highs[-1] if swing_highs else float(df["high"].iloc[-10:-1].max())
        sl = swing_lows[-1] if swing_lows else float(df["low"].iloc[-10:-1].min())

        eq = (sh + sl) / 2.0 if (sh > sl) else last_close

        # Valuation Zone
        if last_close > eq * 1.002:
            valuation = "PREMIUM"
        elif last_close < eq * 0.998:
            valuation = "DISCOUNT"
        else:
            valuation = "EQUILIBRIUM"

        structure = "RANGING"
        trend = "NEUTRAL"
        confidence = 60.0

        # Break of Structure / Change of Character detection
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            prev_sh = swing_highs[-2]
            prev_sl = swing_lows[-2]

            # Bullish BOS: price breaks above swing high in an established uptrend
            if last_close > sh and sh >= prev_sh:
                structure = "BULLISH_BOS"
                trend = "BULLISH"
                confidence = 88.0
            # Bearish BOS: price breaks below swing low in an established downtrend
            elif last_close < sl and sl <= prev_sl:
                structure = "BEARISH_BOS"
                trend = "BEARISH"
                confidence = 88.0
            # Bullish CHoCH: price breaks above swing high after a downtrend (reversal)
            elif last_close > sh and sl <= prev_sl:
                structure = "BULLISH_CHOCH"
                trend = "BULLISH"
                confidence = 85.0
            # Bearish CHoCH: price breaks below swing low after an uptrend (reversal)
            elif last_close < sl and sh >= prev_sh:
                structure = "BEARISH_CHOCH"
                trend = "BEARISH"
                confidence = 85.0

        elif last_close > sh:
            structure = "BULLISH_BOS"
            trend = "BULLISH"
            confidence = 80.0
        elif last_close < sl:
            structure = "BEARISH_BOS"
            trend = "BEARISH"
            confidence = 80.0

        # Order Block detection: last opposite-colored candle before impulse
        order_block = None
        if trend == "BULLISH":
            # Search last bearish candle
            for idx in range(len(df) - 2, max(0, len(df) - 8), -1):
                row = df.iloc[idx]
                if float(row["close"]) < float(row["open"]):
                    order_block = {
                        "type": "BULLISH_ORDER_BLOCK",
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "open": float(row["open"]),
                        "close": float(row["close"])
                    }
                    break
        elif trend == "BEARISH":
            # Search last bullish candle
            for idx in range(len(df) - 2, max(0, len(df) - 8), -1):
                row = df.iloc[idx]
                if float(row["close"]) > float(row["open"]):
                    order_block = {
                        "type": "BEARISH_ORDER_BLOCK",
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "open": float(row["open"]),
                        "close": float(row["close"])
                    }
                    break

        return MarketStructureResult(
            structure=structure,
            trend=trend,
            swing_high=round(sh, 2),
            swing_low=round(sl, 2),
            equilibrium_price=round(eq, 2),
            valuation_zone=valuation,
            order_block=order_block,
            confidence=confidence
        )
