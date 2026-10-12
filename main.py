import asyncio
import os
import sys
import argparse
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load local environment configuration
load_dotenv()

from exchange.delta_client import DeltaExchangeClient
from exchange.order_manager import OrderManager
from market_data.orderbook import OrderBookManager
from market_data.trade_flow import TradeFlowTracker
from market_data.delta_websocket import DeltaWebSocketManager
from risk.risk_manager import RiskManager
from risk.position_sizing import PositionSizer
from agents.market_agent import MarketAnalysisAgent
from agents.smc_agent import SMCLiquidityAgent
from agents.execution_agent import ExecutionAgent
from backtesting.backtest import DeltaBacktester

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("delta_ai_scalper")

async def run_backtest_cli(symbol: str = "BTCUSD"):
    logger.info("Initializing Delta AI Scalper event-driven backtest...")
    backtester = DeltaBacktester(symbol=symbol, initial_capital=10000.0)
    result = await backtester.run()

    print("\n" + "="*65)
    print("       DELTA AI SCALPER - BACKTEST PERFORMANCE REPORT")
    print("="*65)
    print(f" Symbol:                 {symbol}")
    print(f" Initial Capital:        $10,000.00")
    print(f" Total Trades:           {result.total_trades}")
    print(f" Win Rate:               {result.win_rate_pct:.1f}% ({result.winning_trades} Wins / {result.losing_trades} Losses)")
    print(f" Profit Factor:          {result.profit_factor:.2f}")
    print(f" Net Realized PnL:       ${result.net_pnl_usd:+.2f} ({result.return_on_capital_pct:+.2f}% Return)")
    print(f" Max Drawdown:           -${result.max_drawdown_usd:.2f} ({result.max_drawdown_pct:.2f}%)")
    print(f" Expectancy:             +{result.expectancy_r:.2f} R per trade")
    print("="*65 + "\n")

async def run_live_scalper(mode: str, symbol: str, product_id: int):
    is_demo = (mode.upper() == "DEMO")
    is_paper = (mode.upper() == "PAPER")

    api_key = os.getenv("DELTA_API_KEY", "")
    api_secret = os.getenv("DELTA_API_SECRET", "")

    logger.info(f"Starting Delta AI Scalper in {mode.upper()} mode for symbol {symbol}...")
    if is_demo:
        logger.info(f"Connecting to Delta Exchange India Testnet: https://cdn-ind.testnet.deltaex.org")
    elif not is_paper:
        logger.info(f"Connecting to Delta Exchange India Production: https://api.india.delta.exchange")
    else:
        logger.info("Operating in local Simulated Paper Trading mode with realistic slippage and fees.")

    # 1. Initialize Components
    client = DeltaExchangeClient(
        api_key=api_key,
        api_secret=api_secret,
        is_demo=is_demo
    )

    risk_manager = RiskManager(
        risk_per_trade_pct=float(os.getenv("RISK_PER_TRADE_PCT", "0.0025")),
        daily_loss_limit_pct=float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.01")),
        max_simultaneous_positions=int(os.getenv("MAX_SIMULTANEOUS_POSITIONS", "1")),
        max_leverage=float(os.getenv("MAX_LEVERAGE", "25")),
        max_consecutive_api_errors=int(os.getenv("MAX_CONSECUTIVE_API_ERRORS", "3"))
    )

    order_manager = OrderManager(
        client=client,
        risk_manager=risk_manager,
        simulated=is_paper or (not api_key)
    )

    sizer = PositionSizer(
        risk_per_trade_pct=risk_manager.risk_per_trade_pct,
        max_leverage=risk_manager.max_leverage
    )

    orderbook = OrderBookManager(symbol=symbol)
    trade_flow = TradeFlowTracker()

    agent1 = MarketAnalysisAgent()
    agent2 = SMCLiquidityAgent(min_rr=2.0)
    agent3 = ExecutionAgent(
        order_manager=order_manager,
        risk_manager=risk_manager,
        position_sizer=sizer,
        min_agent_score=75.0
    )

    # 2. WebSocket Manager
    ws_manager = DeltaWebSocketManager(symbol=symbol, is_demo=is_demo)
    ws_manager.on_orderbook_update = lambda data: orderbook.update_from_snapshot(
        bids_raw=data.get("bids", []),
        asks_raw=data.get("asks", [])
    )
    ws_manager.on_trade_update = lambda data: [
        trade_flow.add_trade(
            price=float(t.get("price", 0)),
            size=float(t.get("size", 0)),
            side=t.get("side", "buy")
        ) for t in data.get("trades", [data] if "price" in data else [])
    ]

    await ws_manager.start()

    # Pre-populate orderbook and synthetic initial depth if offline
    orderbook.update_from_snapshot(
        bids_raw=[[67100.0 - (i * 10), 5.0 + i] for i in range(15)],
        asks_raw=[[67150.0 + (i * 10), 4.0 + i] for i in range(15)]
    )

    print("\n" + "="*70)
    print("      DELTA AI SCALPER ACTIVE - 3-AGENT ARCHITECTURE RUNNING")
    print("="*70)
    print(f" Environment:        {mode.upper()}")
    print(f" Target Contract:    {symbol} (Product ID: {product_id})")
    print(f" Risk per trade:     0.25% equity risk")
    print(f" Max Leverage:       25x")
    print(f" Daily Loss Limit:   1.0%")
    print(f" Consensus Engine:   Agent 1 (Market) + Agent 2 (SMC) + Agent 3 (Exec)")
    print(" Press Ctrl+C to terminate.")
    print("="*70 + "\n")

    backtester = DeltaBacktester(symbol=symbol, product_id=product_id)
    history_df = backtester.generate_synthetic_candles(num_bars=100, start_price=67100.0)

    try:
        while True:
            cur_price = orderbook.mid_price or float(history_df["close"].iloc[-1])
            spread_bps = orderbook.spread_bps or 0.8

            # Check positions and active trailing stops
            await order_manager.check_positions(cur_price)

            # Evaluate Agents
            a1_sig = agent1.evaluate(history_df)
            a2_sig = agent2.evaluate(history_df)
            
            # Execute Decision
            decision = await agent3.evaluate_and_execute(
                symbol=symbol,
                product_id=product_id,
                agent1_sig=a1_sig,
                agent2_sig=a2_sig,
                spread_bps=spread_bps
            )

            if decision.action != "NO_TRADE":
                logger.info(f"⚡ AGENT CONSENSUS TRIGGERED: {decision.action} {decision.quantity} {symbol} @ ${cur_price:.2f} (Confidence: {decision.confidence:.1f}%)")

            await asyncio.sleep(2.0)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Stopping Delta AI Scalper...")
    finally:
        await ws_manager.stop()
        await client.close()

def main():
    parser = argparse.ArgumentParser(description="Delta Exchange AI Scalper - 3-Agent Architecture")
    parser.add_argument("--mode", choices=["DEMO", "LIVE", "PAPER", "BACKTEST"], default=os.getenv("TRADING_MODE", "DEMO"), help="Runtime mode")
    parser.add_argument("--symbol", default=os.getenv("DEFAULT_SYMBOL", "BTCUSD"), help="Derivative symbol")
    parser.add_argument("--product_id", type=int, default=int(os.getenv("DEFAULT_PRODUCT_ID", "27")), help="Delta product ID")
    args = parser.parse_args()

    if args.mode.upper() == "BACKTEST":
        asyncio.run(run_backtest_cli(args.symbol))
    else:
        asyncio.run(run_live_scalper(args.mode, args.symbol, args.product_id))

if __name__ == "__main__":
    main()
