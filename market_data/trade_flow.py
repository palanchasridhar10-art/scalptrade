from typing import List, Dict, Any, Optional
from collections import deque
import time

class TradeFlowTracker:
    """
    Monitors live public trades on Delta Exchange.
    Calculates Cumulative Volume Delta (CVD), buyer/seller aggression ratio, and volume bursts.
    """
    def __init__(self, max_history: int = 2000):
        self.trades: deque = deque(maxlen=max_history)
        self.cumulative_volume_delta: float = 0.0
        self.buyer_taker_volume: float = 0.0
        self.seller_taker_volume: float = 0.0

    def add_trade(self, price: float, size: float, side: str, timestamp: Optional[float] = None):
        """
        side: 'buy' (buyer is aggressive taker) or 'sell' (seller is aggressive taker)
        """
        ts = timestamp or time.time()
        is_buy = side.lower() == "buy"
        delta = size if is_buy else -size
        
        self.cumulative_volume_delta += delta
        if is_buy:
            self.buyer_taker_volume += size
        else:
            self.seller_taker_volume += size

        self.trades.append({
            "timestamp": ts,
            "price": price,
            "size": size,
            "side": side.lower(),
            "delta": delta,
            "cvd": self.cumulative_volume_delta
        })

    def get_flow_metrics(self, window_seconds: float = 60.0) -> Dict[str, Any]:
        """
        Calculates trade flow metrics over a trailing time window.
        """
        cutoff = time.time() - window_seconds
        recent = [t for t in self.trades if t["timestamp"] >= cutoff]

        if not recent:
            return {
                "trades_count": 0,
                "recent_cvd": 0.0,
                "buy_volume": 0.0,
                "sell_volume": 0.0,
                "taker_buy_ratio": 0.5,
                "flow_bias": "NEUTRAL"
            }

        buy_vol = sum(t["size"] for t in recent if t["side"] == "buy")
        sell_vol = sum(t["size"] for t in recent if t["side"] == "sell")
        total_vol = buy_vol + sell_vol
        
        ratio = (buy_vol / total_vol) if total_vol > 0 else 0.5
        recent_cvd = buy_vol - sell_vol

        if ratio >= 0.65:
            bias = "STRONG_BUY_FLOW"
        elif ratio >= 0.54:
            bias = "BUY_FLOW"
        elif ratio <= 0.35:
            bias = "STRONG_SELL_FLOW"
        elif ratio <= 0.46:
            bias = "SELL_FLOW"
        else:
            bias = "NEUTRAL"

        return {
            "trades_count": len(recent),
            "recent_cvd": round(recent_cvd, 4),
            "total_cvd": round(self.cumulative_volume_delta, 4),
            "buy_volume": round(buy_vol, 4),
            "sell_volume": round(sell_vol, 4),
            "taker_buy_ratio": round(ratio, 4),
            "flow_bias": bias
        }
