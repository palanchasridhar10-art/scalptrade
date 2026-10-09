from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from data.schemas.market_data import OrderBook, Trade, Candle, GEXData
from data.schemas.signals import Agent1Signal
from data.live.buffer import SymbolDataBuffer
from config.settings import Agent1Config

from .orderbook import OrderBookAnalyzer
from .heatmap import HeatMapEngine
from .timesales import TimeSalesAnalyzer
from .footprint import FootprintAnalyzer
from .delta import CVDAnalyzer
from .gex import GEXAnalyzer
from .regime import MarketRegimeDetector

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class Agent1OrderFlow:
    """Agent 1 — Market Microstructure & Order Flow Agent"""
    def __init__(self, config: Optional[Agent1Config] = None):
        self.config = config or Agent1Config()
        self.ob_analyzer = OrderBookAnalyzer(depth_levels=self.config.min_orderbook_depth_levels)
        self.heatmap_engine = HeatMapEngine()
        self.timesales_analyzer = TimeSalesAnalyzer()
        self.footprint_analyzer = FootprintAnalyzer()
        self.cvd_analyzer = CVDAnalyzer(lookback_bars=self.config.cvd_divergence_lookback_bars)
        self.gex_analyzer = GEXAnalyzer()
        self.regime_detector = MarketRegimeDetector()

    def evaluate(self, buffer: SymbolDataBuffer) -> Agent1Signal:
        reasons: List[str] = []
        
        # 1. Order Book
        ob_res = self.ob_analyzer.analyze(buffer.orderbook)
        
        # 2. Heatmap
        hm_res = self.heatmap_engine.analyze(buffer.orderbook)
        
        # 3. Time & Sales
        recent_trades = buffer.get_recent_trades(limit=300)
        ts_res = self.timesales_analyzer.analyze(recent_trades)
        
        # 4. Footprint
        fp_res = self.footprint_analyzer.analyze(recent_trades)
        
        # 5. CVD & Divergence
        cvd_df = buffer.get_cvd_series(limit=100)
        candles_1m = buffer.get_candles_df("1M", limit=30)
        cvd_res = self.cvd_analyzer.analyze(cvd_df, candles_1m)
        
        # 6. GEX
        gex_res = self.gex_analyzer.analyze(buffer.gex_data)
        
        # 7. Regime
        regime_res = self.regime_detector.classify(
            candles_df=candles_1m,
            imbalance=ob_res.get("imbalance", 0.0),
            buy_pressure=ts_res.get("buy_pressure", 0.5),
            cvd_direction=cvd_res.get("cvd_direction", "FLAT")
        )
        regime = regime_res.get("regime", "UNCERTAIN")

        # --- SCORING SYSTEM (0-100) ---
        long_points = 0.0
        short_points = 0.0
        weights = self.config.weights

        # A. Order Book Imbalance (20 pts)
        imb = ob_res.get("imbalance", 0.0)
        if imb > 0.20:
            pts = min(20.0, (imb / 0.5) * weights.orderbook_imbalance)
            long_points += pts
            reasons.append(f"Order book bid-skewed ({imb:+.2f})")
        elif imb < -0.20:
            pts = min(20.0, (abs(imb) / 0.5) * weights.orderbook_imbalance)
            short_points += pts
            reasons.append(f"Order book ask-skewed ({imb:+.2f})")

        # B. Time & Sales Velocity & Aggression (20 pts)
        bp = ts_res.get("buy_pressure", 0.5)
        sp = ts_res.get("sell_pressure", 0.5)
        if bp > 0.58:
            pts = min(20.0, ((bp - 0.5) / 0.3) * weights.timesales_velocity)
            long_points += pts
            reasons.append(f"Aggressive buy pressure ({bp:.1%})")
        elif sp > 0.58:
            pts = min(20.0, ((sp - 0.5) / 0.3) * weights.timesales_velocity)
            short_points += pts
            reasons.append(f"Aggressive sell pressure ({sp:.1%})")

        if ts_res.get("absorption_detected"):
            reasons.append("T&S volume absorption detected")

        # C. CVD Trend & Divergence (20 pts)
        cvd_dir = cvd_res.get("cvd_direction", "FLAT")
        cvd_div = cvd_res.get("divergence", "NONE")
        if cvd_div == "BULLISH_DIV":
            long_points += weights.cvd_divergence
            reasons.append("Bullish CVD divergence (Price Lower Low vs CVD Higher Low)")
        elif cvd_div == "BEARISH_DIV":
            short_points += weights.cvd_divergence
            reasons.append("Bearish CVD divergence (Price Higher High vs CVD Lower High)")
        elif cvd_dir == "UP":
            long_points += weights.cvd_divergence * 0.75
            reasons.append("CVD trend expanding upward")
        elif cvd_dir == "DOWN":
            short_points += weights.cvd_divergence * 0.75
            reasons.append("CVD trend expanding downward")

        # D. Footprint Stacked Imbalances (15 pts)
        s_buys = fp_res.get("stacked_buy_imbalances", 0)
        s_sells = fp_res.get("stacked_sell_imbalances", 0)
        if s_buys > 0:
            long_points += min(15.0, s_buys * 5.0)
            reasons.append(f"Footprint stacked buy imbalance ({s_buys} zones)")
        if s_sells > 0:
            short_points += min(15.0, s_sells * 5.0)
            reasons.append(f"Footprint stacked sell imbalance ({s_sells} zones)")

        # E. Heatmap / Liquidity Bias (15 pts)
        liq_bias = hm_res.get("liquidity_bias", "NEUTRAL")
        if liq_bias == "SUPPORT":
            long_points += weights.liquidity_heatmap * 0.8
            reasons.append("Heavy resting bid support cluster below price")
        elif liq_bias == "RESISTANCE":
            short_points += weights.liquidity_heatmap * 0.8
            reasons.append("Heavy resting ask defense cluster above price")

        # F. Regime Alignment (10 pts)
        if regime in ["TREND_UP", "BREAKOUT"]:
            long_points += weights.regime_alignment
            reasons.append(f"Regime aligns bullish ({regime})")
        elif regime in ["TREND_DOWN", "BREAKDOWN"]:
            short_points += weights.regime_alignment
            reasons.append(f"Regime aligns bearish ({regime})")

        # Determine winner direction and calibrated score
        if long_points > short_points and long_points >= 40.0:
            direction = "LONG"
            score = min(98.0, long_points)
        elif short_points > long_points and short_points >= 40.0:
            direction = "SHORT"
            score = min(98.0, short_points)
        else:
            direction = "NEUTRAL"
            score = max(long_points, short_points)

        return Agent1Signal(
            agent="orderflow",
            symbol=buffer.symbol,
            direction=direction,
            score=round(score, 1),
            regime=regime,
            delta=cvd_res.get("latest_delta", 0.0),
            cvd_direction=cvd_div if cvd_div != "NONE" else cvd_dir,
            orderbook_bias=ob_res.get("bias", "BALANCED"),
            liquidity_bias=hm_res.get("liquidity_bias", "NEUTRAL"),
            gex_status=gex_res.get("status", "UNAVAILABLE"),
            details={
                "orderbook": ob_res,
                "heatmap": hm_res,
                "timesales": ts_res,
                "footprint": fp_res,
                "cvd": cvd_res,
                "gex": gex_res,
                "regime": regime_res
            },
            reasons=reasons,
            timestamp=current_utc()
        )
