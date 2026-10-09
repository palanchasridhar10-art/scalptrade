import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from exchange.adapter import BaseExchangeAdapter
from exchange.account import AccountState, Position, ClosedTradeInfo
from data.schemas.market_data import OrderBook, Trade, Candle

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class PaperExchange(BaseExchangeAdapter):
    def __init__(
        self,
        initial_balance: float = 10000.0,
        taker_fee_bps: float = 4.0,  # 0.04% taker fee
        maker_fee_bps: float = 2.0,  # 0.02% maker fee
        simulated_latency_ms: float = 25.0
    ):
        super().__init__("paper_simulator")
        self.account = AccountState(
            currency="USDT",
            initial_balance=initial_balance,
            balance=initial_balance,
            daily_starting_equity=initial_balance,
            weekly_starting_equity=initial_balance
        )
        self.taker_fee_pct = taker_fee_bps / 10000.0
        self.maker_fee_pct = maker_fee_bps / 10000.0
        self.simulated_latency_ms = simulated_latency_ms
        self.last_prices: Dict[str, float] = {}
        self.is_connected = True

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    def update_price(self, symbol: str, price: float):
        self.last_prices[symbol] = price
        if symbol in self.account.positions:
            self.account.positions[symbol].update_mark_price(price)

    async def get_account_state(self) -> AccountState:
        return self.account

    async def submit_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        if self.simulated_latency_ms > 0:
            await asyncio.sleep(self.simulated_latency_ms / 1000.0)

        current_price = self.last_prices.get(symbol, 67000.0)
        now = timestamp or current_utc()
        
        slippage_pct = 0.00015
        fill_price = current_price * (1.0 + slippage_pct) if side == "BUY" else current_price * (1.0 - slippage_pct)
        
        notional = fill_price * quantity
        commission = notional * self.taker_fee_pct
        
        direction = "LONG" if side == "BUY" else "SHORT"
        
        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=fill_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            mark_price=fill_price,
            entry_time=now
        )
        
        self.account.add_position(position)
        self.account.balance -= commission
        self.account.total_commission_paid += commission
        
        order_id = f"paper_ord_{uuid.uuid4().hex[:8]}"
        return {
            "order_id": order_id,
            "symbol": symbol,
            "status": "FILLED",
            "side": side,
            "fill_price": fill_price,
            "quantity": quantity,
            "notional": notional,
            "commission": commission,
            "timestamp": now.isoformat()
        }

    async def close_position(self, symbol: str, reason: str = "MANUAL", timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        if symbol not in self.account.positions:
            return {"status": "NO_POSITION", "symbol": symbol}
            
        pos = self.account.remove_position(symbol)
        current_price = self.last_prices.get(symbol, pos.mark_price)
        now = timestamp or current_utc()
        
        slippage_pct = 0.00015
        exit_price = current_price * (1.0 - slippage_pct) if pos.direction == "LONG" else current_price * (1.0 + slippage_pct)
        
        if pos.direction == "LONG":
            gross_pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            gross_pnl = (pos.entry_price - exit_price) * pos.quantity
            
        notional = exit_price * pos.quantity
        commission = notional * self.taker_fee_pct
        slippage_usd = notional * slippage_pct
        
        risk_dist = abs(pos.entry_price - pos.stop_loss)
        realized_r = (gross_pnl / (risk_dist * pos.quantity)) if risk_dist > 0 else 0.0

        closed_info = ClosedTradeInfo(
            symbol=symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit_2,
            quantity=pos.quantity,
            gross_pnl=gross_pnl,
            net_pnl=gross_pnl - commission,
            commission=commission,
            slippage=slippage_usd,
            realized_r=realized_r,
            reason=reason,
            entry_time=pos.entry_time,
            exit_time=now
        )
        
        self.account.record_closed_trade(closed_info)
        
        return {
            "symbol": symbol,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "exit_price": exit_price,
            "quantity": pos.quantity,
            "gross_pnl": gross_pnl,
            "net_pnl": gross_pnl - commission,
            "commission": commission,
            "realized_r": realized_r,
            "reason": reason,
            "timestamp": now.isoformat(),
            "closed_info": closed_info
        }

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        return True
