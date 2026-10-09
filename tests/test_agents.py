import pytest
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np

from data.schemas.market_data import OrderBook, OrderBookLevel, Trade, Candle
from data.schemas.signals import Agent1Signal, Agent2Signal
from data.live.buffer import SymbolDataBuffer
from agents.agent1_orderflow import Agent1OrderFlow
from agents.agent2_technical import Agent2TechnicalSMC
from agents.agent3_execution import DecisionFusionEngine, Agent3DecisionRiskExecution
from exchange.paper import PaperExchange

def test_orderbook_imbalance():
    buffer = SymbolDataBuffer("BTCUSDT")
    bids = [OrderBookLevel(price=67000.0 - i, amount=10.0) for i in range(10)]
    asks = [OrderBookLevel(price=67001.0 + i, amount=2.0) for i in range(10)]
    ob = OrderBook(symbol="BTCUSDT", bids=bids, asks=asks)
    buffer.update_orderbook(ob)

    agent1 = Agent1OrderFlow()
    sig = agent1.evaluate(buffer)
    
    assert sig.symbol == "BTCUSDT"
    assert sig.orderbook_bias == "BID"
    assert sig.details["orderbook"]["imbalance"] > 0.50

def test_agent_disagreement_no_trade():
    """Rule 3: Agent Disagreement MUST equal NO_TRADE"""
    fusion = DecisionFusionEngine()
    now = datetime.now(timezone.utc)
    
    a1_buy = Agent1Signal(
        symbol="BTCUSDT",
        direction="LONG",
        score=88.0,
        regime="TREND_UP",
        delta=5000.0,
        cvd_direction="UP",
        orderbook_bias="BID",
        liquidity_bias="SUPPORT",
        gex_status="UNAVAILABLE",
        timestamp=now
    )
    
    a2_sell = Agent2Signal(
        symbol="BTCUSDT",
        direction="SHORT",
        score=89.0,
        trend="BEARISH",
        structure="BOS",
        vwap="BELOW",
        volume_profile="RESISTANCE",
        kelly_fraction=0.005,
        timestamp=now
    )
    
    res = fusion.fuse(a1_buy, a2_sell, spread_bps=1.0, data_is_fresh=True)
    assert res["allowed"] is False
    assert res["direction"] == "NEUTRAL"
    assert any("Agent disagreement" in v for v in res["violations"])

def test_agent_consensus_success():
    fusion = DecisionFusionEngine()
    now = datetime.now(timezone.utc)
    
    a1_buy = Agent1Signal(
        symbol="BTCUSDT",
        direction="LONG",
        score=88.0,
        regime="TREND_UP",
        delta=5000.0,
        cvd_direction="UP",
        orderbook_bias="BID",
        liquidity_bias="SUPPORT",
        gex_status="ESTIMATED",
        timestamp=now
    )
    
    a2_buy = Agent2Signal(
        symbol="BTCUSDT",
        direction="LONG",
        score=91.0,
        trend="BULLISH",
        structure="BOS",
        vwap="ABOVE",
        volume_profile="SUPPORT",
        kelly_fraction=0.005,
        timestamp=now
    )
    
    res = fusion.fuse(a1_buy, a2_buy, spread_bps=1.0, data_is_fresh=True)
    assert res["allowed"] is True
    assert res["direction"] == "LONG"
    assert res["confidence"] >= 85.0
