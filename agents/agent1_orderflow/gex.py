from typing import Dict, Any, Optional
from data.schemas.market_data import GEXData

class GEXAnalyzer:
    def analyze(self, gex_data: Optional[GEXData]) -> Dict[str, Any]:
        if gex_data is None or gex_data.status == "UNAVAILABLE":
            return {
                "status": "UNAVAILABLE",
                "total_gex": 0.0,
                "dealer_regime": "NEUTRAL",
                "gamma_flip_strike": None,
                "volatility_impact": "NEUTRAL",
                "score_bias": "NEUTRAL"
            }

        total_gex = gex_data.total_gex
        dealer_regime = gex_data.dealer_regime
        
        # Positive GEX => Dealer long gamma => Mean reversion dampener
        # Negative GEX => Dealer short gamma => Volatility acceleration
        if total_gex > 0 or dealer_regime == "LONG_GAMMA":
            volatility_impact = "MEAN_REVERSION_SUPPORTED"
            score_bias = "RANGE_OR_BOUNCE"
        elif total_gex < 0 or dealer_regime == "SHORT_GAMMA":
            volatility_impact = "EXPANSION_ACCELERATION"
            score_bias = "TREND_CONTINUATION"
        else:
            volatility_impact = "NEUTRAL"
            score_bias = "NEUTRAL"

        return {
            "status": gex_data.status,
            "total_gex": round(total_gex, 2),
            "call_oi": round(gex_data.call_oi, 2),
            "put_oi": round(gex_data.put_oi, 2),
            "dealer_regime": dealer_regime,
            "gamma_flip_strike": gex_data.gamma_flip_strike,
            "volatility_impact": volatility_impact,
            "score_bias": score_bias
        }
