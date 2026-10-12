import asyncio
import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from exchange.delta_client import DeltaExchangeClient
from risk.risk_manager import RiskManager

logger = logging.getLogger("order_manager")

@dataclass
class ManagedPosition:
    position_id: str
    symbol: str
    product_id: int
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float
    mark_price: float
    highest_price: float
    lowest_price: float
    entry_time: float
    unrealized_pnl: float = 0.0
    trailing_activated: bool = False

    def update_mark(self, mark: float):
        self.mark_price = mark
        if self.direction == "LONG":
            self.unrealized_pnl = (mark - self.entry_price) * self.quantity
            if mark > self.highest_price or self.highest_price == 0.0:
                self.highest_price = mark
        else:
            self.unrealized_pnl = (self.entry_price - mark) * self.quantity
            if mark < self.lowest_price or self.lowest_price == 0.0:
                self.lowest_price = mark

class OrderManager:
    """
    Manages order execution, duplicate-order prevention, and position lifecycle monitoring.
    Supports both direct Delta Exchange live/demo API execution and simulated paper fills.
    """
    def __init__(
        self,
        client: DeltaExchangeClient,
        risk_manager: RiskManager,
        simulated: bool = False,
        initial_balance: float = 10000.0
    ):
        self.client = client
        self.risk_manager = risk_manager
        self.simulated = simulated
        
        # Local simulated account state
        self.balance: float = initial_balance
        self.equity: float = initial_balance
        self.positions: Dict[str, ManagedPosition] = {}
        self.closed_trades: List[Dict[str, Any]] = []

        # Duplicate order prevention: orders in-flight and client order ID deduplication
        self.active_client_order_ids: set = set()
        self.in_flight_lock = asyncio.Lock()

    async def get_equity(self) -> float:
        if self.simulated:
            float_pnl = sum(p.unrealized_pnl for p in self.positions.values())
            self.equity = self.balance + float_pnl
            return round(self.equity, 2)
        
        # Query Delta Exchange wallet
        res = await self.client.get_wallet_balances()
        if res.get("success") and "result" in res:
            # Parse USDT / USD equity
            balances = res["result"]
            for b in balances:
                if b.get("asset_symbol") in ["USDT", "USD"]:
                    return float(b.get("balance", self.equity))
        return self.equity

    async def execute_trade(
        self,
        symbol: str,
        product_id: int,
        direction: str,  # "LONG" or "SHORT"
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        client_order_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes an approved signal with duplicate-order prevention and atomic SL/TP.
        """
        async with self.in_flight_lock:
            cid = client_order_id or f"dscalp_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
            
            # 1. Duplicate order prevention check
            if cid in self.active_client_order_ids:
                logger.warning(f"DUPLICATE ORDER PREVENTED: Order ID {cid} already in flight.")
                return {"success": False, "reason": "DUPLICATE_ORDER_REJECTED"}

            if symbol in self.positions:
                logger.warning(f"DUPLICATE ORDER PREVENTED: Position already exists for {symbol}.")
                return {"success": False, "reason": "ACTIVE_POSITION_EXISTS"}

            self.active_client_order_ids.add(cid)

            try:
                side = "buy" if direction == "LONG" else "sell"
                
                if self.simulated or not (self.client.api_key and self.client.api_secret):
                    # Simulated Paper Fill with realistic slippage (0.015%) and taker fee (0.04%)
                    slip_pct = 0.00015
                    fill_price = entry_price * (1.0 + slip_pct) if direction == "LONG" else entry_price * (1.0 - slip_pct)
                    comm = fill_price * quantity * 0.0004
                    self.balance -= comm

                    pos = ManagedPosition(
                        position_id=f"pos_{cid}",
                        symbol=symbol,
                        product_id=product_id,
                        direction=direction,
                        entry_price=fill_price,
                        quantity=quantity,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        mark_price=fill_price,
                        highest_price=fill_price,
                        lowest_price=fill_price,
                        entry_time=time.time()
                    )
                    self.positions[symbol] = pos
                    self.risk_manager.reset_api_errors()

                    logger.info(f"ORDER FILLED (Simulated): {direction} {quantity} {symbol} @ ${fill_price:.2f} | SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}")
                    return {
                        "success": True,
                        "order_id": f"sim_{cid}",
                        "fill_price": fill_price,
                        "quantity": quantity,
                        "commission": comm,
                        "status": "FILLED"
                    }

                # Live Delta Exchange API Call
                res = await self.client.place_order(
                    product_id=product_id,
                    size=quantity,
                    side=side,
                    order_type="market_order",
                    stop_loss_price=stop_loss,
                    take_profit_price=take_profit,
                    client_order_id=cid
                )

                if res.get("success"):
                    self.risk_manager.reset_api_errors()
                    # Store position locally for tracking
                    self.positions[symbol] = ManagedPosition(
                        position_id=cid,
                        symbol=symbol,
                        product_id=product_id,
                        direction=direction,
                        entry_price=entry_price,
                        quantity=quantity,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        mark_price=entry_price,
                        highest_price=entry_price,
                        lowest_price=entry_price,
                        entry_time=time.time()
                    )
                    return {"success": True, "result": res.get("result"), "status": "SUBMITTED"}
                else:
                    self.risk_manager.record_api_error()
                    logger.error(f"Order submission error on Delta: {res.get('error')}")
                    return {"success": False, "error": res.get("error")}

            finally:
                self.active_client_order_ids.discard(cid)

    async def check_positions(self, current_price: float, trailing_activation_r: float = 1.2) -> List[Dict[str, Any]]:
        """
        Monitors active positions against current market price for SL, TP, and Trailing Stops.
        """
        closed_events = []
        for sym, pos in list(self.positions.items()):
            pos.update_mark(current_price)
            risk_dist = abs(pos.entry_price - pos.stop_loss)

            should_close = False
            reason = ""

            # Stop-Loss Check
            if pos.direction == "LONG" and current_price <= pos.stop_loss:
                should_close = True
                reason = "STOP_LOSS_TRIGGERED"
            elif pos.direction == "SHORT" and current_price >= pos.stop_loss:
                should_close = True
                reason = "STOP_LOSS_TRIGGERED"

            # Take-Profit Check
            elif pos.direction == "LONG" and current_price >= pos.take_profit:
                should_close = True
                reason = "TAKE_PROFIT_TRIGGERED"
            elif pos.direction == "SHORT" and current_price <= pos.take_profit:
                should_close = True
                reason = "TAKE_PROFIT_TRIGGERED"

            # Trailing Stop Management
            if not should_close and risk_dist > 0:
                if pos.direction == "LONG":
                    r_gain = (pos.highest_price - pos.entry_price) / risk_dist
                    if r_gain >= trailing_activation_r:
                        new_sl = pos.highest_price - (risk_dist * 0.5)
                        if new_sl > pos.stop_loss:
                            pos.stop_loss = round(new_sl, 2)
                            pos.trailing_activated = True
                else:
                    r_gain = (pos.entry_price - pos.lowest_price) / risk_dist
                    if r_gain >= trailing_activation_r:
                        new_sl = pos.lowest_price + (risk_dist * 0.5)
                        if new_sl < pos.stop_loss:
                            pos.stop_loss = round(new_sl, 2)
                            pos.trailing_activated = True

            if should_close:
                await self.close_position(sym, reason=reason, exit_price=current_price)
                closed_events.append({"symbol": sym, "reason": reason, "exit_price": current_price})

        return closed_events

    async def close_position(self, symbol: str, reason: str = "MANUAL", exit_price: Optional[float] = None) -> Dict[str, Any]:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return {"success": False, "reason": "NO_ACTIVE_POSITION"}

        price = exit_price or pos.mark_price
        gross_pnl = (price - pos.entry_price) * pos.quantity if pos.direction == "LONG" else (pos.entry_price - price) * pos.quantity
        comm = price * pos.quantity * 0.0004
        net_pnl = gross_pnl - comm

        self.balance += net_pnl
        self.risk_manager.realized_daily_pnl += net_pnl

        trade_info = {
            "symbol": symbol,
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "exit_price": price,
            "quantity": pos.quantity,
            "net_pnl": round(net_pnl, 2),
            "reason": reason,
            "duration_seconds": round(time.time() - pos.entry_time, 1),
            "timestamp": time.time()
        }
        self.closed_trades.append(trade_info)

        if not self.simulated and self.client.api_key:
            await self.client.close_position(pos.product_id)

        logger.info(f"POSITION CLOSED: {pos.direction} {symbol} @ ${price:.2f} | Net PnL: ${net_pnl:+.2f} ({reason})")
        return {"success": True, "trade": trade_info}
