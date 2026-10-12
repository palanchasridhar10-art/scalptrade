from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import pandas as pd

from strategies.liquidity_sweep import LiquiditySweepDetector, LiquiditySweepResult
from strategies.fair_value_gap import FairValueGapDetector, FVGResult
from strategies.market_structure import MarketStructureAnalyzer, MarketStructureResult

@dataclass
class SMCAgentSignal:
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    score: float  # 0.0 to 100.0
    entry_price: float
    invalidation_level: float  # Stop-Loss
    take_profit_level: float  # Take-Profit Target
    risk_reward_ratio: float
    structure: str  # BOS, CHoCH, RANGING
    has_liquidity_sweep: bool
    has_fvg: bool
    has_order_block: bool
    valuation_zone: str  # PREMIUM, DISCOUNT, EQUILIBRIUM
    reasons: List[str] = field(default_factory=list)

class SMCLiquidityAgent:
    """
    Agent 2 — SMC and Liquidity Analysis.
    Identifies institutional liquidity sweeps, BOS, CHoCH, Fair Value Gaps, and Order Blocks.
    Computes precise entry, invalidation (SL), and take-profit levels with R:R >= 2.0.
    """
    def __init__(self, min_rr: float = 2.0):
        self.min_rr = min_rr
        self.sweep_detector = LiquiditySweepDetector()
        self.fvg_detector = FairValueGapDetector()
        self.structure_analyzer = MarketStructureAnalyzer()

    def evaluate(self, df: pd.DataFrame, pdh: Optional[float] = None, pdl: Optional[float] = None) -> SMCAgentSignal:
        if df.empty or len(df) < 20:
            return SMCAgentSignal(
                direction="NEUTRAL",
                score=40.0,
                entry_price=0.0,
                invalidation_level=0.0,
                take_profit_level=0.0,
                risk_reward_ratio=0.0,
                structure="RANGING",
                has_liquidity_sweep=False,
                has_fvg=False,
                has_order_block=False,
                valuation_zone="EQUILIBRIUM",
                reasons=["Insufficient historical data for SMC evaluation."]
            )

        cur_price = float(df["close"].iloc[-1])

        # 1. Run Structural & Liquidity Sub-Engines
        sweep_res = self.sweep_detector.analyze(df, pdh=pdh, pdl=pdl)
        fvg_res = self.fvg_detector.analyze(df)
        struct_res = self.structure_analyzer.analyze(df)

        reasons = []
        long_points = 0.0
        short_points = 0.0

        # Liquidity Sweep Confluence (30 pts)
        if sweep_res.has_sweep:
            if sweep_res.direction == "BULLISH_SWEEP":
                long_points += 30.0
                reasons.append(f"SSL Liquidity Sweep below ${sweep_res.swept_level:.2f} with strong wick rejection (Stop Hunt)")
            elif sweep_res.direction == "BEARISH_SWEEP":
                short_points += 30.0
                reasons.append(f"BSL Liquidity Sweep above ${sweep_res.swept_level:.2f} with strong wick rejection (Stop Hunt)")

        # Market Structure (BOS / CHoCH) (25 pts)
        if "BOS" in struct_res.structure:
            if struct_res.trend == "BULLISH":
                long_points += 22.0
                reasons.append(f"Bullish Break of Structure (BOS) confirming trend expansion")
            else:
                short_points += 22.0
                reasons.append(f"Bearish Break of Structure (BOS) confirming trend expansion")
        elif "CHOCH" in struct_res.structure:
            if struct_res.trend == "BULLISH":
                long_points += 25.0
                reasons.append(f"Bullish Change of Character (CHoCH) structural reversal")
            else:
                short_points += 25.0
                reasons.append(f"Bearish Change of Character (CHoCH) structural reversal")

        # Fair Value Gap Confluence (20 pts)
        if fvg_res.has_fvg and not fvg_res.is_mitigated:
            if fvg_res.direction == "BULLISH_FVG":
                long_points += 20.0
                reasons.append(f"Bullish Fair Value Gap (${fvg_res.gap_bottom:.2f} - ${fvg_res.gap_top:.2f}) offering liquidity support")
            elif fvg_res.direction == "BEARISH_FVG":
                short_points += 20.0
                reasons.append(f"Bearish Fair Value Gap (${fvg_res.gap_bottom:.2f} - ${fvg_res.gap_top:.2f}) offering liquidity resistance")

        # Order Block Mitigation (15 pts)
        has_ob = struct_res.order_block is not None
        if has_ob:
            ob_type = struct_res.order_block["type"]
            if ob_type == "BULLISH_ORDER_BLOCK":
                long_points += 15.0
                reasons.append("Bullish Order Block mitigation zone active")
            else:
                short_points += 15.0
                reasons.append("Bearish Order Block mitigation zone active")

        # Premium / Discount Filter (10 pts)
        if struct_res.valuation_zone == "DISCOUNT":
            long_points += 10.0
            short_points -= 10.0
            reasons.append("Price is in institutional DISCOUNT zone (Favorable for Longs)")
        elif struct_res.valuation_zone == "PREMIUM":
            short_points += 10.0
            long_points -= 10.0
            reasons.append("Price is in institutional PREMIUM zone (Favorable for Shorts)")

        # Determine Winner & Build Trade Parameters
        if long_points > short_points and long_points >= 35.0:
            direction = "LONG"
            score = min(98.0, 48.0 + long_points)
            
            # Invalidation level: Sweep wick low or FVG bottom or swing low
            sl = sweep_res.invalidation_level if sweep_res.has_sweep and sweep_res.invalidation_level > 0 else (
                fvg_res.invalidation_level if fvg_res.has_fvg and fvg_res.invalidation_level > 0 else struct_res.swing_low
            )
            # Ensure SL is strictly below entry
            if sl >= cur_price:
                sl = cur_price * 0.995

            risk_dist = cur_price - sl
            tp = cur_price + (risk_dist * 2.3)  # Targeting 2.3 R:R
            rr = (tp - cur_price) / risk_dist if risk_dist > 0 else 0.0

        elif short_points > long_points and short_points >= 35.0:
            direction = "SHORT"
            score = min(98.0, 48.0 + short_points)

            # Invalidation level: Sweep wick high or FVG top or swing high
            sl = sweep_res.invalidation_level if sweep_res.has_sweep and sweep_res.invalidation_level > 0 else (
                fvg_res.invalidation_level if fvg_res.has_fvg and fvg_res.invalidation_level > 0 else struct_res.swing_high
            )
            # Ensure SL is strictly above entry
            if sl <= cur_price:
                sl = cur_price * 1.005

            risk_dist = sl - cur_price
            tp = cur_price - (risk_dist * 2.3)  # Targeting 2.3 R:R
            rr = (cur_price - tp) / risk_dist if risk_dist > 0 else 0.0

        else:
            direction = "NEUTRAL"
            score = max(long_points, short_points)
            sl = 0.0
            tp = 0.0
            rr = 0.0

        return SMCAgentSignal(
            direction=direction,
            score=round(score, 1),
            entry_price=round(cur_price, 2),
            invalidation_level=round(sl, 2),
            take_profit_level=round(tp, 2),
            risk_reward_ratio=round(rr, 2),
            structure=struct_res.structure,
            has_liquidity_sweep=sweep_res.has_sweep,
            has_fvg=fvg_res.has_fvg,
            has_order_block=has_ob,
            valuation_zone=struct_res.valuation_zone,
            reasons=reasons
        )
