from typing import Dict, Any, Optional
from dataclasses import dataclass
import math

@dataclass
class PositionSizeResult:
    allowed: bool
    quantity: float
    notional_usd: float
    effective_leverage: float
    risk_amount_usd: float
    reasons: list[str]

class PositionSizer:
    """
    Calculates dynamic position sizing based strictly on account equity risk.
    Enforces 0.25% equity risk per trade and maximum 25x leverage constraint.
    """
    def __init__(
        self,
        risk_per_trade_pct: float = 0.0025,  # 0.25% of account equity
        max_leverage: float = 25.0,
        min_contract_size: float = 0.001,
        contract_step: float = 0.001
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_leverage = max_leverage
        self.min_contract_size = min_contract_size
        self.contract_step = contract_step

    def calculate(
        self,
        account_equity: float,
        entry_price: float,
        stop_loss_price: float
    ) -> PositionSizeResult:
        if account_equity <= 0:
            return PositionSizeResult(False, 0.0, 0.0, 0.0, 0.0, ["Account equity is zero or negative."])

        risk_dist = abs(entry_price - stop_loss_price)
        if risk_dist <= 0:
            return PositionSizeResult(False, 0.0, 0.0, 0.0, 0.0, ["Invalid stop loss: distance to entry is zero."])

        # 1. Total dollar risk allocated (0.25% of account equity)
        risk_amount_usd = account_equity * self.risk_per_trade_pct

        # 2. Raw quantity sized so loss at Stop Loss equals exactly risk_amount_usd
        raw_quantity = risk_amount_usd / risk_dist

        # 3. Maximum notional cap based on 25x leverage
        max_notional = account_equity * self.max_leverage
        raw_notional = raw_quantity * entry_price

        reasons = []
        if raw_notional > max_notional:
            raw_quantity = max_notional / entry_price
            raw_notional = max_notional
            reasons.append(f"Position size capped by 25x maximum leverage limit (${max_notional:.2f}).")

        # 4. Round to contract precision
        steps = math.floor(raw_quantity / self.contract_step)
        final_quantity = round(steps * self.contract_step, 4)

        if final_quantity < self.min_contract_size:
            return PositionSizeResult(
                allowed=False,
                quantity=0.0,
                notional_usd=0.0,
                effective_leverage=0.0,
                risk_amount_usd=risk_amount_usd,
                reasons=[f"Calculated size ({final_quantity}) below minimum allowable contract ({self.min_contract_size})."]
            )

        final_notional = round(final_quantity * entry_price, 2)
        effective_leverage = round(final_notional / account_equity, 2)

        return PositionSizeResult(
            allowed=True,
            quantity=final_quantity,
            notional_usd=final_notional,
            effective_leverage=effective_leverage,
            risk_amount_usd=round(risk_amount_usd, 2),
            reasons=reasons
        )
