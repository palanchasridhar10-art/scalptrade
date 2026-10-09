from typing import Dict, Any, Optional
from data.schemas.market_data import OrderBook

class HeatMapEngine:
    def __init__(self, cluster_threshold_pct: float = 0.15):
        self.cluster_threshold_pct = cluster_threshold_pct

    def analyze(self, ob: Optional[OrderBook]) -> Dict[str, Any]:
        if ob is None or not ob.bids or not ob.asks:
            return {
                "liquidity_above": 0.0,
                "liquidity_below": 0.0,
                "nearest_major_liquidity_above": None,
                "nearest_major_liquidity_below": None,
                "liquidity_bias": "NEUTRAL"
            }

        mid_price = (ob.best_bid + ob.best_ask) / 2.0
        
        # Aggregate bids and asks
        bid_vol_total = sum(b.amount for b in ob.bids)
        ask_vol_total = sum(a.amount for a in ob.asks)
        
        # Find major clusters (resting walls >= 2.5x mean order size)
        mean_bid = bid_vol_total / len(ob.bids) if ob.bids else 1.0
        mean_ask = ask_vol_total / len(ob.asks) if ob.asks else 1.0
        
        major_bid_clusters = [b for b in ob.bids if b.amount >= mean_bid * 2.2]
        major_ask_clusters = [a for a in ob.asks if a.amount >= mean_ask * 2.2]
        
        nearest_bid = major_bid_clusters[0].price if major_bid_clusters else (ob.bids[-1].price if ob.bids else None)
        nearest_ask = major_ask_clusters[0].price if major_ask_clusters else (ob.asks[-1].price if ob.asks else None)
        
        total = bid_vol_total + ask_vol_total
        liq_above_ratio = ask_vol_total / total if total > 0 else 0.5
        liq_below_ratio = bid_vol_total / total if total > 0 else 0.5
        
        if liq_below_ratio > 0.60:
            bias = "SUPPORT"
        elif liq_above_ratio > 0.60:
            bias = "RESISTANCE"
        else:
            bias = "NEUTRAL"
            
        return {
            "liquidity_above": round(liq_above_ratio, 3),
            "liquidity_below": round(liq_below_ratio, 3),
            "nearest_major_liquidity_above": nearest_ask,
            "nearest_major_liquidity_below": nearest_bid,
            "liquidity_bias": bias,
            "num_bid_clusters": len(major_bid_clusters),
            "num_ask_clusters": len(major_ask_clusters)
        }
