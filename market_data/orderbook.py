from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import numpy as np

@dataclass
class OrderBookLevel:
    price: float
    size: float

    @property
    def notional(self) -> float:
        return self.price * self.size

@dataclass
class OrderBookManager:
    """
    Manages Level 2 Order Book depth for Delta Exchange contracts.
    Computes real-time spreads, bid/ask volume imbalances, and institutional walls.
    """
    symbol: str = "BTCUSD"
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    last_update_time: float = 0.0

    def update_from_snapshot(self, bids_raw: List[Any], asks_raw: List[Any], timestamp: Optional[float] = None):
        """
        Expects bids and asks as [[price, size], ...] or [{'price': p, 'size': s}, ...]
        """
        parsed_bids = []
        for b in bids_raw:
            if isinstance(b, (list, tuple)) and len(b) >= 2:
                parsed_bids.append(OrderBookLevel(price=float(b[0]), size=float(b[1])))
            elif isinstance(b, dict):
                parsed_bids.append(OrderBookLevel(price=float(b.get("price", b.get("limit_price", 0))), size=float(b.get("size", 0))))
        
        parsed_asks = []
        for a in asks_raw:
            if isinstance(a, (list, tuple)) and len(a) >= 2:
                parsed_asks.append(OrderBookLevel(price=float(a[0]), size=float(a[1])))
            elif isinstance(a, dict):
                parsed_asks.append(OrderBookLevel(price=float(a.get("price", a.get("limit_price", 0))), size=float(a.get("size", 0))))

        # Bids sorted descending price, asks sorted ascending price
        self.bids = sorted(parsed_bids, key=lambda x: x.price, reverse=True)
        self.asks = sorted(parsed_asks, key=lambda x: x.price, reverse=False)
        self.last_update_time = timestamp or 0.0

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> float:
        bb = self.best_bid
        ba = self.best_ask
        if bb and ba:
            return (bb + ba) / 2.0
        return bb or ba or 0.0

    @property
    def spread_usd(self) -> float:
        bb = self.best_bid
        ba = self.best_ask
        if bb and ba:
            return round(ba - bb, 4)
        return 0.0

    @property
    def spread_bps(self) -> float:
        mid = self.mid_price
        if mid > 0:
            return round((self.spread_usd / mid) * 10000.0, 2)
        return 0.0

    def calculate_imbalance(self, depth: int = 10) -> float:
        """
        Order book imbalance ratio between -1.0 (100% asks) and +1.0 (100% bids).
        """
        bid_vol = sum(b.size for b in self.bids[:depth])
        ask_vol = sum(a.size for a in self.asks[:depth])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return round((bid_vol - ask_vol) / total, 4)

    def detect_institutional_walls(self, threshold_multiplier: float = 2.5) -> Dict[str, Any]:
        """
        Identifies heavy resting limit orders indicative of institutional defense walls.
        """
        bid_sizes = [b.size for b in self.bids[:15]]
        ask_sizes = [a.size for a in self.asks[:15]]

        mean_bid = np.mean(bid_sizes) if bid_sizes else 1.0
        mean_ask = np.mean(ask_sizes) if ask_sizes else 1.0

        bid_walls = [b for b in self.bids[:15] if b.size >= (mean_bid * threshold_multiplier) and b.size > 2.0]
        ask_walls = [a for a in self.asks[:15] if a.size >= (mean_ask * threshold_multiplier) and a.size > 2.0]

        return {
            "bid_wall": {
                "price": bid_walls[0].price if bid_walls else None,
                "size": bid_walls[0].size if bid_walls else 0.0,
                "notional": bid_walls[0].notional if bid_walls else 0.0
            },
            "ask_wall": {
                "price": ask_walls[0].price if ask_walls else None,
                "size": ask_walls[0].size if ask_walls else 0.0,
                "notional": ask_walls[0].notional if ask_walls else 0.0
            },
            "total_bid_depth": sum(bid_sizes),
            "total_ask_depth": sum(ask_sizes),
            "imbalance": self.calculate_imbalance(10)
        }
