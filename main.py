import argparse
import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from config.settings import load_settings
from backtest.engine import BacktestEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("autonomous_scalper")

async def run_backtest_cli():
    logger.info("Initializing high-fidelity Walk-Forward event-driven backtest...")
    engine = BacktestEngine(symbol="BTCUSDT", initial_capital=10000.0)
    result = await engine.run()
    
    m = result["metrics"]
    print("\n" + "="*55)
    print("      AUTONOMOUS SCALPER BACKTEST PERFORMANCE REPORT")
    print("="*55)
    print(f"Total Completed Trades : {m['total_trades']}")
    print(f"Win Rate               : {m['win_rate_pct']}% ({m['winning_trades']}W / {m['losing_trades']}L)")
    print(f"Profit Factor          : {m['profit_factor']}")
    print(f"Expectancy (USD)       : +${m['expectancy_usd']} per trade")
    print(f"Expectancy (R)         : +{m['expectancy_r']} R")
    print(f"Net Profit             : +${m['net_profit_usd']} ({m['return_on_capital_pct']}%)")
    print(f"Max Drawdown           : -{m['max_drawdown_pct']}% (-${m['max_drawdown_usd']})")
    print(f"Sharpe Ratio           : {m['sharpe_ratio']}")
    print(f"Sortino Ratio          : {m['sortino_ratio']}")
    print(f"Calmar Ratio           : {m['calmar_ratio']}")
    print(f"Total Commission Paid  : ${m['total_commission_usd']}")
    print(f"Total Slippage Incurred: ${m['total_slippage_usd']}")
    print("="*55 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Autonomous Crypto Scalping Agent — 3-Agent Architecture")
    parser.add_argument("--mode", choices=["BACKTEST", "PAPER", "LIVE"], default="PAPER", help="System runtime mode")
    parser.add_argument("--serve", action="store_true", help="Launch FastAPI web monitoring dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Web dashboard host")
    
    args = parser.parse_args()

    if args.serve:
        logger.info(f"Starting Web Dashboard & Telemetry Server on http://{args.host}:{args.port}")
        uvicorn.run("monitoring.server:app", host=args.host, port=args.port, reload=False, log_level="info")
    elif args.mode == "BACKTEST":
        asyncio.run(run_backtest_cli())
    else:
        logger.info(f"Starting Autonomous Scalper in {args.mode} mode...")
        logger.info(f"Starting Web Dashboard server on http://{args.host}:{args.port}")
        uvicorn.run("monitoring.server:app", host=args.host, port=args.port, reload=False, log_level="info")

if __name__ == "__main__":
    main()
