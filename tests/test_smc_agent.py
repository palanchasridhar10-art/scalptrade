import pytest
import pandas as pd
from agents.smc_agent import SMCLiquidityAgent
from strategies.liquidity_sweep import LiquiditySweepDetector
from strategies.fair_value_gap import FairValueGapDetector
from strategies.market_structure import MarketStructureAnalyzer

def test_liquidity_sweep_detection():
    detector = LiquiditySweepDetector(min_wick_ratio=1.0)
    
    # 10 baseline candles between 67000 and 67200
    rows = []
    for i in range(10):
        rows.append({"open": 67050.0, "high": 67200.0, "low": 67000.0, "close": 67100.0, "volume": 100.0})
    
    # Candle 11 sweeps swing low (66900), but closes back at 67080 with long lower wick
    rows.append({
        "open": 67050.0,
        "high": 67100.0,
        "low": 66850.0,  # Swept below 67000
        "close": 67080.0,  # Closed back inside range
        "volume": 350.0
    })
    
    df = pd.DataFrame(rows)
    res = detector.analyze(df)
    assert res.has_sweep is True
    assert res.direction == "BULLISH_SWEEP"
    assert res.swept_level == 67000.0
    assert res.invalidation_level == 66850.0

def test_fair_value_gap_detection():
    detector = FairValueGapDetector(min_gap_pct=0.01)
    
    # 3-candle sequence with Bullish FVG
    c1 = {"open": 67000.0, "high": 67050.0, "low": 66950.0, "close": 67020.0, "volume": 100.0}
    c2 = {"open": 67030.0, "high": 67400.0, "low": 67020.0, "close": 67380.0, "volume": 500.0}
    c3 = {"open": 67390.0, "high": 67600.0, "low": 67200.0, "close": 67550.0, "volume": 200.0}
    
    # Low of c3 (67200) > High of c1 (67050) -> FVG gap = 150 points
    df = pd.DataFrame([c1, c2, c3])
    res = detector.analyze(df)
    assert res.has_fvg is True
    assert res.direction == "BULLISH_FVG"
    assert res.gap_top == 67200.0
    assert res.gap_bottom == 67050.0
    assert res.consequent_encroachment == 67125.0

def test_smc_agent_eval():
    agent = SMCLiquidityAgent(min_rr=2.0)
    prices = [65000.0 + (i * 30.0) for i in range(40)]
    df = pd.DataFrame({
        "open": [p - 5.0 for p in prices],
        "high": [p + 20.0 for p in prices],
        "low": [p - 15.0 for p in prices],
        "close": prices,
        "volume": [100.0] * 40
    })
    sig = agent.evaluate(df)
    assert sig.direction in ["LONG", "SHORT", "NEUTRAL"]
    assert sig.score >= 0.0
