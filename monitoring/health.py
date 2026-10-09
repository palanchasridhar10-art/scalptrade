from datetime import datetime, timezone
from typing import Dict, Any
from data.live.buffer import MarketDataManager

class HealthMonitor:
    def __init__(self, data_manager: MarketDataManager):
        self.data_manager = data_manager

    def check_health(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        symbols_status = {}
        all_healthy = True

        for symbol, buffer in self.data_manager.buffers.items():
            stale = buffer.is_stale(timeout_ms=2000)
            if stale:
                all_healthy = False
                
            latency_ms = 0.0
            if buffer.last_update_time:
                latency_ms = (now - buffer.last_update_time).total_seconds() * 1000.0

            symbols_status[symbol] = {
                "stale": stale,
                "latency_ms": round(latency_ms, 1),
                "trades_buffered": len(buffer.trades),
                "candles_1m_count": len(buffer.candles["1M"]),
                "orderbook_ready": buffer.orderbook is not None
            }

        return {
            "status": "HEALTHY" if all_healthy else "DEGRADED",
            "timestamp": now.isoformat(),
            "symbols": symbols_status
        }
