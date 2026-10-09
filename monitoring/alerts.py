import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("monitoring.alerts")

class AlertDispatcher:
    def __init__(self, telegram_token: Optional[str] = None, discord_webhook: Optional[str] = None):
        self.telegram_token = telegram_token
        self.discord_webhook = discord_webhook
        self.alert_history = []

    async def send_alert(self, title: str, message: str, level: str = "INFO"):
        alert_item = {
            "title": title,
            "message": message,
            "level": level,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.alert_history.append(alert_item)
        
        log_msg = f"[{level}] {title} — {message}"
        if level in ["CRITICAL", "EMERGENCY"]:
            logger.critical(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

    def get_recent_alerts(self, limit: int = 20):
        return self.alert_history[-limit:]
