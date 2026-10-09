import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from exchange.adapter import BaseExchangeAdapter

logger = logging.getLogger("agent3.kill_switch")

class KillSwitch:
    """Multi-tier Emergency Kill Switch"""
    def __init__(self, exchange: BaseExchangeAdapter):
        self.exchange = exchange
        self.is_active: bool = False
        self.activation_reason: Optional[str] = None
        self.activation_time: Optional[datetime] = None

    async def trigger(self, reason: str = "MANUAL_EMERGENCY") -> Dict[str, Any]:
        """
        Tier 1: Lock trade generation
        Tier 2: Cancel all open orders
        Tier 3: Emergency close all positions
        """
        self.is_active = True
        self.activation_reason = reason
        self.activation_time = datetime.now(timezone.utc)
        logger.critical(f"KILL SWITCH TRIGGERED: {reason}")

        # Cancel orders
        await self.exchange.cancel_all_orders()

        # Close all active positions
        account = await self.exchange.get_account_state()
        closed_positions = []
        for symbol in list(account.positions.keys()):
            res = await self.exchange.close_position(symbol, reason=f"KILL_SWITCH: {reason}")
            closed_positions.append(res)

        return {
            "kill_switch_active": True,
            "reason": reason,
            "timestamp": self.activation_time.isoformat(),
            "closed_positions_count": len(closed_positions),
            "details": closed_positions
        }

    def reset(self):
        self.is_active = False
        self.activation_reason = None
        self.activation_time = None
        logger.info("Kill switch reset. System restored to NORMAL standby.")
