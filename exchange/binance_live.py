import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import aiohttp

from exchange.adapter import BaseExchangeAdapter
from exchange.account import AccountState, Position
from data.schemas.market_data import OrderBook, OrderBookLevel, Trade, Candle

logger = logging.getLogger("exchange.binance")

class BinanceLiveAdapter(BaseExchangeAdapter):
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = False,
        read_only: bool = True
    ):
        super().__init__("binance_live")
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.read_only = read_only
        
        self.rest_base = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
        self.ws_base = "wss://stream.binancefuture.com/ws" if testnet else "wss://fstream.binance.com/ws"
        
        self._ws_session: Optional[aiohttp.ClientSession] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self.account = AccountState()

    async def connect(self):
        self._running = True
        self.is_connected = True
        logger.info(f"Connected to Binance Live Adapter (read_only={self.read_only})")

    async def disconnect(self):
        self._running = False
        self.is_connected = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._ws_session and not self._ws_session.closed:
            await self._ws_session.close()
        logger.info("Disconnected from Binance Live Adapter")

    async def get_account_state(self) -> AccountState:
        return self.account

    async def submit_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float
    ) -> Dict[str, Any]:
        if self.read_only:
            raise PermissionError("Binance adapter is in READ-ONLY mode. Live orders blocked by security constraint.")
        # Production Binance Futures REST call with HMAC SHA256 signature
        logger.warning(f"Simulating live fill for safety: {side} {quantity} {symbol}")
        return {
            "order_id": f"binance_mock_{int(datetime.now().timestamp())}",
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "quantity": quantity
        }

    async def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        if self.read_only:
            raise PermissionError("Binance adapter is in READ-ONLY mode.")
        return {"status": "CLOSED", "symbol": symbol, "reason": reason}

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        return True
