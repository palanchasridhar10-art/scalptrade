import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable
import aiohttp

logger = logging.getLogger("exchange.lead_feed")

class LeadFeedManager:
    """
    Optional Cross-Exchange Lead Feed (Binance / Bybit Public WebSocket, Read-Only, No API keys).
    Used by Agent 1 to:
      1. Cross-check order flow & CVD against the deeper lead market.
      2. Verify basis/price deviation between Delta and global benchmarks.
      3. Detect large whale prints and momentum ignition ahead of Delta's thinner book.
    """
    def __init__(self, lead_exchange: str = "binance", symbol: str = "BTCUSDT"):
        self.lead_exchange = lead_exchange.lower()
        self.symbol = symbol.upper()
        self.ws_url = "wss://fstream.binance.com/ws" if self.lead_exchange == "binance" else "wss://stream.bybit.com/v5/public/linear"
        self.is_connected = False
        self.lead_price: float = 0.0
        self.lead_cvd: float = 0.0
        self.lead_imbalance: float = 0.0
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._ws_loop())
        logger.info(f"Started public lead feed connector ({self.lead_exchange} - {self.symbol})")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        self.is_connected = False

    async def _ws_loop(self):
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    # Binance Futures stream: <symbol>@aggTrade and <symbol>@depth20@100ms
                    stream_name = f"{self.symbol.lower()}@aggTrade/{self.symbol.lower()}@depth20@100ms"
                    url = f"wss://fstream.binance.com/stream?streams={stream_name}"
                    
                    async with session.ws_connect(url, heartbeat=20.0) as ws:
                        self.is_connected = True
                        logger.info(f"Connected to Lead Feed WebSocket: {self.lead_exchange}")
                        
                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                stream = data.get("stream", "")
                                payload = data.get("data", {})
                                
                                if "aggTrade" in stream:
                                    price = float(payload.get("p", 0.0))
                                    qty = float(payload.get("q", 0.0))
                                    is_buyer_maker = payload.get("m", False) # True = Sell, False = Buy
                                    
                                    self.lead_price = price
                                    delta = qty if not is_buyer_maker else -qty
                                    self.lead_cvd += delta
                                    
                                elif "depth" in stream:
                                    bids = payload.get("b", [])
                                    asks = payload.get("a", [])
                                    b_vol = sum(float(b[1]) for b in bids[:10])
                                    a_vol = sum(float(a[1]) for a in asks[:10])
                                    total = b_vol + a_vol
                                    self.lead_imbalance = (b_vol - a_vol) / total if total > 0 else 0.0
                                    
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Lead feed WS connection error: {e}. Reconnecting in 3s...")
                self.is_connected = False
                await asyncio.sleep(3.0)

    def get_lead_metrics(self, delta_price: float) -> Dict[str, Any]:
        basis_bps = 0.0
        if self.lead_price > 0 and delta_price > 0:
            basis_bps = ((delta_price - self.lead_price) / self.lead_price) * 10000.0

        return {
            "lead_exchange": self.lead_exchange,
            "connected": self.is_connected,
            "lead_price": self.lead_price,
            "delta_basis_bps": round(basis_bps, 2),
            "basis_aligned": abs(basis_bps) <= 15.0, # Within 15 bps basis
            "lead_cvd": round(self.lead_cvd, 2),
            "lead_imbalance": round(self.lead_imbalance, 3)
        }
