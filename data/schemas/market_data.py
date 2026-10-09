from datetime import datetime, timezone
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class OrderBookLevel(BaseModel):
    price: float
    amount: float

class OrderBook(BaseModel):
    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: datetime = Field(default_factory=current_utc)
    
    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0
        
    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0
        
    @property
    def spread(self) -> float:
        return max(0.0, self.best_ask - self.best_bid)
        
    @property
    def spread_bps(self) -> float:
        mid = (self.best_bid + self.best_ask) / 2.0
        return (self.spread / mid * 10000.0) if mid > 0 else 0.0

class Trade(BaseModel):
    symbol: str
    trade_id: str
    price: float
    quantity: float
    is_buyer_maker: bool  # True = seller aggressed (Sell), False = buyer aggressed (Buy)
    timestamp: datetime = Field(default_factory=current_utc)

    @property
    def is_aggressive_buy(self) -> bool:
        return not self.is_buyer_maker
        
    @property
    def is_aggressive_sell(self) -> bool:
        return self.is_buyer_maker

class Candle(BaseModel):
    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades_count: int = 0
    taker_buy_volume: float = 0.0
    is_closed: bool = True

class FundingRate(BaseModel):
    symbol: str
    funding_rate: float
    mark_price: float
    next_funding_time: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=current_utc)

class OpenInterest(BaseModel):
    symbol: str
    open_interest: float
    timestamp: datetime = Field(default_factory=current_utc)

class LiquidationEvent(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    price: float
    quantity: float
    timestamp: datetime = Field(default_factory=current_utc)

class GEXData(BaseModel):
    symbol: str
    spot_price: float
    total_gex: float
    call_gex: float
    put_gex: float
    call_oi: float
    put_oi: float
    gamma_flip_strike: Optional[float] = None
    dealer_regime: Literal["LONG_GAMMA", "SHORT_GAMMA", "NEUTRAL"] = "NEUTRAL"
    status: Literal["VERIFIED", "ESTIMATED", "UNAVAILABLE"] = "UNAVAILABLE"
    timestamp: datetime = Field(default_factory=current_utc)
