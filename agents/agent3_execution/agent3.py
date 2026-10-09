from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

from data.schemas.signals import Agent1Signal, Agent2Signal, Agent3Decision, TradeRecord
from data.live.buffer import SymbolDataBuffer
from exchange.adapter import BaseExchangeAdapter
from config.settings import Agent3Config, RiskLimits, CooldownConfig, EmergencyConfig

from .decision import DecisionFusionEngine
from .risk import RiskEngine
from .sizing import PositionSizer
from .orders import TradeSetupBuilder
from .position_manager import PositionLifecycleManager
from .kill_switch import KillSwitch

logger = logging.getLogger("agent3.execution")

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class Agent3DecisionRiskExecution:
    """Agent 3 — Decision, Risk & Execution Agent (Sole entity authorized to trade)"""
    def __init__(
        self,
        exchange: BaseExchangeAdapter,
        config: Optional[Agent3Config] = None,
        risk_limits: Optional[RiskLimits] = None,
        cooldown: Optional[CooldownConfig] = None,
        emergency: Optional[EmergencyConfig] = None
    ):
        self.exchange = exchange
        self.config = config or Agent3Config()
        self.risk_limits = risk_limits or RiskLimits()
        
        self.fusion = DecisionFusionEngine(self.config)
        self.risk_engine = RiskEngine(self.risk_limits, cooldown, emergency)
        self.sizer = PositionSizer(self.risk_limits)
        self.setup_builder = TradeSetupBuilder(min_risk_reward=self.config.min_risk_reward)
        self.position_manager = PositionLifecycleManager(
            trailing_activation_r=self.config.trailing_stop_activation_r
        )
        self.kill_switch = KillSwitch(exchange)

    async def evaluate_and_execute(
        self,
        buffer: SymbolDataBuffer,
        agent1_sig: Agent1Signal,
        agent2_sig: Agent2Signal,
        current_time: Optional[datetime] = None
    ) -> Agent3Decision:
        account = await self.exchange.get_account_state()
        symbol = buffer.symbol
        spread_bps = buffer.orderbook.spread_bps if buffer.orderbook else 0.0
        now = current_time or current_utc()
        is_fresh = not buffer.is_stale(timeout_ms=self.risk_engine.emergency.stale_data_timeout_ms) if current_time is None else True
        
        current_price = buffer.orderbook.best_bid if buffer.orderbook else 67000.0
        
        # 1. Active Position Lifecycle Monitoring Check
        if symbol in account.positions:
            pos = account.positions[symbol]
            exit_check = self.position_manager.check_position(
                pos, current_price, agent1_sig, agent2_sig, current_time=now
            )
            if exit_check["should_exit"]:
                logger.info(f"Position exit triggered for {symbol}: {exit_check['reason']}")
                await self.exchange.close_position(symbol, reason=exit_check["reason"], timestamp=now)

        # 2. Decision / Signal Fusion Check
        fusion_res = self.fusion.fuse(agent1_sig, agent2_sig, spread_bps, is_fresh)
        
        if not fusion_res["allowed"]:
            return Agent3Decision(
                decision="NO_TRADE",
                symbol=symbol,
                direction="NEUTRAL",
                confidence=fusion_res["confidence"],
                risk_allowed=False,
                entry=current_price,
                stop_loss=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                risk_reward=0.0,
                position_size=0.0,
                notional_usd=0.0,
                agent1_score=agent1_sig.score,
                agent2_score=agent2_sig.score,
                market_regime=agent1_sig.regime,
                reasons=fusion_res["reasons"],
                risk_violations=fusion_res["violations"],
                timestamp=now
            )

        direction = fusion_res["direction"]

        # 3. Risk Engine Validation (Absolute Authority)
        risk_res = self.risk_engine.validate_candidate(
            symbol=symbol,
            direction=direction,
            account=account,
            spread_bps=spread_bps,
            data_is_fresh=is_fresh,
            current_time=now
        )

        if not risk_res["allowed"]:
            return Agent3Decision(
                decision="NO_TRADE",
                symbol=symbol,
                direction=direction,
                confidence=fusion_res["confidence"],
                risk_allowed=False,
                entry=current_price,
                stop_loss=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                risk_reward=0.0,
                position_size=0.0,
                notional_usd=0.0,
                agent1_score=agent1_sig.score,
                agent2_score=agent2_sig.score,
                market_regime=agent1_sig.regime,
                reasons=fusion_res["reasons"],
                risk_violations=risk_res["violations"],
                timestamp=now
            )

        # 4. Build Trade Setup (Entry, SL, TP1, TP2, R:R)
        setup = self.setup_builder.build_setup(
            symbol=symbol,
            direction=direction,
            current_price=current_price,
            agent1=agent1_sig,
            agent2=agent2_sig
        )

        if not setup["valid_rr"]:
            return Agent3Decision(
                decision="NO_TRADE",
                symbol=symbol,
                direction=direction,
                confidence=fusion_res["confidence"],
                risk_allowed=True,
                entry=setup["entry"],
                stop_loss=setup["stop_loss"],
                take_profit_1=setup["take_profit_1"],
                take_profit_2=setup["take_profit_2"],
                risk_reward=setup["risk_reward"],
                position_size=0.0,
                notional_usd=0.0,
                agent1_score=agent1_sig.score,
                agent2_score=agent2_sig.score,
                market_regime=agent1_sig.regime,
                reasons=["Setup Risk/Reward below required 2.0 minimum threshold"],
                risk_violations=[f"R:R ratio {setup['risk_reward']:.2f} < 2.0"],
                timestamp=now
            )

        # 5. Position Sizing
        size_res = self.sizer.calculate_size(
            account=account,
            entry_price=setup["entry"],
            stop_loss_price=setup["stop_loss"],
            fractional_kelly_pct=agent2_sig.kelly_fraction,
            risk_multiplier=risk_res["risk_multiplier"]
        )

        if size_res["quantity"] <= 0 or size_res["notional_usd"] < 10.0:
            return Agent3Decision(
                decision="NO_TRADE",
                symbol=symbol,
                direction=direction,
                confidence=fusion_res["confidence"],
                risk_allowed=False,
                entry=setup["entry"],
                stop_loss=setup["stop_loss"],
                take_profit_1=setup["take_profit_1"],
                take_profit_2=setup["take_profit_2"],
                risk_reward=setup["risk_reward"],
                position_size=0.0,
                notional_usd=0.0,
                agent1_score=agent1_sig.score,
                agent2_score=agent2_sig.score,
                market_regime=agent1_sig.regime,
                reasons=["Calculated position size below minimum notional limits"],
                risk_violations=["Position sizing evaluated to 0"],
                timestamp=now
            )

        # 6. Execute Order via Exchange Adapter
        side = "BUY" if direction == "LONG" else "SELL"
        order_res = await self.exchange.submit_market_order(
            symbol=symbol,
            side=side,
            quantity=size_res["quantity"],
            stop_loss=setup["stop_loss"],
            take_profit_1=setup["take_profit_1"],
            take_profit_2=setup["take_profit_2"],
            timestamp=now
        )

        self.risk_engine.record_execution(timestamp=now)

        return Agent3Decision(
            decision="BUY" if direction == "LONG" else "SELL",
            symbol=symbol,
            direction=direction,
            confidence=fusion_res["confidence"],
            risk_allowed=True,
            entry=setup["entry"],
            stop_loss=setup["stop_loss"],
            take_profit_1=setup["take_profit_1"],
            take_profit_2=setup["take_profit_2"],
            risk_reward=setup["risk_reward"],
            position_size=size_res["quantity"],
            notional_usd=size_res["notional_usd"],
            agent1_score=agent1_sig.score,
            agent2_score=agent2_sig.score,
            market_regime=agent1_sig.regime,
            liquidity_target=setup["take_profit_2"],
            reasons=fusion_res["reasons"],
            risk_violations=[],
            timestamp=now
        )
