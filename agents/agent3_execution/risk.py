from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from exchange.account import AccountState
from config.settings import RiskLimits, CooldownConfig, EmergencyConfig

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class RiskEngine:
    """The Risk Engine has absolute authority to veto any trade."""
    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        cooldown: Optional[CooldownConfig] = None,
        emergency: Optional[EmergencyConfig] = None
    ):
        self.limits = limits or RiskLimits()
        self.cooldown = cooldown or CooldownConfig()
        self.emergency = emergency or EmergencyConfig()
        self.last_trade_time: Optional[datetime] = None
        self.kill_switch_active: bool = False

    def validate_candidate(
        self,
        symbol: str,
        direction: str,
        account: AccountState,
        spread_bps: float,
        data_is_fresh: bool = True,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        violations: List[str] = []
        now = current_time or current_utc()

        # 1. Kill Switch Check
        if self.kill_switch_active:
            violations.append("EMERGENCY: Kill switch is actively locking all trade generation.")
            return {"allowed": False, "violations": violations}

        # 2. Data Freshness Check
        if not data_is_fresh:
            violations.append(f"STALE FEED: Market data latency exceeds SLA limit ({self.emergency.stale_data_timeout_ms}ms).")

        # 3. Spread Check
        if spread_bps > self.limits.max_spread_bps:
            violations.append(f"HIGH SPREAD: Current spread {spread_bps:.2f} bps exceeds limit {self.limits.max_spread_bps:.2f} bps.")

        # 4. Daily Loss Limit Check
        daily_loss_pct = -account.daily_pnl_pct
        if daily_loss_pct >= self.limits.max_daily_loss_pct:
            violations.append(f"DAILY LOSS LIMIT REACHED: Current loss {daily_loss_pct:.2%} exceeds limit {self.limits.max_daily_loss_pct:.2%}.")

        # 5. Weekly Loss Limit Check
        weekly_loss_pct = -account.weekly_pnl_pct
        if weekly_loss_pct >= self.limits.max_weekly_loss_pct:
            violations.append(f"WEEKLY LOSS LIMIT REACHED: Current loss {weekly_loss_pct:.2%} exceeds limit {self.limits.max_weekly_loss_pct:.2%}.")

        # 6. Max Open Positions Check
        if len(account.positions) >= self.limits.max_open_positions:
            violations.append(f"POSITION LIMIT: Open positions ({len(account.positions)}) at max limit ({self.limits.max_open_positions}).")

        # 7. Existing Position for Symbol
        if symbol in account.positions:
            violations.append(f"EXISTING POSITION: Symbol {symbol} already has an active position.")

        # 8. Consecutive Losses Cooldown
        if account.consecutive_losses >= 4 and self.cooldown.four_consecutive_losses_kill_switch:
            violations.append(f"COOLDOWN HALT: 4 consecutive losses triggered automated circuit breaker.")

        # 9. Normal Trade Cooldown (time between trades)
        if self.last_trade_time is not None:
            elapsed = (now - self.last_trade_time).total_seconds()
            if elapsed < self.cooldown.normal_trade_cooldown_sec:
                violations.append(f"TRADE COOLDOWN: Must wait {int(self.cooldown.normal_trade_cooldown_sec - elapsed)}s before next execution.")

        allowed = len(violations) == 0
        return {
            "allowed": allowed,
            "violations": violations,
            "risk_multiplier": self._calculate_risk_multiplier(account)
        }

    def _calculate_risk_multiplier(self, account: AccountState) -> float:
        if account.consecutive_losses == 2:
            return self.cooldown.two_consecutive_losses_risk_reduction
        elif account.consecutive_losses >= 3:
            return 0.25
        return 1.0

    def record_execution(self, timestamp: Optional[datetime] = None):
        self.last_trade_time = timestamp or current_utc()
