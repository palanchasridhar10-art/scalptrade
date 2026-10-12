from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import time

@dataclass
class RiskValidationResult:
    allowed: bool
    violations: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

class RiskManager:
    """
    Independent Risk Manager with Absolute Veto Authority.
    Possesses full authority to reject ANY trade regardless of Agent recommendations.
    Strictly enforces Section 4 risk parameters:
      - 0.25% risk per trade
      - 1.0% daily loss limit
      - Max 1 simultaneous position
      - Max 25x leverage
      - Mandatory Stop-Loss and Take-Profit
      - Emergency circuit breaker upon repeated API errors
    """
    def __init__(
        self,
        risk_per_trade_pct: float = 0.0025,
        daily_loss_limit_pct: float = 0.01,
        max_simultaneous_positions: int = 1,
        max_leverage: float = 25.0,
        require_stop_loss: bool = True,
        require_take_profit: bool = True,
        max_consecutive_api_errors: int = 3,
        min_risk_reward_ratio: float = 2.0,
        max_spread_bps: float = 6.0
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.max_simultaneous_positions = max_simultaneous_positions
        self.max_leverage = max_leverage
        self.require_stop_loss = require_stop_loss
        self.require_take_profit = require_take_profit
        self.max_consecutive_api_errors = max_consecutive_api_errors
        self.min_risk_reward_ratio = min_risk_reward_ratio
        self.max_spread_bps = max_spread_bps

        # Internal state tracking
        self.daily_starting_equity: float = 10000.0
        self.realized_daily_pnl: float = 0.0
        self.consecutive_api_errors: int = 0
        self.circuit_breaker_active: bool = False
        self.kill_switch_active: bool = False
        self.last_reset_day: int = time.gmtime().tm_yday

    def record_api_error(self):
        self.consecutive_api_errors += 1
        if self.consecutive_api_errors >= self.max_consecutive_api_errors:
            self.circuit_breaker_active = True

    def reset_api_errors(self):
        self.consecutive_api_errors = 0

    def trigger_kill_switch(self, reason: str = "MANUAL_TRIGGER"):
        self.kill_switch_active = True

    def reset_daily_accounting(self, current_equity: float):
        self.daily_starting_equity = current_equity
        self.realized_daily_pnl = 0.0
        self.last_reset_day = time.gmtime().tm_yday
        self.circuit_breaker_active = False

    def validate_trade_candidate(
        self,
        symbol: str,
        current_equity: float,
        active_positions_count: int,
        entry_price: float,
        stop_loss_price: Optional[float],
        take_profit_price: Optional[float],
        spread_bps: float,
        requested_quantity: float = 0.0
    ) -> RiskValidationResult:
        violations: List[str] = []
        reasons: List[str] = []

        # 0. Check day rollover
        today = time.gmtime().tm_yday
        if today != self.last_reset_day:
            self.reset_daily_accounting(current_equity)

        # 1. Manual or Emergency Kill Switch Check
        if self.kill_switch_active:
            violations.append("EMERGENCY: Kill Switch is active. All new trade executions are blocked.")
            return RiskValidationResult(allowed=False, violations=violations)

        # 2. Circuit Breaker Check (Repeated API Errors)
        if self.circuit_breaker_active or self.consecutive_api_errors >= self.max_consecutive_api_errors:
            violations.append(f"CIRCUIT BREAKER: {self.consecutive_api_errors} consecutive API errors detected. Trading halted.")
            return RiskValidationResult(allowed=False, violations=violations)

        # 3. Maximum Simultaneous Positions Check
        if active_positions_count >= self.max_simultaneous_positions:
            violations.append(f"POSITION LIMIT: Active positions ({active_positions_count}) at max limit ({self.max_simultaneous_positions}).")

        # 4. Mandatory Stop-Loss Check
        if self.require_stop_loss and (stop_loss_price is None or stop_loss_price <= 0):
            violations.append("RISK RULE: Stop-Loss is strictly REQUIRED on Delta Futures contracts.")

        # 5. Mandatory Take-Profit Check
        if self.require_take_profit and (take_profit_price is None or take_profit_price <= 0):
            violations.append("RISK RULE: Take-Profit is strictly REQUIRED on Delta Futures contracts.")

        # 6. Risk-to-Reward Ratio Check (min 2.0 R:R)
        if stop_loss_price and take_profit_price and entry_price > 0:
            risk_dist = abs(entry_price - stop_loss_price)
            reward_dist = abs(take_profit_price - entry_price)
            rr = (reward_dist / risk_dist) if risk_dist > 0 else 0.0
            if rr < self.min_risk_reward_ratio:
                violations.append(f"RISK/REWARD VETO: Setup R:R {rr:.2f} is below mandatory {self.min_risk_reward_ratio:.1f} R:R threshold.")
            else:
                reasons.append(f"Valid R:R ratio {rr:.2f} >= {self.min_risk_reward_ratio:.1f}")

        # 7. Daily Loss Limit Check (1.0% limit)
        daily_loss_limit_usd = self.daily_starting_equity * self.daily_loss_limit_pct
        current_daily_pnl = self.realized_daily_pnl + (current_equity - self.daily_starting_equity)
        if current_daily_pnl <= -daily_loss_limit_usd:
            violations.append(f"DAILY LOSS LIMIT BREACH: Current daily loss (${abs(current_daily_pnl):.2f}) exceeds 1% limit (${daily_loss_limit_usd:.2f}).")

        # 8. Maximum Leverage Constraint Check
        if requested_quantity > 0 and current_equity > 0:
            notional = requested_quantity * entry_price
            effective_leverage = notional / current_equity
            if effective_leverage > self.max_leverage:
                violations.append(f"LEVERAGE LIMIT BREACH: Effective leverage {effective_leverage:.1f}x exceeds max limit {self.max_leverage}x.")

        # 9. Excessive Market Spread Check
        if spread_bps > self.max_spread_bps:
            violations.append(f"EXCESSIVE SPREAD: Market spread {spread_bps:.2f} bps exceeds risk ceiling {self.max_spread_bps:.2f} bps.")

        is_allowed = len(violations) == 0
        if is_allowed:
            reasons.append("All Section 4 Risk Management limits satisfied.")

        return RiskValidationResult(
            allowed=is_allowed,
            violations=violations,
            reasons=reasons
        )
