from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from data.schemas.market_data import OrderBook, Trade, Candle
from exchange.account import AccountState, Position

class BaseExchangeAdapter(ABC):
    def __init__(self, name: str):
        self.name = name
        self.is_connected = False
        self.on_orderbook_callback: Optional[Callable[[OrderBook], Any]] = None
        self.on_trade_callback: Optional[Callable[[Trade], Any]] = None
        self.on_candle_callback: Optional[Callable[[Candle], Any]] = None

    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def get_account_state(self) -> AccountState:
        pass

    @abstractmethod
    async def submit_market_order(
        self,
        symbol: str,
        side: str,  # "BUY" or "SELL"
        quantity: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        pass
