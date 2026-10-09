import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Set
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.settings import load_settings, SystemSettings
from data.live.buffer import MarketDataManager, SymbolDataBuffer
from data.schemas.market_data import OrderBook, OrderBookLevel, Trade, Candle
from exchange.paper import PaperExchange
from exchange.account import Position, ClosedTradeInfo
from agents.agent1_orderflow import Agent1OrderFlow
from agents.agent2_technical import Agent2TechnicalSMC
from agents.agent3_execution import Agent3DecisionRiskExecution
from storage.database import DatabaseManager
from storage.memory import MemorySystem
from backtest.engine import BacktestEngine
from monitoring.health import HealthMonitor

logger = logging.getLogger("server")

# Shared runtime state
settings: SystemSettings = load_settings()
data_manager = MarketDataManager()
db_manager = DatabaseManager()
memory_system = MemorySystem(db=db_manager)
paper_exchange = PaperExchange(initial_balance=settings.initial_capital)

agent1 = Agent1OrderFlow(settings.agent1)
agent2 = Agent2TechnicalSMC(settings.agent2)
agent3 = Agent3DecisionRiskExecution(
    exchange=paper_exchange,
    config=settings.agent3,
    risk_limits=settings.risk_limits,
    cooldown=settings.cooldown,
    emergency=settings.emergency
)
health_monitor = HealthMonitor(data_manager)

primary_symbol = "BTCUSDT"
buffer = data_manager.get_or_create(primary_symbol)
active_websockets: Set[WebSocket] = set()

active_trades_map: Dict[str, Dict[str, Any]] = {}
current_price = 67420.50
tick_counter = 0

def init_sample_data():
    global current_price
    now = datetime.now(timezone.utc)
    base_price = 67420.50
    current_price = base_price
    
    # 50 historical 5M candles
    for i in range(50):
        t = now - timedelta(minutes=5 * (50 - i))
        p = base_price + (i * 8.5) + (i % 3 * 5.0)
        c = Candle(
            symbol=primary_symbol,
            timeframe="5M",
            open_time=t,
            close_time=t + timedelta(minutes=5),
            open=p - 10.0,
            high=p + 25.0,
            low=p - 15.0,
            close=p + 12.0,
            volume=120.0 + (i * 2.0),
            taker_buy_volume=75.0 + (i * 1.5)
        )
        buffer.add_candle(c)

    # Initial order book & trades
    bids = [OrderBookLevel(price=round(base_price - 0.5 - (j * 2.0), 2), amount=4.5 + j * 1.2) for j in range(25)]
    asks = [OrderBookLevel(price=round(base_price + 0.5 + (j * 2.0), 2), amount=3.8 + j * 1.1) for j in range(25)]
    ob = OrderBook(symbol=primary_symbol, bids=bids, asks=asks, timestamp=now)
    buffer.update_orderbook(ob)
    paper_exchange.update_price(primary_symbol, base_price)

    # Seed realistic initial trades into buffer
    for k in range(50):
        trade_time = now - timedelta(seconds=(50 - k) * 2)
        side = "BUY" if (k % 3 != 0) else "SELL"
        tr = Trade(
            symbol=primary_symbol,
            trade_id=f"seed_{k}",
            price=base_price + (k * 0.5),
            quantity=1.5 + (k % 4) * 0.5,
            is_buyer_maker=(side == "SELL"),
            timestamp=trade_time
        )
        buffer.add_trade(tr)

init_sample_data()

