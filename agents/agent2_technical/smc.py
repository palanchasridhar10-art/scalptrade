from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

class SMCEngine:
    def __init__(self, swing_lookback: int = 5, fvg_min_pct: float = 0.001):
        self.swing_lookback = swing_lookback
        self.fvg_min_pct = fvg_min_pct

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 15:
            return {
                "structure": "CONSOLIDATION",
                "bos": False,
                "choch": False,
                "liquidity_sweep": False,
                "fvg": False,
                "order_block": False,
                "fvg_zone": None,
                "order_block_zone": None,
                "premium_discount": "EQUILIBRIUM",
                "nearest_swing_high": 0.0,
                "nearest_swing_low": 0.0
            }

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        opens = df["open"].values
        n = len(df)

        # 1. Identify Swing Highs and Swing Lows
        swing_highs = []
        swing_lows = []

        k = self.swing_lookback
        for i in range(k, n - k):
            if all(highs[i] > highs[i - j] for j in range(1, k + 1)) and all(highs[i] > highs[i + j] for j in range(1, k + 1)):
                swing_highs.append((i, highs[i]))
            if all(lows[i] < lows[i - j] for j in range(1, k + 1)) and all(lows[i] < lows[i + j] for j in range(1, k + 1)):
                swing_lows.append((i, lows[i]))

        latest_swing_high = swing_highs[-1][1] if swing_highs else max(highs[-15:])
        latest_swing_low = swing_lows[-1][1] if swing_lows else min(lows[-15:])
        
        current_close = closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]

        # 2. Break of Structure (BOS) & Change of Character (CHoCH)
        bos = False
        choch = False
        structure = "CONSOLIDATION"

        if current_close > latest_swing_high:
            bos = True
            structure = "BOS"
        elif current_close < latest_swing_low:
            bos = True
            structure = "BOS"

        # CHoCH detection: reversal break of second-latest swing in opposing direction
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            prev_swing_high = swing_highs[-2][1]
            prev_swing_low = swing_lows[-2][1]
            if current_close > prev_swing_high and closes[-3] < prev_swing_low:
                choch = True
                structure = "CHoCH"
            elif current_close < prev_swing_low and closes[-3] > prev_swing_high:
                choch = True
                structure = "CHoCH"

        # 3. Liquidity Sweeps (Wick breaks swing high/low but candle closes back inside)
        liquidity_sweep = False
        sweep_direction = "NONE"
        if current_high > latest_swing_high and current_close < latest_swing_high:
            liquidity_sweep = True
            sweep_direction = "SELL_SIDE_SWEEP"  # Swept buy stops (bearish reversal opportunity)
        elif current_low < latest_swing_low and current_close > latest_swing_low:
            liquidity_sweep = True
            sweep_direction = "BUY_SIDE_SWEEP"   # Swept sell stops (bullish reversal opportunity)

        # 4. Fair Value Gaps (FVG)
        # Bullish FVG: Low(i) > High(i-2) with displacement
        # Bearish FVG: High(i) < Low(i-2) with displacement
        fvg = False
        fvg_zone = None
        fvg_direction = "NONE"

        if n >= 3:
            # Check last 3 completed candles
            for idx in range(n - 1, max(n - 5, 2), -1):
                if lows[idx] > highs[idx - 2]:
                    gap_pct = (lows[idx] - highs[idx - 2]) / highs[idx - 2]
                    if gap_pct >= self.fvg_min_pct:
                        fvg = True
                        fvg_zone = {"low": highs[idx - 2], "high": lows[idx]}
                        fvg_direction = "BULLISH_FVG"
                        break
                elif highs[idx] < lows[idx - 2]:
                    gap_pct = (lows[idx - 2] - highs[idx]) / highs[idx]
                    if gap_pct >= self.fvg_min_pct:
                        fvg = True
                        fvg_zone = {"low": highs[idx], "high": lows[idx - 2]}
                        fvg_direction = "BEARISH_FVG"
                        break

        # 5. Order Blocks (Last opposing candle before displacement)
        order_block = False
        order_block_zone = None
        if bos or choch:
            # Locate last opposite body candle
            for idx in range(n - 2, max(n - 8, 0), -1):
                if current_close > latest_swing_high and closes[idx] < opens[idx]: # Bearish candle before bullish move
                    order_block = True
                    order_block_zone = {"low": lows[idx], "high": highs[idx], "type": "BULLISH_OB"}
                    break
                elif current_close < latest_swing_low and closes[idx] > opens[idx]: # Bullish candle before bearish move
                    order_block = True
                    order_block_zone = {"low": lows[idx], "high": highs[idx], "type": "BEARISH_OB"}
                    break

        # 6. Premium vs Discount Zone (Fibonacci 50% Equilibrium)
        range_span = latest_swing_high - latest_swing_low
        equilibrium = latest_swing_low + (range_span * 0.5) if range_span > 0 else current_close
        if current_close > equilibrium + (range_span * 0.05):
            prem_disc = "PREMIUM"
        elif current_close < equilibrium - (range_span * 0.05):
            prem_disc = "DISCOUNT"
        else:
            prem_disc = "EQUILIBRIUM"

        return {
            "structure": structure,
            "bos": bos,
            "choch": choch,
            "liquidity_sweep": liquidity_sweep,
            "sweep_direction": sweep_direction,
            "fvg": fvg,
            "fvg_direction": fvg_direction,
            "fvg_zone": fvg_zone,
            "order_block": order_block,
            "order_block_zone": order_block_zone,
            "premium_discount": prem_disc,
            "equilibrium_price": round(equilibrium, 2),
            "nearest_swing_high": round(latest_swing_high, 2),
            "nearest_swing_low": round(latest_swing_low, 2)
        }
