import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.settings import load_settings, SystemSettings
from data.live.buffer import MarketDataManager, SymbolDataBuffer
from data.schemas.market_data import OrderBook, OrderBookLevel, Trade, Candle
from exchange.paper import PaperExchange
from agents.agent1_orderflow import Agent1OrderFlow
from agents.agent2_technical import Agent2TechnicalSMC
from agents.agent3_execution import Agent3DecisionRiskExecution
from storage.database import DatabaseManager
from storage.memory import MemorySystem
from backtest.engine import BacktestEngine
from monitoring.health import HealthMonitor

logger = logging.getLogger("server")

app = FastAPI(title="Autonomous Scalper Agent 3-Agent Architecture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

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

# Initialize active symbols
primary_symbol = "BTCUSDT"
buffer = data_manager.get_or_create(primary_symbol)

# Pre-populate buffer with initial candles
def init_sample_data():
    now = datetime.now(timezone.utc)
    base_price = 67420.50
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

    # Initial order book
    bids = [OrderBookLevel(price=round(base_price - 0.5 - (j * 2.0), 2), amount=4.5 + j * 1.2) for j in range(25)]
    asks = [OrderBookLevel(price=round(base_price + 0.5 + (j * 2.0), 2), amount=3.8 + j * 1.1) for j in range(25)]
    ob = OrderBook(symbol=primary_symbol, bids=bids, asks=asks, timestamp=now)
    buffer.update_orderbook(ob)
    paper_exchange.update_price(primary_symbol, base_price)

init_sample_data()

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
    engine = BacktestEngine(symbol=primary_symbol, initial_capital=settings.initial_capital)
    result = await engine.run()
    return JSONResponse(content=result)

@app.post("/api/kill-switch")
async def trigger_kill_switch_endpoint():
    res = await agent3.kill_switch.trigger("USER_MANUAL_TRIGGER")
    return JSONResponse(content=res)

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await websocket.accept()
    price = 67420.50
    try:
        while True:
            # Simulate slight real-time price & tick fluctuations
            now = datetime.now(timezone.utc)
            delta_p = (hash(str(now)) % 11 - 5) * 1.5
            price = max(60000.0, price + delta_p)
            
            # Update order book & buffer
            bids = [OrderBookLevel(price=round(price - 0.5 - (j * 2.0), 2), amount=5.0 + j * 1.5) for j in range(25)]
            asks = [OrderBookLevel(price=round(price + 0.5 + (j * 2.0), 2), amount=4.0 + j * 1.2) for j in range(25)]
            ob = OrderBook(symbol=primary_symbol, bids=bids, asks=asks, timestamp=now)
            buffer.update_orderbook(ob)
            paper_exchange.update_price(primary_symbol, price)

            # Evaluate Agents
            a1_sig = agent1.evaluate(buffer)
            a2_sig = agent2.evaluate(buffer)
            a3_dec = await agent3.evaluate_and_execute(buffer, a1_sig, a2_sig)
            
            account = await paper_exchange.get_account_state()

            payload = {
                "timestamp": now.isoformat(),
                "market": {
                    "symbol": primary_symbol,
                    "price": price,
                    "spread_bps": ob.spread_bps,
                    "volatility_regime": a1_sig.regime
                },
                "account": account.model_dump(),
                "agent1": a1_sig.model_dump(),
                "agent2": a2_sig.model_dump(),
                "agent3": a3_dec.model_dump()
            }
            
            await websocket.send_text(json.dumps(payload, default=str))
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WS error: {e}")
