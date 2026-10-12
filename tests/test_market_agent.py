import pytest
import pandas as pd
import numpy as np
from agents.market_agent import MarketAnalysisAgent

def test_market_agent_regime_and_volatility():
    agent = MarketAnalysisAgent()

    # Generate synthetic bullish trend
    prices = [60000.0 + (i * 25.0) for i in range(50)]
    df_bull = pd.DataFrame({
        "open": [p - 5.0 for p in prices],
        "high": [p + 15.0 for p in prices],
        "low": [p - 10.0 for p in prices],
        "close": prices,
        "volume": [100.0] * 50
    })

    sig = agent.evaluate(df_bull)
    assert sig.regime in ["TRENDING_BULLISH", "HIGH_VOLATILITY"]
    assert sig.direction_bias == "LONG"
    assert sig.trend_probability >= 0.70
    assert sig.volatility_atr > 0
    assert sig.score >= 70.0
