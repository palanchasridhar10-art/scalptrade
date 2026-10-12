from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

@dataclass
class MarketAgentSignal:
    regime: str  # "TRENDING_BULLISH", "TRENDING_BEARISH", "RANGING", "HIGH_VOLATILITY"
    trend_probability: float  # 0.0 to 1.0
    volatility_atr: float
    volatility_regime: str  # "LOW", "NORMAL", "HIGH", "EXTREME"
    direction_bias: str  # "LONG", "SHORT", "NEUTRAL"
    score: float  # 0.0 to 100.0
    reasons: List[str] = field(default_factory=list)

class MarketAnalysisAgent:
    """
    Agent 1 — AI Market Analysis.
    Analyzes market conditions and estimates whether the market is trending, ranging, or highly volatile.
    Calculates multi-timeframe trend probability, volatility regimes, and macro directional alignment.
    """
    def __init__(self, atr_period: int = 14, rsi_period: int = 14):
        self.atr_period = atr_period
        self.rsi_period = rsi_period

    def calculate_atr(self, df: pd.DataFrame) -> float:
        if len(df) < self.atr_period + 1:
            return 10.0
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1])
            )
        )
        return float(np.mean(tr[-self.atr_period:]))

    def calculate_ema(self, series: pd.Series, period: int) -> float:
        if len(series) < period:
            return float(series.iloc[-1])
        return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

    def calculate_rsi(self, series: pd.Series) -> float:
        if len(series) < self.rsi_period + 1:
            return 50.0
        delta = series.diff().dropna()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0

    def evaluate(self, df: pd.DataFrame) -> MarketAgentSignal:
        if df.empty or len(df) < 20:
            return MarketAgentSignal(
                regime="RANGING",
                trend_probability=0.5,
                volatility_atr=10.0,
                volatility_regime="NORMAL",
                direction_bias="NEUTRAL",
                score=50.0,
                reasons=["Insufficient historical bars for evaluation."]
            )

        close = df["close"]
        cur_price = float(close.iloc[-1])
        atr = self.calculate_atr(df)
        rsi = self.calculate_rsi(close)

        ema9 = self.calculate_ema(close, 9)
        ema21 = self.calculate_ema(close, 21)
        ema50 = self.calculate_ema(close, 50)

        # 1. Volatility Regime Classification
        atr_pct = (atr / cur_price) * 100.0 if cur_price > 0 else 0.0
        if atr_pct >= 0.65:
            vol_regime = "EXTREME"
        elif atr_pct >= 0.35:
            vol_regime = "HIGH"
        elif atr_pct <= 0.12:
            vol_regime = "LOW"
        else:
            vol_regime = "NORMAL"

        reasons = []

        # 2. Trend & Regime Analysis
        ema_bullish = cur_price > ema9 > ema21 > ema50
        ema_bearish = cur_price < ema9 < ema21 < ema50

        # Bollinger Band width for expansion / contraction
        std20 = float(close.rolling(20).std().iloc[-1]) if len(close) >= 20 else 1.0
        bb_width_pct = (std20 * 4.0 / cur_price) * 100.0 if cur_price > 0 else 1.0

        if vol_regime in ["HIGH", "EXTREME"] and bb_width_pct >= 1.2:
            regime = "HIGH_VOLATILITY"
            reasons.append(f"High volatility expansion: ATR {atr_pct:.2f}% | BB Width {bb_width_pct:.2f}%")
        elif ema_bullish:
            regime = "TRENDING_BULLISH"
            reasons.append("Bullish trend alignment: Price > EMA9 > EMA21 > EMA50")
        elif ema_bearish:
            regime = "TRENDING_BEARISH"
            reasons.append("Bearish trend alignment: Price < EMA9 < EMA21 < EMA50")
        else:
            regime = "RANGING"
            reasons.append("Consolidation: EMAs interleaved without distinct trend slope")

        # 3. Trend Probability & Scoring
        trend_prob = 0.5
        score = 50.0
        direction = "NEUTRAL"

        if regime == "TRENDING_BULLISH":
            trend_prob = 0.78
            direction = "LONG"
            score = 85.0
            if rsi > 55 and rsi < 72:
                score += 7.0
                trend_prob = 0.85
                reasons.append(f"RSI {rsi:.1f} confirms healthy bullish momentum without overbought exhaustion")
        elif regime == "TRENDING_BEARISH":
            trend_prob = 0.78
            direction = "SHORT"
            score = 85.0
            if rsi < 45 and rsi > 28:
                score += 7.0
                trend_prob = 0.85
                reasons.append(f"RSI {rsi:.1f} confirms healthy bearish momentum without oversold exhaustion")
        elif regime == "HIGH_VOLATILITY":
            trend_prob = 0.60
            direction = "LONG" if cur_price > ema21 else "SHORT"
            score = 72.0
            reasons.append(f"High volatility bias towards {direction}")
        else:
            direction = "NEUTRAL"
            score = 45.0
            trend_prob = 0.40

        score = min(98.0, max(20.0, score))

        return MarketAgentSignal(
            regime=regime,
            trend_probability=round(trend_prob, 2),
            volatility_atr=round(atr, 2),
            volatility_regime=vol_regime,
            direction_bias=direction,
            score=round(score, 1),
            reasons=reasons
        )
