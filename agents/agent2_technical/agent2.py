from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import pandas as pd

from data.schemas.signals import Agent2Signal
from data.live.buffer import SymbolDataBuffer
from config.settings import Agent2Config

from .indicators import TechnicalIndicators
from .smc import SMCEngine
from .liquidity import LiquidityEngine
from .volume_profile import VolumeProfileEngine
from .market_profile import MarketProfileEngine
from .vwap import VWAPEngine
from .volatility import VolatilityEngine
from .kelly import KellyCriterion

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class Agent2TechnicalSMC:
    """Agent 2 — Technical, Smart Money Concepts & Liquidity Agent"""
    def __init__(self, config: Optional[Agent2Config] = None):
        self.config = config or Agent2Config()
        self.indicators = TechnicalIndicators()
        self.smc = SMCEngine()
        self.liquidity = LiquidityEngine()
        self.volume_profile = VolumeProfileEngine(
            num_bins=self.config.indicators.volume_profile_bins,
            value_area_pct=self.config.indicators.value_area_pct
        )
        self.market_profile = MarketProfileEngine()
        self.vwap_engine = VWAPEngine()
        self.volatility_engine = VolatilityEngine()
        self.kelly_calculator = KellyCriterion(fraction_multiplier=0.15)

    def evaluate(self, buffer: SymbolDataBuffer) -> Agent2Signal:
        reasons: List[str] = []

        # Get multi-timeframe candle datasets
        df_1m = buffer.get_candles_df("1M", limit=100)
        df_5m = buffer.get_candles_df("5M", limit=100)
        df_15m = buffer.get_candles_df("15M", limit=100)
        df_1h = buffer.get_candles_df("1H", limit=100)
        df_1d = buffer.get_candles_df("1D", limit=30)

        current_price = buffer.orderbook.best_bid if buffer.orderbook else (
            float(df_1m["close"].iloc[-1]) if not df_1m.empty else 67000.0
        )

        # 1. Indicators (5M primary)
        ind_res = self.indicators.analyze_all(df_5m if len(df_5m) >= 20 else df_1m)
        
        # 2. SMC Structure (5M / 15M)
        smc_res = self.smc.analyze(df_5m if len(df_5m) >= 15 else df_1m)
        
        # 3. Liquidity Engine & Limit Orders Heatmap (1D/1H Key Levels + L2 Limit Depth)
        liq_res = self.liquidity.analyze(df_1d, df_1h, current_price, buffer.orderbook)
        
        # 4. Volume Profile (15M / 1H)
        vp_res = self.volume_profile.analyze(df_15m if len(df_15m) >= 10 else df_1m, current_price)
        
        # 5. Market Profile (5M Initial Balance)
        mp_res = self.market_profile.analyze(df_5m, current_price)
        
        # 6. VWAP (1M / 5M)
        vwap_res = self.vwap_engine.calculate_vwap(df_5m if len(df_5m) >= 10 else df_1m)
        
        # 7. Volatility (5M)
        vol_res = self.volatility_engine.analyze(df_5m if len(df_5m) >= 15 else df_1m)
        
        # 8. Kelly Position Sizing Fraction
        kelly_res = self.kelly_calculator.calculate(win_rate=0.62, payoff_ratio=2.2, sample_size=120)

        # --- SCORING SYSTEM (0-100) ---
        long_points = 0.0
        short_points = 0.0
        weights = self.config.weights

        # A. SMC Structure & Confluence (25 pts)
        struct = smc_res.get("structure", "CONSOLIDATION")
        has_sweep = smc_res.get("liquidity_sweep", False)
        sweep_dir = smc_res.get("sweep_direction", "NONE")
        has_fvg = smc_res.get("fvg", False)
        fvg_dir = smc_res.get("fvg_direction", "NONE")
        has_ob = smc_res.get("order_block", False)
        prem_disc = smc_res.get("premium_discount", "EQUILIBRIUM")

        if smc_res.get("choch"):
            reasons.append("SMC Change of Character (CHoCH) structural transition")
            if ind_res.get("trend_score", 0) >= 0:
                long_points += 15.0
            else:
                short_points += 15.0
        elif smc_res.get("bos"):
            reasons.append("SMC Break of Structure (BOS) trend expansion")
            if current_price > smc_res.get("nearest_swing_high", 0.0):
                long_points += 12.0
            else:
                short_points += 12.0

        # High-Accuracy SMC Confluence: Liquidity Sweep + FVG Displacement / Order Block
        if has_sweep and sweep_dir == "BUY_SIDE_SWEEP":
            long_points += 15.0
            reasons.append("Sell-side liquidity sweep below key swing low (Bullish Reversal)")
            if has_fvg and fvg_dir == "BULLISH_FVG":
                long_points += 8.0
                reasons.append("High-confluence: Liquidity Sweep + Bullish FVG displacement")
            if has_ob:
                long_points += 5.0
                reasons.append("High-confluence: Bullish Order Block mitigation")
        elif has_sweep and sweep_dir == "SELL_SIDE_SWEEP":
            short_points += 15.0
            reasons.append("Buy-side liquidity sweep above key swing high (Bearish Reversal)")
            if has_fvg and fvg_dir == "BEARISH_FVG":
                short_points += 8.0
                reasons.append("High-confluence: Liquidity Sweep + Bearish FVG displacement")
            if has_ob:
                short_points += 5.0
                reasons.append("High-confluence: Bearish Order Block mitigation")

        # Premium / Discount Valuation Filter (Prevents buying the top / shorting the bottom)
        if prem_disc == "DISCOUNT":
            long_points += 8.0
            short_points -= 10.0
            reasons.append("Price in institutional DISCOUNT zone (Favorable for LONG)")
        elif prem_disc == "PREMIUM":
            short_points += 8.0
            long_points -= 10.0
            reasons.append("Price in institutional PREMIUM zone (Favorable for SHORT)")

        # B. Limit Order Heatmap & Resting Wall Defense (15 pts)
        hm_bias = liq_res.get("heatmap_bias", "NEUTRAL")
        bid_wall = liq_res.get("nearest_major_bid_wall")
        ask_wall = liq_res.get("nearest_major_ask_wall")
        
        if hm_bias == "SUPPORT":
            long_points += 8.0
            wall_text = f" @ ${bid_wall:,.2f}" if bid_wall else ""
            reasons.append(f"Agent 2 Heatmap: Heavy resting Limit Bid Wall support{wall_text}")
        elif hm_bias == "RESISTANCE":
            short_points += 8.0
            wall_text = f" @ ${ask_wall:,.2f}" if ask_wall else ""
            reasons.append(f"Agent 2 Heatmap: Heavy resting Limit Ask Wall resistance{wall_text}")

        # C. Multi-Timeframe Trend & EMA Alignment (15 pts)
        trend_score = ind_res.get("trend_score", 0)
        if trend_score > 0:
            long_points += weights.mtf_trend_alignment
            reasons.append("Trend alignment: Price > EMA20 > EMA50 > EMA200")
        elif trend_score < 0:
            short_points += weights.mtf_trend_alignment
            reasons.append("Trend alignment: Price < EMA20 < EMA50 < EMA200")

        # C. Volume Profile POC & Value Area (10 pts)
        va_pos = vp_res.get("position_relative_to_va", "INSIDE")
        poc_price = vp_res.get("poc", current_price)
        if va_pos == "BELOW_VAL" and current_price > poc_price * 0.995:
            long_points += weights.volume_profile * 0.8
            reasons.append("Volume Profile: Value Area Low rejection & mean reversion")
        elif va_pos == "ABOVE_VAH" and current_price < poc_price * 1.005:
            short_points += weights.volume_profile * 0.8
            reasons.append("Volume Profile: Value Area High rejection & mean reversion")
        elif va_pos == "ABOVE_VAH":
            long_points += weights.volume_profile * 0.7
            reasons.append("Volume Profile: Value Area breakout expansion")

        # D. Market Profile Initial Balance (10 pts)
        mp_ext = mp_res.get("ib_extension", "WITHIN_IB")
        if mp_ext == "BULLISH_EXTENSION":
            long_points += weights.market_profile
            reasons.append("Market Profile: Bullish Initial Balance Range Extension")
        elif mp_ext == "BEARISH_EXTENSION":
            short_points += weights.market_profile
            reasons.append("Market Profile: Bearish Initial Balance Range Extension")

        # E. VWAP & Bands (10 pts)
        vwap_pos = vwap_res.get("position", "AT_VWAP")
        if vwap_pos == "ABOVE":
            long_points += weights.vwap_position
            reasons.append("Price holding firmly above VWAP")
        elif vwap_pos == "BELOW":
            short_points += weights.vwap_position
            reasons.append("Price trading below VWAP resistance")

        # F. Momentum RSI / MACD (10 pts)
        rsi = ind_res.get("rsi", 50.0)
        macd_hist = ind_res.get("macd_hist", 0.0)
        if 42.0 <= rsi <= 68.0 and macd_hist > 0:
            long_points += weights.momentum_rsi_macd
            reasons.append(f"Bullish momentum: RSI={rsi:.1f}, MACD positive")
        elif 32.0 <= rsi <= 58.0 and macd_hist < 0:
            short_points += weights.momentum_rsi_macd
            reasons.append(f"Bearish momentum: RSI={rsi:.1f}, MACD negative")

        # G. Volatility Compatibility (10 pts)
        vol_score = vol_res.get("volatility_score", 5.0)
        long_points += vol_score
        short_points += vol_score

        # Determine winner direction and calibrated score
        if long_points > short_points and long_points >= 40.0:
            direction = "LONG"
            score = min(98.0, long_points)
            trend = "BULLISH"
        elif short_points > long_points and short_points >= 40.0:
            direction = "SHORT"
            score = min(98.0, short_points)
            trend = "BEARISH"
        else:
            direction = "NEUTRAL"
            score = max(long_points, short_points)
            trend = "NEUTRAL"

        return Agent2Signal(
            agent="technical_smc",
            symbol=buffer.symbol,
            direction=direction,
            score=round(score, 1),
            trend=trend,
            structure=struct if struct in ["BOS", "CHoCH", "CONSOLIDATION"] else "CONSOLIDATION",
            liquidity_sweep=smc_res.get("liquidity_sweep", False),
            fvg=smc_res.get("fvg", False),
            order_block=smc_res.get("order_block", False),
            vwap=vwap_pos if vwap_pos in ["ABOVE", "BELOW", "AT_VWAP"] else "AT_VWAP",
            volume_profile="SUPPORT" if va_pos in ["BELOW_VAL", "INSIDE_VA"] else "RESISTANCE",
            kelly_fraction=kelly_res.get("recommended_risk_pct", 0.005),
            details={
                "indicators": ind_res,
                "smc": smc_res,
                "liquidity": liq_res,
                "volume_profile": vp_res,
                "market_profile": mp_res,
                "vwap": vwap_res,
                "volatility": vol_res,
                "kelly": kelly_res
            },
            reasons=reasons,
            timestamp=current_utc()
        )
