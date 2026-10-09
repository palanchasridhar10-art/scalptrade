from typing import Dict, Any, Optional
from data.schemas.market_data import OrderBook

class OrderBookAnalyzer:
    def __init__(self, depth_levels: int = 20):
        self.depth_levels = depth_levels

    def analyze(self, ob: Optional[OrderBook]) -> Dict[str, Any]:
        if ob is None or not ob.bids or not ob.asks:
            return {
                "valid": False,
                "bid_depth": 0.0,
                "ask_depth": 0.0,
                "imbalance": 0.0,
                "spread": 0.0,
                "spread_bps": 0.0,
                "bias": "BALANCED",
                "score_contribution": 0.0,
                "reason": "Order book data unavailable"
            }

        bids = ob.bids[:self.depth_levels]
        asks = ob.asks[:self.depth_levels]

        bid_volume = sum(b.amount for b in bids)
        ask_volume = sum(a.amount for a in asks)
        total_vol = bid_volume + ask_volume

        # Imbalance = (Bid Vol - Ask Vol) / (Bid Vol + Ask Vol)
        imbalance = (bid_volume - ask_volume) / total_vol if total_vol > 0 else 0.0

        if imbalance > 0.25:
            bias = "BID"
        elif imbalance < -0.25:
            bias = "ASK"
        else:
            bias = "BALANCED"

        # Check for spoofing / liquidity pull heuristic
        # (sudden top-heavy concentration vs deep depth ratio)
        top3_bid = sum(b.amount for b in bids[:3])
        top3_ask = sum(a.amount for a in asks[:3])
        bid_concentration = top3_bid / bid_volume if bid_volume > 0 else 0.0
        ask_concentration = top3_ask / ask_volume if ask_volume > 0 else 0.0
        
        spoofing_risk = "LOW"
        if bid_concentration > 0.70 or ask_concentration > 0.70:
            spoofing_risk = "MEDIUM"

        return {
            "valid": True,
            "bid_depth": bid_volume,
            "ask_depth": ask_volume,
            "imbalance": imbalance,
            "spread": ob.spread,
            "spread_bps": ob.spread_bps,
            "bias": bias,
            "spoofing_risk": spoofing_risk,
            "best_bid": ob.best_bid,
            "best_ask": ob.best_ask
        }
