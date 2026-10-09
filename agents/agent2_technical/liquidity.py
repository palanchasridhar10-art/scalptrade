from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

class LiquidityEngine:
    def analyze(self, df_1d: pd.DataFrame, df_1h: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        pdh = None
        pdl = None
        if not df_1d.empty and len(df_1d) >= 2:
            pdh = float(df_1d["high"].iloc[-2])
            pdl = float(df_1d["low"].iloc[-2])

        # Find Equal Highs (EQH) and Equal Lows (EQL) on 1H (within 0.05% tolerance)
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

        return {
            "pdh": pdh,
            "pdl": pdl,
            "equal_highs": list(set(eqh_levels))[:3],
            "equal_lows": list(set(eql_levels))[:3],
            "nearest_buy_side_liquidity": nearest_bsl,
            "nearest_sell_side_liquidity": nearest_ssl,
            "liquidity_targets_count": len(bsl_targets) + len(ssl_targets)
        }
