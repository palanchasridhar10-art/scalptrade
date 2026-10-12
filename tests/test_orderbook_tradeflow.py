import pytest
from market_data.orderbook import OrderBookManager
from market_data.trade_flow import TradeFlowTracker

def test_orderbook_depth_and_spread():
    ob = OrderBookManager(symbol="BTCUSD")
    bids = [[67000.0, 2.5], [66990.0, 4.0], [66980.0, 15.0]]
    asks = [[67010.0, 1.8], [67020.0, 3.2], [67030.0, 20.0]]
    ob.update_from_snapshot(bids, asks)

    assert ob.best_bid == 67000.0
    assert ob.best_ask == 67010.0
    assert ob.mid_price == 67005.0
    assert ob.spread_usd == 10.0
    assert ob.spread_bps > 1.0

    walls = ob.detect_institutional_walls(threshold_multiplier=2.0)
    assert walls["bid_wall"]["price"] == 66980.0
    assert walls["ask_wall"]["price"] == 67030.0
    assert "imbalance" in walls

def test_trade_flow_cvd():
    tf = TradeFlowTracker()
    tf.add_trade(price=67000.0, size=1.5, side="buy")
    tf.add_trade(price=67005.0, size=2.0, side="buy")
    tf.add_trade(price=67002.0, size=0.5, side="sell")

    metrics = tf.get_flow_metrics(window_seconds=10.0)
    assert metrics["trades_count"] == 3
    assert metrics["recent_cvd"] == 3.0  # (1.5 + 2.0) - 0.5 = 3.0
    assert metrics["taker_buy_ratio"] > 0.8
    assert "BUY_FLOW" in metrics["flow_bias"]
