from typing import List, Dict, Any
from collections import defaultdict
from data.schemas.market_data import Trade

class FootprintAnalyzer:
    def __init__(self, tick_size: float = 1.0, imbalance_ratio: float = 3.0):
        self.tick_size = tick_size
        self.imbalance_ratio = imbalance_ratio

    def analyze(self, trades: List[Trade]) -> Dict[str, Any]:
        if not trades:
            return {
                "poc_price": 0.0,
                "stacked_buy_imbalances": 0,
                "stacked_sell_imbalances": 0,
                "absorption_price": None,
                "delta_profile": {}
            }

        # Bucket trades into discrete price levels
        bid_vol_by_level = defaultdict(float)
        ask_vol_by_level = defaultdict(float)
        total_vol_by_level = defaultdict(float)

        for t in trades:
            level = round(t.price / self.tick_size) * self.tick_size
            if t.is_aggressive_buy:
                ask_vol_by_level[level] += t.quantity
            else:
                bid_vol_by_level[level] += t.quantity
            total_vol_by_level[level] += t.quantity

        # Find Footprint POC
        poc_price = max(total_vol_by_level.items(), key=lambda x: x[1])[0] if total_vol_by_level else 0.0

        # Detect stacked diagonal imbalances (>= 3 consecutive levels with buy/sell ratio >= 3.0)
        sorted_levels = sorted(total_vol_by_level.keys())
        stacked_buys = 0
        stacked_sells = 0
        current_buy_streak = 0
        current_sell_streak = 0

        for lvl in sorted_levels:
            b_vol = bid_vol_by_level[lvl]
            a_vol = ask_vol_by_level[lvl]
            
            if b_vol > 0 and (a_vol / b_vol) >= self.imbalance_ratio:
                current_buy_streak += 1
                if current_buy_streak >= 3:
                    stacked_buys += 1
            else:
                current_buy_streak = 0

            if a_vol > 0 and (b_vol / a_vol) >= self.imbalance_ratio:
                current_sell_streak += 1
                if current_sell_streak >= 3:
                    stacked_sells += 1
            else:
                current_sell_streak = 0

        return {
            "poc_price": poc_price,
            "stacked_buy_imbalances": stacked_buys,
            "stacked_sell_imbalances": stacked_sells,
            "absorption_price": poc_price if max(total_vol_by_level.values(), default=0.0) > 10.0 else None,
            "total_levels_tracked": len(sorted_levels)
        }
