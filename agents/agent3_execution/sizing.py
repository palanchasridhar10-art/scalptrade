from typing import Dict, Any
from exchange.account import AccountState
from config.settings import RiskLimits

class PositionSizer:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def calculate_size(
        self,
        account: AccountState,
        entry_price: float,
        stop_loss_price: float,
        fractional_kelly_pct: float,
        risk_multiplier: float = 1.0
    ) -> Dict[str, Any]:
        equity = account.equity
        if equity <= 0 or entry_price <= 0:
            return {"quantity": 0.0, "notional_usd": 0.0, "risk_usd": 0.0, "risk_pct": 0.0}

        # Distance to Stop Loss in percentage
        sl_distance_pct = abs(entry_price - stop_loss_price) / entry_price
        if sl_distance_pct < 0.001: # Minimum 0.1% stop loss distance
            sl_distance_pct = 0.001

        # Determine target risk % of account
        # Combine Agent 2 fractional Kelly with hard risk limit and loss multiplier
        raw_risk_pct = min(self.limits.max_risk_per_trade_pct, max(self.limits.min_risk_per_trade_pct, fractional_kelly_pct))
        target_risk_pct = raw_risk_pct * risk_multiplier
        risk_usd = equity * target_risk_pct

        # Position Notional = Risk USD / Stop Loss Distance %
        raw_notional = risk_usd / sl_distance_pct

        # Apply maximum position size and leverage caps
        max_allowed_notional = min(
            self.limits.max_position_size_usd,
            equity * self.limits.max_leverage
        )
        final_notional = min(raw_notional, max_allowed_notional)
        quantity = final_notional / entry_price

        return {
            "quantity": round(quantity, 4),
            "notional_usd": round(final_notional, 2),
            "risk_usd": round(risk_usd, 2),
            "risk_pct": round(target_risk_pct, 4),
            "sl_distance_pct": round(sl_distance_pct, 4),
            "effective_leverage": round(final_notional / equity, 2)
        }
