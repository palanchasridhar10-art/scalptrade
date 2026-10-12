import asyncio
import pytest
from exchange.delta_client import DeltaExchangeClient
from exchange.order_manager import OrderManager
from risk.risk_manager import RiskManager
from risk.position_sizing import PositionSizer
from agents.market_agent import MarketAgentSignal
from agents.smc_agent import SMCAgentSignal
from agents.execution_agent import ExecutionAgent

def test_execution_agent_consensus_and_duplicate_prevention():
    async def _async_test():
        client = DeltaExchangeClient(is_demo=True)
        rm = RiskManager(risk_per_trade_pct=0.0025, max_simultaneous_positions=1)
        om = OrderManager(client=client, risk_manager=rm, simulated=True, initial_balance=10000.0)
        sizer = PositionSizer()
        agent3 = ExecutionAgent(order_manager=om, risk_manager=rm, position_sizer=sizer, min_agent_score=75.0)

        # 1. Consensus Failure: Agent 1 is SHORT but Agent 2 is LONG
        a1_disagree = MarketAgentSignal(
            regime="TRENDING_BEARISH",
            trend_probability=0.8,
            volatility_atr=20.0,
            volatility_regime="NORMAL",
            direction_bias="SHORT",
            score=85.0
        )
        a2_long = SMCAgentSignal(
            direction="LONG",
            score=88.0,
            entry_price=67000.0,
            invalidation_level=66800.0,
            take_profit_level=67500.0,
            risk_reward_ratio=2.5,
            structure="BULLISH_BOS",
            has_liquidity_sweep=True,
            has_fvg=True,
            has_order_block=True,
            valuation_zone="DISCOUNT"
        )

        dec_disagree = await agent3.evaluate_and_execute(
            symbol="BTCUSD",
            product_id=27,
            agent1_sig=a1_disagree,
            agent2_sig=a2_long,
            spread_bps=0.8
        )
        assert dec_disagree.action == "NO_TRADE"
        assert dec_disagree.risk_approved is False

        # 2. Valid Consensus: Both Agent 1 and Agent 2 agree on LONG
        a1_agree = MarketAgentSignal(
            regime="TRENDING_BULLISH",
            trend_probability=0.85,
            volatility_atr=20.0,
            volatility_regime="NORMAL",
            direction_bias="LONG",
            score=88.0
        )
        dec_agree = await agent3.evaluate_and_execute(
            symbol="BTCUSD",
            product_id=27,
            agent1_sig=a1_agree,
            agent2_sig=a2_long,
            spread_bps=0.8
        )
        assert dec_agree.action == "EXECUTE_BUY"
        assert dec_agree.risk_approved is True
        assert "BTCUSD" in om.positions

        # 3. Duplicate Order Prevention: Second execution attempt while position is active
        dec_dup = await agent3.evaluate_and_execute(
            symbol="BTCUSD",
            product_id=27,
            agent1_sig=a1_agree,
            agent2_sig=a2_long,
            spread_bps=0.8
        )
        assert dec_dup.action == "NO_TRADE"
        assert dec_dup.risk_approved is False
        assert any("POSITION LIMIT" in v for v in dec_dup.risk_violations)

    asyncio.run(_async_test())
