from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from exchange.account import Position, AccountState
from data.schemas.signals import Agent1Signal, Agent2Signal

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class PositionLifecycleManager:
    def __init__(
        self,
        trailing_activation_r: float = 1.2,
        trailing_distance_r: float = 0.5,
        max_holding_time_minutes: int = 120
    ):
        self.trailing_activation_r = trailing_activation_r
        self.trailing_distance_r = trailing_distance_r
        self.max_holding_time_minutes = max_holding_time_minutes

    def check_position(
        self,
        position: Position,
        current_price: float,
        agent1: Optional[Agent1Signal] = None,
        agent2: Optional[Agent2Signal] = None,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Monitors active positions and identifies exit triggers.
        Returns whether to exit, exit reason, and trailing SL updates.
        """
        position.update_mark_price(current_price)
        risk_dist = abs(position.entry_price - position.stop_loss)
        if risk_dist <= 0:
            risk_dist = position.entry_price * 0.005

        now = current_time or current_utc()

        # 1. Stop Loss Hit
        if position.direction == "LONG" and current_price <= position.stop_loss:
            return {"should_exit": True, "reason": "STOP_LOSS_HIT", "exit_price": current_price}
        elif position.direction == "SHORT" and current_price >= position.stop_loss:
            return {"should_exit": True, "reason": "STOP_LOSS_HIT", "exit_price": current_price}

        # 2. Take Profit 2 (Final Target) Hit
        if position.direction == "LONG" and current_price >= position.take_profit_2:
            return {"should_exit": True, "reason": "TAKE_PROFIT_2_REACHED", "exit_price": current_price}
        elif position.direction == "SHORT" and current_price <= position.take_profit_2:
            return {"should_exit": True, "reason": "TAKE_PROFIT_2_REACHED", "exit_price": current_price}

        # 3. Trailing Stop Management
        if position.direction == "LONG":
            r_multiple = (position.highest_price - position.entry_price) / risk_dist
            if r_multiple >= self.trailing_activation_r:
                new_sl = position.highest_price - (risk_dist * self.trailing_distance_r)
                if new_sl > position.stop_loss:
                    position.stop_loss = round(new_sl, 2)
        else:
            r_multiple = (position.entry_price - position.lowest_price) / risk_dist
            if r_multiple >= self.trailing_activation_r:
                new_sl = position.lowest_price + (risk_dist * self.trailing_distance_r)
                if new_sl < position.stop_loss:
                    position.stop_loss = round(new_sl, 2)

        # 4. Structure Failure / Strong Opposite Consensus Exit
        if agent1 and agent2:
            if position.direction == "LONG" and agent1.direction == "SHORT" and agent2.direction == "SHORT" and agent1.score >= 85 and agent2.score >= 85:
                return {"should_exit": True, "reason": "OPPOSING_STRUCTURE_BREAK", "exit_price": current_price}
            elif position.direction == "SHORT" and agent1.direction == "LONG" and agent2.direction == "LONG" and agent1.score >= 85 and agent2.score >= 85:
                return {"should_exit": True, "reason": "OPPOSING_STRUCTURE_BREAK", "exit_price": current_price}

        # 5. Time Stop (Scalp position held too long without resolving)
        holding_mins = (now - position.entry_time).total_seconds() / 60.0
        if holding_mins >= self.max_holding_time_minutes:
            return {"should_exit": True, "reason": "TIME_DECAY_STOP", "exit_price": current_price}

        return {"should_exit": False, "reason": "HOLD", "current_sl": position.stop_loss}
