import pytest
import asyncio
from datetime import datetime, timezone

from exchange.account import AccountState, Position
from exchange.paper import PaperExchange
from agents.agent3_execution.risk import RiskEngine
from agents.agent3_execution.sizing import PositionSizer
from agents.agent3_execution.kill_switch import KillSwitch
from config.settings import RiskLimits

def test_risk_engine_daily_loss_veto():
    risk_limits = RiskLimits(max_daily_loss_pct=0.015)
    risk = RiskEngine(limits=risk_limits)
    
    account = AccountState(
        initial_balance=10000.0,
        balance=9800.0,
        daily_starting_equity=10000.0
    )
    res = risk.validate_candidate("BTCUSDT", "LONG", account, spread_bps=1.0, data_is_fresh=True)
    assert res["allowed"] is False
    assert any("DAILY LOSS LIMIT REACHED" in v for v in res["violations"])

def test_risk_engine_stale_data_veto():
    risk = RiskEngine()
    account = AccountState(initial_balance=10000.0, balance=10000.0)
    
    res = risk.validate_candidate("BTCUSDT", "LONG", account, spread_bps=1.0, data_is_fresh=False)
    assert res["allowed"] is False
    assert any("STALE FEED" in v for v in res["violations"])

def test_position_sizer_kelly_and_equity_cap():
    limits = RiskLimits(
        max_risk_per_trade_pct=0.005,
        max_leverage=3.0,
        max_position_size_usd=50000.0
    )
    sizer = PositionSizer(limits)
    account = AccountState(initial_balance=10000.0, balance=10000.0)
    
    entry = 67000.0
    stop_loss = 66665.0
    
    res = sizer.calculate_size(
        account=account,
        entry_price=entry,
        stop_loss_price=stop_loss,
        fractional_kelly_pct=0.005
    )
    
    assert res["notional_usd"] <= 10000.0 * 3.0
    assert res["risk_usd"] <= 50.0 + 1.0
    assert res["quantity"] > 0

def test_kill_switch_flattens_positions():
    async def _async_test():
        exchange = PaperExchange(initial_balance=10000.0)
        await exchange.connect()
        
        await exchange.submit_market_order("BTCUSDT", "BUY", 0.1, 66000.0, 68000.0, 69000.0)
        acc = await exchange.get_account_state()
        assert "BTCUSDT" in acc.positions
        
        kill = KillSwitch(exchange)
        res = await kill.trigger("TEST_EMERGENCY")
        
        assert res["kill_switch_active"] is True
        acc_after = await exchange.get_account_state()
        assert len(acc_after.positions) == 0

    asyncio.run(_async_test())
