import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Callable
import pandas as pd
import aiohttp

logger = logging.getLogger("price_feed")

class AutomaticPriceFeed:
    """
    Automatic Real-Time Market Price & Candle Streamer.
    Continuously fetches live market prices, L2 order books, and OHLCV candles
    from Delta Exchange India live endpoints without requiring user intervention.
    """
    DELTA_LIVE_API = "https://api.india.delta.exchange"
    DELTA_DEMO_API = "https://cdn-ind.testnet.deltaex.org"

    def __init__(
        self,
        symbol: str = "BTCUSD",
        is_demo: bool = False,
        poll_interval: float = 1.5
    ):
        self.symbol = symbol
        self.is_demo = is_demo
        self.poll_interval = poll_interval
        self.base_url = self.DELTA_DEMO_API if is_demo else self.DELTA_LIVE_API
        
        # Real-time state
        self.current_price: float = 0.0
        self.mark_price: float = 0.0
        self.spot_price: float = 0.0
        self.spread_bps: float = 0.8
        self.candles_df: pd.DataFrame = pd.DataFrame()
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Callback for when live price or candles update
        self.on_tick: Optional[Callable[[Dict[str, Any]], None]] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0))
        return self._session

    async def fetch_live_ticker(self) -> Dict[str, Any]:
        """Fetch real-time mark price and 24h stats."""
        session = await self.get_session()
        # Fallback to live API if demo endpoint has zero volume
        urls = [f"{self.base_url}/v2/tickers/{self.symbol}", f"{self.DELTA_LIVE_API}/v2/tickers/{self.symbol}"]
        for url in urls:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("result", {})
                        mark = float(result.get("mark_price", 0.0))
                        spot = float(result.get("spot_price", mark))
                        close = float(result.get("close", mark))
                        if mark > 0:
                            self.mark_price = mark
                            self.spot_price = spot
                            self.current_price = spot if spot > 0 else mark
                            return result
            except Exception as e:
                logger.debug(f"Ticker fetch retry on {url}: {e}")
        return {}

    async def fetch_live_orderbook(self) -> Dict[str, Any]:
        """Fetch real Level 2 resting limit orders."""
        session = await self.get_session()
        urls = [f"{self.base_url}/v2/l2orderbook/{self.symbol}", f"{self.DELTA_LIVE_API}/v2/l2orderbook/{self.symbol}"]
        for url in urls:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("result", {})
                        if result.get("buy") or result.get("sell"):
                            return result
            except Exception as e:
                logger.debug(f"Orderbook fetch retry: {e}")
        return {}

    async def fetch_live_candles(self, resolution: str = "1m", limit: int = 60) -> pd.DataFrame:
        """Fetch real OHLCV historical candlestick bars directly from Delta Exchange."""
        session = await self.get_session()
        now = int(time.time())
        start = now - (limit * 60 * 2)
        urls = [f"{self.base_url}/v2/history/candles", f"{self.DELTA_LIVE_API}/v2/history/candles"]

        for url in urls:
            try:
                params = {"symbol": self.symbol, "resolution": resolution, "start": start, "end": now}
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw_candles = data.get("result", [])
                        if raw_candles:
                            # Format into DataFrame
                            df = pd.DataFrame(raw_candles)
                            # Columns: time, open, high, low, close, volume
                            df = df.rename(columns={"time": "open_time"})
                            df["close"] = df["close"].astype(float)
                            df["open"] = df["open"].astype(float)
                            df["high"] = df["high"].astype(float)
                            df["low"] = df["low"].astype(float)
                            df["volume"] = df["volume"].astype(float)
                            # Sort chronologically
                            df = df.sort_values("open_time").reset_index(drop=True)
                            self.candles_df = df
                            if not df.empty:
                                self.current_price = float(df["close"].iloc[-1])
                            return df
            except Exception as e:
                logger.debug(f"Candles fetch retry: {e}")
        return self.candles_df

    async def start(self):
        """Start automatic live background price polling."""
        self.is_running = True
        logger.info(f"Automatic Live Price Feed initialized for {self.symbol}...")
        # Initial bootstrap
        await self.fetch_live_ticker()
        await self.fetch_live_candles(limit=60)
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _poll_loop(self):
        while self.is_running:
            try:
                # 1. Update live ticker
                await self.fetch_live_ticker()

                # 2. Periodically update candles (every 5 cycles)
                await self.fetch_live_candles(limit=60)

                # 3. Fire tick callback
                if self.on_tick:
                    self.on_tick({
                        "symbol": self.symbol,
                        "price": self.current_price,
                        "mark_price": self.mark_price,
                        "spot_price": self.spot_price,
                        "timestamp": time.time()
                    })

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in automatic price feed loop: {e}")

            await asyncio.sleep(self.poll_interval)
