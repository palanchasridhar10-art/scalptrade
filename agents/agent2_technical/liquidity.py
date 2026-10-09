from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from data.schemas.market_data import OrderBook

class LiquidityEngine:
    """
    Agent 2 Liquidity & Resting Limit Order Heatmap Engine.
    Maps resting institutional limit order clusters, structural buy/sell-side liquidity pools (BSL/SSL),
    and defense walls at specific Bitcoin price levels.
    """
    def analyze(
        self,
        df_1d: pd.DataFrame,
        df_1h: pd.DataFrame,
        current_price: float,
        orderbook: Optional[OrderBook] = None
    ) -> Dict[str, Any]:
        pdh = None
        pdl = None
        if not df_1d.empty and len(df_1d) >= 2:
            pdh = float(df_1d["high"].iloc[-2])
            pdl = float(df_1d["low"].iloc[-2])

        # 1. Structural Equal Highs (EQH) and Equal Lows (EQL) on 1H (within 0.05% tolerance)
        eqh_levels = []
        eql_levels = []
        
        if not df_1h.empty and len(df_1h) >= 10:
            highs = df_1h["high"].values[-24:]
            lows = df_1h["low"].values[-24:]
            
            for i in range(len(highs)):
                for j in range(i + 3, len(highs)):
                    if abs(highs[i] - highs[j]) / highs[i] < 0.0005:
                        eqh_levels.append(round((highs[i] + highs[j]) / 2.0, 2))
                    if abs(lows[i] - lows[j]) / lows[i] < 0.0005:
                        eql_levels.append(round((lows[i] + lows[j]) / 2.0, 2))

        # Target pools
        bsl_targets = [h for h in ([pdh] + eqh_levels) if h and h > current_price]
        ssl_targets = [l for l in ([pdl] + eql_levels) if l and l < current_price]

        nearest_bsl = min(bsl_targets) if bsl_targets else None
        nearest_ssl = max(ssl_targets) if ssl_targets else None

        # 2. Limit Orders & Heatmap Depth Analysis on Bitcoin price ladder
        resting_bids_heatmap = []
        resting_asks_heatmap = []
        total_bid_vol = 0.0
        total_ask_vol = 0.0
        nearest_major_bid_wall = None
        nearest_major_ask_wall = None
        max_bid_vol = 0.0
        max_ask_vol = 0.0

        if orderbook and orderbook.bids and orderbook.asks:
            avg_bid_vol = np.mean([b.amount for b in orderbook.bids]) if orderbook.bids else 1.0
            avg_ask_vol = np.mean([a.amount for a in orderbook.asks]) if orderbook.asks else 1.0

            # Scan top resting limit bids (Support)
            for b in orderbook.bids:
                total_bid_vol += b.amount
                is_wall = b.amount >= (avg_bid_vol * 2.2) or b.amount >= 15.0
                tag = "INSTITUTIONAL_BID_WALL" if is_wall else "LIMIT_BID"
                if ssl_targets and any(abs(b.price - s) < 15.0 for s in ssl_targets):
                    tag = "SELL_SIDE_LIQUIDITY_POOL"
                
                entry = {
                    "price": round(b.price, 2),
                    "amount_btc": round(b.amount, 3),
                    "notional_usd": round(b.price * b.amount, 2),
                    "is_wall": is_wall,
                    "tag": tag,
                    "distance_pct": round((b.price - current_price) / current_price * 100.0, 2)
                }
                resting_bids_heatmap.append(entry)
                if is_wall and b.amount > max_bid_vol:
                    max_bid_vol = b.amount
                    nearest_major_bid_wall = round(b.price, 2)

            # Scan top resting limit asks (Resistance)
            for a in orderbook.asks:
                total_ask_vol += a.amount
                is_wall = a.amount >= (avg_ask_vol * 2.2) or a.amount >= 15.0
                tag = "INSTITUTIONAL_ASK_WALL" if is_wall else "LIMIT_ASK"
                if bsl_targets and any(abs(a.price - s) < 15.0 for s in bsl_targets):
                    tag = "BUY_SIDE_LIQUIDITY_POOL"

                entry = {
                    "price": round(a.price, 2),
                    "amount_btc": round(a.amount, 3),
                    "notional_usd": round(a.price * a.amount, 2),
                    "is_wall": is_wall,
                    "tag": tag,
                    "distance_pct": round((a.price - current_price) / current_price * 100.0, 2)
                }
                resting_asks_heatmap.append(entry)
                if is_wall and a.amount > max_ask_vol:
                    max_ask_vol = a.amount
                    nearest_major_ask_wall = round(a.price, 2)

        # Calculate Heatmap resting bias
        if total_bid_vol > total_ask_vol * 1.25:
            heatmap_bias = "SUPPORT"
        elif total_ask_vol > total_bid_vol * 1.25:
            heatmap_bias = "RESISTANCE"
        else:
            heatmap_bias = "NEUTRAL"

        return {
            "pdh": pdh,
            "pdl": pdl,
            "equal_highs": list(set(eqh_levels))[:3],
            "equal_lows": list(set(eql_levels))[:3],
            "nearest_buy_side_liquidity": nearest_bsl,
            "nearest_sell_side_liquidity": nearest_ssl,
            "liquidity_targets_count": len(bsl_targets) + len(ssl_targets),
            # Resting Limit Orders Heatmap
            "heatmap_bias": heatmap_bias,
            "total_bid_volume_btc": round(total_bid_vol, 2),
            "total_ask_volume_btc": round(total_ask_vol, 2),
            "nearest_major_bid_wall": nearest_major_bid_wall,
            "nearest_major_ask_wall": nearest_major_ask_wall,
            "resting_bids": resting_bids_heatmap[:10],
            "resting_asks": resting_asks_heatmap[:10]
        }
