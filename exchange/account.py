from datetime import datetime, timezone
from typing import Dict, Optional, List
from pydantic import BaseModel, Field

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class Position(BaseModel):
    symbol: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    leverage: float = 1.0
    mark_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = 0.0
    entry_time: datetime = Field(default_factory=current_utc)

    def update_mark_price(self, mark: float):
        self.mark_price = mark
        if self.direction == "LONG":
            self.unrealized_pnl = (mark - self.entry_price) * self.quantity
            self.unrealized_pnl_pct = (mark - self.entry_price) / self.entry_price
            if mark > self.highest_price or self.highest_price == 0.0:
                self.highest_price = mark
        else:
            self.unrealized_pnl = (self.entry_price - mark) * self.quantity
            self.unrealized_pnl_pct = (self.entry_price - mark) / self.entry_price
            if mark < self.lowest_price or self.lowest_price == 0.0:
                self.lowest_price = mark

class ClosedTradeInfo(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    commission: float
    slippage: float = 0.0
    realized_r: float = 0.0
    reason: str
    entry_time: datetime
    exit_time: datetime

class AccountState(BaseModel):
    currency: str = "USDT"
    initial_balance: float = 10000.0
    balance: float = 10000.0
    realized_pnl: float = 0.0
    total_commission_paid: float = 0.0
    high_watermark: float = 10000.0
    daily_starting_equity: float = 10000.0
    weekly_starting_equity: float = 10000.0
    daily_realized_pnl: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    positions: Dict[str, Position] = Field(default_factory=dict)
    closed_trades: List[ClosedTradeInfo] = Field(default_factory=list)
    
    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def equity(self) -> float:
        eq = self.balance + self.unrealized_pnl
        if eq > self.high_watermark:
            object.__setattr__(self, 'high_watermark', eq)
        return eq

    @property
    def daily_pnl(self) -> float:
        return self.equity - self.daily_starting_equity

    @property
    def daily_pnl_pct(self) -> float:
        return (self.daily_pnl / self.daily_starting_equity) if self.daily_starting_equity > 0 else 0.0

    @property
    def weekly_pnl_pct(self) -> float:
        return ((self.equity - self.weekly_starting_equity) / self.weekly_starting_equity) if self.weekly_starting_equity > 0 else 0.0

    @property
    def total_drawdown_pct(self) -> float:
        return max(0.0, (self.high_watermark - self.equity) / self.high_watermark) if self.high_watermark > 0 else 0.0

    def add_position(self, pos: Position):
        self.positions[pos.symbol] = pos

    def remove_position(self, symbol: str) -> Optional[Position]:
        return self.positions.pop(symbol, None)

    def record_closed_trade(self, info: ClosedTradeInfo):
        self.balance += info.net_pnl
        self.realized_pnl += info.net_pnl
        self.daily_realized_pnl += info.net_pnl
        self.total_commission_paid += info.commission
        self.closed_trades.append(info)
        
        if self.balance > self.high_watermark:
            self.high_watermark = self.balance

        if info.net_pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif info.net_pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
