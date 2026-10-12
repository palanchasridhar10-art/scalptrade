import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import time

from agents.market_agent import MarketAgentSignal
from agents.smc_agent import SMCAgentSignal
from risk.risk_manager import RiskManager, RiskValidationResult
from risk.position_sizing import PositionSizer, PositionSizeResult
from exchange.order_manager import OrderManager

logger = logging.getLogger("execution_agent")

@dataclass
class ExecutionDecision:
    action: str  # "EXECUTE_BUY", "EXECUTE_SELL", "NO_TRADE"
    symbol: str
    direction: str  # "LONG", "SHORT", "NEUTRAL"
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    quantity: float
    notional_usd: float
    effective_leverage: float
    risk_approved: bool
    reasons: List[str] = field(default_factory=list)
    risk_violations: List[str] = field(default_factory=list)

class ExecutionAgent:
    """
    Agent 3 — Execution & Signal Validation.
    Receives signals from Agent 1 (Market Analysis) and Agent 2 (SMC Analysis).
    Enforces Signal Validator consensus, submits candidate to Risk Manager for absolute veto review,
    calculates dynamic 0.25% equity position sizing, and executes via OrderManager.
    """
    def __init__(
        self,
        order_manager: OrderManager,
        risk_manager: RiskManager,
        position_sizer: Optional[PositionSizer] = None,
        min_agent_score: float = 75.0
    ):
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.sizer = position_sizer or PositionSizer()
        self.min_agent_score = min_agent_score

    async def evaluate_and_execute(
        self,
        symbol: str,
        product_id: int,
        agent1_sig: MarketAgentSignal,
        agent2_sig: SMCAgentSignal,
        spread_bps: float
    ) -> ExecutionDecision:
        reasons = []
        violations = []

        # 1. SIGNAL VALIDATOR: Check Cross-Agent Consensus
        direction_agree = (
            agent1_sig.direction_bias in ["LONG", "SHORT"] and
            agent1_sig.direction_bias == agent2_sig.direction
        )

        score_ok = (
            agent1_sig.score >= self.min_agent_score and
            agent2_sig.score >= self.min_agent_score
        )

        rr_ok = agent2_sig.risk_reward_ratio >= self.risk_manager.min_risk_reward_ratio

        if not direction_agree:
            reasons.append(f"Consensus failure: Agent 1 ({agent1_sig.direction_bias}) and Agent 2 ({agent2_sig.direction}) do not agree.")
            return ExecutionDecision(
                action="NO_TRADE",
                symbol=symbol,
                direction="NEUTRAL",
                confidence=0.0,
                entry_price=agent2_sig.entry_price,
                stop_loss=0.0,
                take_profit=0.0,
                risk_reward=0.0,
                quantity=0.0,
                notional_usd=0.0,
                effective_leverage=0.0,
                risk_approved=False,
                reasons=reasons,
                risk_violations=["Agents lack directional agreement."]
            )

        if not score_ok:
            reasons.append(f"Confidence threshold not met: A1 Score {agent1_sig.score:.1f} / A2 Score {agent2_sig.score:.1f} < {self.min_agent_score:.1f}")
            return ExecutionDecision(
                action="NO_TRADE",
                symbol=symbol,
                direction=agent2_sig.direction,
                confidence=(agent1_sig.score + agent2_sig.score) / 2.0,
                entry_price=agent2_sig.entry_price,
                stop_loss=agent2_sig.invalidation_level,
                take_profit=agent2_sig.take_profit_level,
                risk_reward=agent2_sig.risk_reward_ratio,
                quantity=0.0,
                notional_usd=0.0,
                effective_leverage=0.0,
                risk_approved=False,
                reasons=reasons,
                risk_violations=["Agent scores below minimum quality threshold."]
            )

        if not rr_ok:
            reasons.append(f"Risk/Reward ratio {agent2_sig.risk_reward_ratio:.2f} is below required {self.risk_manager.min_risk_reward_ratio:.1f}")
            return ExecutionDecision(
                action="NO_TRADE",
                symbol=symbol,
                direction=agent2_sig.direction,
                confidence=(agent1_sig.score + agent2_sig.score) / 2.0,
                entry_price=agent2_sig.entry_price,
                stop_loss=agent2_sig.invalidation_level,
                take_profit=agent2_sig.take_profit_level,
                risk_reward=agent2_sig.risk_reward_ratio,
                quantity=0.0,
                notional_usd=0.0,
                effective_leverage=0.0,
                risk_approved=False,
                reasons=reasons,
                risk_violations=["R:R ratio below 2.0 requirement."]
            )

        direction = agent2_sig.direction
        entry_price = agent2_sig.entry_price
        stop_loss = agent2_sig.invalidation_level
        take_profit = agent2_sig.take_profit_level
        confidence = (agent1_sig.score * 0.45) + (agent2_sig.score * 0.55)

        # 2. POSITION SIZING: Calculate exact quantity (0.25% equity risk, max 25x leverage)
        current_equity = await self.order_manager.get_equity()
        size_res = self.sizer.calculate(
            account_equity=current_equity,
            entry_price=entry_price,
            stop_loss_price=stop_loss
        )

        if not size_res.allowed:
            reasons.extend(size_res.reasons)
            return ExecutionDecision(
                action="NO_TRADE",
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward=agent2_sig.risk_reward_ratio,
                quantity=0.0,
                notional_usd=0.0,
                effective_leverage=0.0,
                risk_approved=False,
                reasons=reasons,
                risk_violations=size_res.reasons
            )

        # 3. RISK MANAGER: Absolute Authority Review
        active_pos_count = len(self.order_manager.positions)
        risk_val = self.risk_manager.validate_trade_candidate(
            symbol=symbol,
            current_equity=current_equity,
            active_positions_count=active_pos_count,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            spread_bps=spread_bps,
            requested_quantity=size_res.quantity
        )

        if not risk_val.allowed:
            reasons.append("Trade VETOED by independent Risk Manager.")
            logger.warning(f"Trade Vetoed by Risk Manager for {symbol}: {risk_val.violations}")
            return ExecutionDecision(
                action="NO_TRADE",
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                risk_reward=agent2_sig.risk_reward_ratio,
                quantity=size_res.quantity,
                notional_usd=size_res.notional_usd,
                effective_leverage=size_res.effective_leverage,
                risk_approved=False,
                reasons=reasons,
                risk_violations=risk_val.violations
            )

        # 4. ORDER PLACEMENT: Dispatch order with atomic SL and TP
        reasons.extend(risk_val.reasons)
        reasons.extend(agent1_sig.reasons)
        reasons.extend(agent2_sig.reasons)

        order_res = await self.order_manager.execute_trade(
            symbol=symbol,
            product_id=product_id,
            direction=direction,
            quantity=size_res.quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        action = "EXECUTE_BUY" if direction == "LONG" else "EXECUTE_SELL"
        if not order_res.get("success"):
            action = "NO_TRADE"
            reasons.append(f"Execution failed: {order_res.get('reason') or order_res.get('error')}")

        return ExecutionDecision(
            action=action,
            symbol=symbol,
            direction=direction,
            confidence=round(confidence, 1),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=agent2_sig.risk_reward_ratio,
            quantity=size_res.quantity,
            notional_usd=size_res.notional_usd,
            effective_leverage=size_res.effective_leverage,
            risk_approved=True,
            reasons=reasons,
            risk_violations=[]
        )
