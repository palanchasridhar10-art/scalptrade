from typing import List, Dict, Any
from datetime import datetime, timezone
from data.schemas.market_data import Trade

class TimeSalesAnalyzer:
    def __init__(self, velocity_window_seconds: float = 60.0):
        self.velocity_window_seconds = velocity_window_seconds

    def analyze(self, trades: List[Trade]) -> Dict[str, Any]:
        if not trades:
            return {
                "valid": False,
                "buy_pressure": 0.5,
                "sell_pressure": 0.5,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "net_volume": 0.0,
                "trade_velocity": 0.0,
                "large_trades_count": 0,
                "absorption_detected": False,
                "exhaustion_detected": False,
                "bias": "BALANCED"
            }

        now = datetime.now(timezone.utc)
        recent = [
            t for t in trades 
            if (now - t.timestamp).total_seconds() <= self.velocity_window_seconds
        ] or trades[-50:]

        buy_vol = sum(t.quantity for t in recent if t.is_aggressive_buy)
        sell_vol = sum(t.quantity for t in recent if t.is_aggressive_sell)
        total_vol = buy_vol + sell_vol

        buy_pressure = (buy_vol / total_vol) if total_vol > 0 else 0.5
        sell_pressure = (sell_vol / total_vol) if total_vol > 0 else 0.5

        # Trade velocity (trades per second)
        timespan = max(1.0, (recent[-1].timestamp - recent[0].timestamp).total_seconds())
        velocity = len(recent) / timespan

        # Large trades (whales > 2.5x mean volume)
        mean_vol = total_vol / len(recent) if recent else 1.0
        large_trades = [t for t in recent if t.quantity >= mean_vol * 2.5]

        # Absorption / Exhaustion Detection:
        # Absorption: high aggressive volume with minimal price change (< 0.05%)
        price_change_pct = abs(recent[-1].price - recent[0].price) / recent[0].price if recent[0].price > 0 else 0.0
        absorption = (total_vol > mean_vol * 20.0) and (price_change_pct < 0.0005)
        
        # Exhaustion: sudden drop in velocity and volume following a sharp move
        exhaustion = (price_change_pct > 0.002) and (velocity < 1.0)

        if buy_pressure > 0.60:
            bias = "BULLISH"
        elif sell_pressure > 0.60:
            bias = "BEARISH"
        else:
            bias = "BALANCED"

        return {
            "valid": True,
            "buy_pressure": round(buy_pressure, 3),
            "sell_pressure": round(sell_pressure, 3),
            "buy_volume": round(buy_vol, 4),
            "sell_volume": round(sell_vol, 4),
            "net_volume": round(buy_vol - sell_vol, 4),
            "trade_velocity": round(velocity, 2),
            "large_trades_count": len(large_trades),
            "absorption_detected": absorption,
            "exhaustion_detected": exhaustion,
            "bias": bias
        }