async def autonomous_trading_engine_loop():
    """Continuous 24/7 background autonomous engine evaluating and executing trades"""
    global current_price, tick_counter
    logger.info("Autonomous Scalper Trading Engine background task started.")
    
    while True:
        try:
            now = datetime.now(timezone.utc)
            tick_counter += 1

            # Realistic micro-fluctuations and momentum bursts
            cycle = tick_counter % 30
            if cycle < 12:
                # Bullish buildup & sweep
                delta_p = 4.5 + (tick_counter % 3) * 2.0
                trade_side = "BUY"
                trade_amt = 3.5 + (tick_counter % 5) * 1.2
            elif cycle < 18:
                # Retracement to FVG / discount
                delta_p = -3.5 - (tick_counter % 3) * 1.5
                trade_side = "SELL"
                trade_amt = 1.5 + (tick_counter % 3) * 0.8
            else:
                # Continuation rally
                delta_p = 6.0 + (tick_counter % 4) * 2.5
                trade_side = "BUY"
                trade_amt = 4.5 + (tick_counter % 6) * 1.5

            current_price = max(50000.0, current_price + delta_p)

            # Ingest trade tick into live buffer
            t_obj = Trade(
                symbol=primary_symbol,
                trade_id=f"t_{int(now.timestamp())}_{tick_counter}",
                price=round(current_price, 2),
                quantity=round(trade_amt, 4),
                is_buyer_maker=(trade_side == "SELL"),
                timestamp=now
            )
            buffer.add_trade(t_obj)

            # Update Order Book
            spread = 0.50
            bids = [OrderBookLevel(price=round(current_price - spread - (j * 2.0), 2), amount=5.0 + j * 1.5) for j in range(25)]
            asks = [OrderBookLevel(price=round(current_price + spread + (j * 2.0), 2), amount=4.0 + j * 1.2) for j in range(25)]
            ob = OrderBook(symbol=primary_symbol, bids=bids, asks=asks, timestamp=now)
            buffer.update_orderbook(ob)
            paper_exchange.update_price(primary_symbol, current_price)

            # Track 1M and 5M candle rolls
            c_last = Candle(
                symbol=primary_symbol,
                timeframe="1M",
                open_time=now - timedelta(minutes=1),
                close_time=now,
                open=current_price - delta_p,
                high=current_price + 8.0,
                low=current_price - 6.0,
                close=current_price,
                volume=85.0 + trade_amt * 10,
                taker_buy_volume=55.0 if trade_side == "BUY" else 30.0
            )
            buffer.add_candle(c_last)

            # 1. Track open positions before evaluation
            acc_before = await paper_exchange.get_account_state()
            open_pos_before = dict(acc_before.positions)

            # 2. Evaluate Agents and Execute
            a1_sig = agent1.evaluate(buffer)
            a2_sig = agent2.evaluate(buffer)
            a3_dec = await agent3.evaluate_and_execute(buffer, a1_sig, a2_sig)

            # 3. Track open positions after evaluation
            acc_after = await paper_exchange.get_account_state()
            open_pos_after = dict(acc_after.positions)

            # Detect new trade opened
            for sym, pos in open_pos_after.items():
                if sym not in open_pos_before:
                    t_id = f"tr_{int(now.timestamp())}_{uuid.uuid4().hex[:4]}"
                    trade_record = {
                        "trade_id": t_id,
                        "symbol": sym,
                        "setup": "LIQUIDITY_SWEEP_FVG",
                        "direction": pos.direction,
                        "entry_time": now.isoformat(),
                        "exit_time": None,
                        "duration_seconds": 0,
                        "entry_price": pos.entry_price,
                        "exit_price": None,
                        "stop_loss": pos.stop_loss,
                        "take_profit": pos.take_profit_2,
                        "quantity": pos.quantity,
                        "notional_usd": round(pos.entry_price * pos.quantity, 2),
                        "realized_pnl": 0.0,
                        "realized_r": 0.0,
                        "commission_usd": round(pos.entry_price * pos.quantity * 0.0004, 2),
                        "slippage_usd": round(pos.entry_price * pos.quantity * 0.00015, 2),
                        "agent1_score": a1_sig.score,
                        "agent2_score": a2_sig.score,
                        "fused_confidence": a3_dec.confidence,
                        "market_regime": a1_sig.regime,
                        "exit_reason": "ACTIVE_OPEN",
                        "status": "OPEN"
                    }
                    active_trades_map[sym] = trade_record
                    db_manager.record_trade(trade_record)
                    logger.info(f"LIVE TRADE EXECUTED: {pos.direction} {sym} @ ${pos.entry_price:.2f}")

            # Detect position closed
            for sym, pos in open_pos_before.items():
                if sym not in open_pos_after and sym in active_trades_map:
                    tr = active_trades_map.pop(sym)
                    # Find latest closed trade info
                    if acc_after.closed_trades:
                        last_c = acc_after.closed_trades[-1]
                        tr["exit_time"] = now.isoformat()
                        tr["exit_price"] = last_c.exit_price
                        tr["duration_seconds"] = (now - pos.entry_time).total_seconds()
                        tr["realized_pnl"] = round(last_c.net_pnl, 2)
                        tr["realized_r"] = round(last_c.realized_r, 2)
                        tr["commission_usd"] = round(last_c.commission, 2)
                        tr["slippage_usd"] = round(last_c.slippage, 2)
                        tr["exit_reason"] = last_c.reason
                        tr["status"] = "CLOSED"
                        db_manager.record_trade(tr)
                        memory_system.record_trade(last_c)
                        logger.info(f"LIVE TRADE CLOSED: {sym} Net PnL: ${last_c.net_pnl:+.2f} ({last_c.realized_r:+.2f} R) Reason: {last_c.reason}")

            # Calculate Comprehensive Portfolio Statistics
            closed_trades = acc_after.closed_trades
            total_trades_count = len(closed_trades)
            win_trades = [t for t in closed_trades if t.net_pnl > 0]
            loss_trades = [t for t in closed_trades if t.net_pnl <= 0]
            win_rate = (len(win_trades) / total_trades_count * 100.0) if total_trades_count > 0 else 0.0
            total_wins_val = sum(t.net_pnl for t in win_trades)
            total_loss_val = abs(sum(t.net_pnl for t in loss_trades))
            profit_factor = (total_wins_val / total_loss_val) if total_loss_val > 0 else (2.5 if total_wins_val > 0 else 1.0)
            
            realized_pnl = sum(t.net_pnl for t in closed_trades)
            unrealized_pnl = acc_after.unrealized_pnl
            daily_pnl = acc_after.daily_pnl
            daily_pnl_pct = acc_after.daily_pnl_pct * 100.0
            
            hwm = acc_after.high_watermark
            dd_pct = ((hwm - acc_after.equity) / hwm * 100.0) if hwm > 0 else 0.0

            # Construct Web Telemetry Payload
            portfolio_summary = {
                "equity": round(acc_after.equity, 2),
                "balance": round(acc_after.balance, 2),
                "daily_pnl": round(daily_pnl, 2),
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "realized_pnl": round(realized_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "total_trades": total_trades_count,
                "winning_trades": len(win_trades),
                "losing_trades": len(loss_trades),
                "win_rate_pct": round(win_rate, 1),
                "profit_factor": round(profit_factor, 2),
                "drawdown_pct": round(dd_pct, 2),
                "max_daily_loss_limit_pct": settings.risk_limits.max_daily_loss_pct * 100.0
            }

            payload = {
                "timestamp": now.isoformat(),
                "portfolio": portfolio_summary,
                "market": {
                    "symbol": primary_symbol,
                    "price": round(current_price, 2),
                    "spread_bps": ob.spread_bps,
                    "volatility_regime": a1_sig.regime
                },
                "account": acc_after.model_dump(),
                "agent1": a1_sig.model_dump(),
                "agent2": a2_sig.model_dump(),
                "agent3": a3_dec.model_dump()
            }

            # Broadcast to active WebSockets
            dead_sockets = set()
            msg_str = json.dumps(payload, default=str)
            for ws in active_websockets:
                try:
                    await ws.send_text(msg_str)
                except Exception:
                    dead_sockets.add(ws)
            active_websockets.difference_update(dead_sockets)

        except Exception as e:
            logger.error(f"Error in autonomous scalper loop: {e}", exc_info=True)

        await asyncio.sleep(1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch continuous background scalper engine
    task = asyncio.create_task(autonomous_trading_engine_loop())
    yield
    task.cancel()

app = FastAPI(title="Autonomous Scalper Agent 3-Agent Architecture", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))

@app.get("/api/status")
async def get_status():
    account = await paper_exchange.get_account_state()
    health = health_monitor.check_health()
    return {
        "mode": settings.trading_mode,
        "health": health,
        "account": account.model_dump(),
        "primary_symbol": primary_symbol
    }

@app.get("/api/trades")
async def get_trades():
    trades = db_manager.get_recent_trades(limit=50)
    return JSONResponse(content=trades)

@app.get("/api/strategy-memory")
async def get_strategy_memory():
    knowledge = memory_system.get_strategy_knowledge()
    return JSONResponse(content=knowledge)

@app.post("/api/backtest/run")
async def run_backtest_endpoint():
    try:
        engine = BacktestEngine(symbol=primary_symbol, initial_capital=settings.initial_capital)
        result = await engine.run()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Backtest endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e), "message": "Backtest execution encountered an error"})

@app.post("/api/kill-switch")
async def trigger_kill_switch_endpoint():
    res = await agent3.kill_switch.trigger("USER_MANUAL_TRIGGER")
    return JSONResponse(content=res)

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        while True:
            # Keep socket alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.discard(websocket)
    except Exception:
        active_websockets.discard(websocket)
