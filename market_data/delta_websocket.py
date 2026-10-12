import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Callable
import websockets

logger = logging.getLogger("delta_websocket")

class DeltaWebSocketManager:
    """
    Async WebSocket Manager for Delta Exchange India feeds.
    Connects to L2 Orderbook, Trades, Candlestick, and Ticker channels with auto-reconnection.
    """
    DEMO_WS_URL = "wss://socket-ind.testnet.deltaex.org"
    LIVE_WS_URL = "wss://socket.india.delta.exchange"

    def __init__(
        self,
        symbol: str = "BTCUSD",
        is_demo: bool = True,
        ws_url: Optional[str] = None
    ):
        self.symbol = symbol
        self.is_demo = is_demo
        self.ws_url = ws_url or (self.DEMO_WS_URL if is_demo else self.LIVE_WS_URL)
        
        self.is_running: bool = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._task: Optional[asyncio.Task] = None
        
        # Event callbacks
        self.on_orderbook_update: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_trade_update: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_candle_update: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_ticker_update: Optional[Callable[[Dict[str, Any]], None]] = None

    def get_subscription_payload(self) -> Dict[str, Any]:
        return {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {"name": "l2_orderbook", "symbols": [self.symbol]},
                    {"name": "all_trades", "symbols": [self.symbol]},
                    {"name": "candlestick_1m", "symbols": [self.symbol]},
                    {"name": "v2/ticker", "symbols": [self.symbol]}
                ]
            }
        }

    async def start(self):
        self.is_running = True
        self._task = asyncio.create_task(self._connection_loop())
        logger.info(f"Delta WebSocket worker started for {self.symbol} on {self.ws_url}")

    async def stop(self):
        self.is_running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
        logger.info("Delta WebSocket worker stopped")

    async def _connection_loop(self):
        while self.is_running:
            try:
                logger.info(f"Connecting to Delta Exchange WebSocket: {self.ws_url} ...")
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as ws:
                    self._ws = ws
                    # Send subscription payload
                    sub_msg = json.dumps(self.get_subscription_payload())
                    await ws.send(sub_msg)
                    logger.info(f"Subscribed to Delta Exchange channels for {self.symbol}")

                    while self.is_running:
                        msg_text = await ws.recv()
                        try:
                            msg_data = json.loads(msg_text)
                            self._handle_message(msg_data)
                        except json.JSONDecodeError:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Delta WebSocket connection lost ({e}). Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    def _handle_message(self, data: Dict[str, Any]):
        channel = data.get("type", data.get("channel", ""))

        # 1. L2 Order Book snapshot or delta
        if "l2_orderbook" in channel or channel == "snapshot" or "bids" in data:
            if self.on_orderbook_update:
                self.on_orderbook_update(data)

        # 2. Public Trades
        elif "all_trades" in channel or "trades" in channel:
            if self.on_trade_update:
                self.on_trade_update(data)

        # 3. Candlestick
        elif "candlestick" in channel or "candle" in channel:
            if self.on_candle_update:
                self.on_candle_update(data)

        # 4. Ticker
        elif "ticker" in channel or "mark_price" in data:
            if self.on_ticker_update:
                self.on_ticker_update(data)
