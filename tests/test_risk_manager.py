import pytest
from risk.risk_manager import RiskManager
from risk.position_sizing import PositionSizer

def test_position_sizer_equity_risk():
    sizer = PositionSizer(risk_per_trade_pct=0.0025, max_leverage=25.0)
    
    # $10,000 equity -> 0.25% risk = $25.00
    # Entry = 67,000, Stop Loss = 66,500 (Risk distance = 500)
    # Expected quantity = 25 / 500 = 0.05 BTC
    res = sizer.calculate(account_equity=10000.0, entry_price=67000.0, stop_loss_price=66500.0)
    assert res.allowed is True
    assert res.quantity == 0.05
    assert res.risk_amount_usd == 25.00
    assert res.notional_usd == 3350.00
    assert res.effective_leverage == 0.34  # Well below 25x

def test_position_sizer_max_leverage_capping():
    sizer = PositionSizer(risk_per_trade_pct=0.0025, max_leverage=25.0)
    
    # Very tight SL (distance = 1 point) would demand 25.0 BTC = $1.67M notional (>167x leverage)
    # Must be capped strictly at 25x leverage ($250,000 notional)
    res = sizer.calculate(account_equity=10000.0, entry_price=67000.0, stop_loss_price=66999.0)
    assert res.allowed is True
    assert res.effective_leverage <= 25.0
    assert res.notional_usd <= 250000.0

def test_risk_manager_veto_authority():
    rm = RiskManager(
        risk_per_trade_pct=0.0025,
        daily_loss_limit_pct=0.01,
        max_simultaneous_positions=1,
        max_leverage=25.0,
        require_stop_loss=True,
        require_take_profit=True,
        min_risk_reward_ratio=2.0
    )
    rm.daily_starting_equity = 10000.0

    # 1. Valid Candidate Check
    v_ok = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=10000.0,
        active_positions_count=0,
        entry_price=67000.0,
        stop_loss_price=66800.0,
        take_profit_price=67500.0,  # 500 / 200 = 2.5 R:R
        spread_bps=0.8,
        requested_quantity=0.05
    )
    assert v_ok.allowed is True

    # 2. Veto on Missing Stop-Loss
    v_no_sl = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=10000.0,
        active_positions_count=0,
        entry_price=67000.0,
        stop_loss_price=None,
        take_profit_price=67500.0,
        spread_bps=0.8
    )
    assert v_no_sl.allowed is False
    assert any("Stop-Loss" in viol for viol in v_no_sl.violations)

    # 3. Veto on R:R < 2.0
    v_bad_rr = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=10000.0,
        active_positions_count=0,
        entry_price=67000.0,
        stop_loss_price=66800.0,  # 200 risk
        take_profit_price=67200.0,  # 200 reward = 1.0 R:R (< 2.0)
        spread_bps=0.8
    )
    assert v_bad_rr.allowed is False
    assert any("RISK/REWARD" in viol for viol in v_bad_rr.violations)

    # 4. Veto on Max Simultaneous Positions (Already 1 active)
    v_pos_limit = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=10000.0,
        active_positions_count=1,
        entry_price=67000.0,
        stop_loss_price=66800.0,
        take_profit_price=67500.0,
        spread_bps=0.8
    )
    assert v_pos_limit.allowed is False
    assert any("POSITION LIMIT" in viol for viol in v_pos_limit.violations)

    # 5. Veto on Daily Loss Limit Breach (> 1.0% = $100.00 loss)
    v_daily_loss = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=9880.0,  # $120 daily loss
        active_positions_count=0,
        entry_price=67000.0,
        stop_loss_price=66800.0,
        take_profit_price=67500.0,
        spread_bps=0.8
    )
    assert v_daily_loss.allowed is False
    assert any("DAILY LOSS LIMIT" in viol for viol in v_daily_loss.violations)

    # 6. Circuit breaker on repeated API errors
    rm.record_api_error()
    rm.record_api_error()
    rm.record_api_error()
    v_err = rm.validate_trade_candidate(
        symbol="BTCUSD",
        current_equity=10000.0,
        active_positions_count=0,
        entry_price=67000.0,
        stop_loss_price=66800.0,
        take_profit_price=67500.0,
        spread_bps=0.8
    )
    assert v_err.allowed is False
    assert any("CIRCUIT BREAKER" in viol for viol in v_err.violations)
