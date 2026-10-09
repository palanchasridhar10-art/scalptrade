from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from data.schemas.market_data import (
    OrderBook, Trade, Candle, FundingRate, OpenInterest, LiquidationEvent, GEXData
)

class SymbolDataBuffer:
    def __init__(self, symbol: str, max_trades: int = 5000, max_candles: int = 1000):
        self.symbol = symbol
        self.max_trades = max_trades
        self.max_candles = max_candles
        
        self.orderbook: Optional[OrderBook] = None
        self.trades: deque[Trade] = deque(maxlen=max_trades)
        self.candles: Dict[str, deque[Candle]] = {
            "1M": deque(maxlen=max_candles),
            "5M": deque(maxlen=max_candles),
            "15M": deque(maxlen=max_candles),
            "1H": deque(maxlen=max_candles),
            "4H": deque(maxlen=max_candles),
            "1D": deque(maxlen=max_candles)
        }
        self.funding_rate: Optional[FundingRate] = None
        self.open_interest: Optional[OpenInterest] = None
        self.liquidations: deque[LiquidationEvent] = deque(maxlen=500)
        self.gex_data: Optional[GEXData] = None
        
        self.last_update_time: Optional[datetime] = None
        self.cumulative_volume_delta: float = 0.0
        self.cvd_history: deque[dict] = deque(maxlen=max_trades)

    def is_stale(self, timeout_ms: int = 2000) -> bool:
        if self.last_update_time is None:
            return True
        now = datetime.now(timezone.utc)
        diff_ms = (now - self.last_update_time).total_seconds() * 1000.0
        return diff_ms > timeout_ms

    def update_orderbook(self, ob: OrderBook):
        self.orderbook = ob
        self.last_update_time = ob.timestamp

    def add_trade(self, trade: Trade):
        self.trades.append(trade)
        self.last_update_time = trade.timestamp
        
        delta = trade.quantity if trade.is_aggressive_buy else -trade.quantity
        self.cumulative_volume_delta += delta
        self.cvd_history.append({
            "timestamp": trade.timestamp,
            "price": trade.price,
            "delta": delta,
            "cvd": self.cumulative_volume_delta
        })

    def add_candle(self, candle: Candle):
        tf = candle.timeframe.upper()
        if tf in self.candles:
            if self.candles[tf] and self.candles[tf][-1].open_time == candle.open_time:
                self.candles[tf][-1] = candle
            else:
                self.candles[tf].append(candle)
            self.last_update_time = candle.close_time

    def update_funding(self, funding: FundingRate):
        self.funding_rate = funding

    def update_oi(self, oi: OpenInterest):
        self.open_interest = oi

    def add_liquidation(self, liq: LiquidationEvent):
        self.liquidations.append(liq)

    def update_gex(self, gex: GEXData):
        self.gex_data = gex

    def get_candles_df(self, timeframe: str = "1M", limit: int = 100) -> pd.DataFrame:
        tf = timeframe.upper()
        candles = list(self.candles.get(tf, []))[-limit:]
        if not candles:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"])
        
        data = [{
            "open_time": c.open_time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "taker_buy_volume": c.taker_buy_volume
        } for c in candles]
        
        df = pd.DataFrame(data)
        df.set_index("open_time", inplace=False)
        return df

    def get_recent_trades(self, limit: int = 200) -> List[Trade]:
        return list(self.trades)[-limit:]

    def get_cvd_series(self, limit: int = 200) -> pd.DataFrame:
        history = list(self.cvd_history)[-limit:]
        if not history:
            return pd.DataFrame(columns=["timestamp", "price", "delta", "cvd"])
        return pd.DataFrame(history)

class MarketDataManager:
    def __init__(self):
        self.buffers: Dict[str, SymbolDataBuffer] = {}

    def get_or_create(self, symbol: str) -> SymbolDataBuffer:
        if symbol not in self.buffers:
            self.buffers[symbol] = SymbolDataBuffer(symbol)
        return self.buffers[symbol]

    def get_buffer(self, symbol: str) -> Optional[SymbolDataBuffer]:
        return self.buffers.get(symbol)
