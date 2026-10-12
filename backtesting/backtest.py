import asyncio
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from exchange.delta_client import DeltaExchangeClient
from exchange.order_manager import OrderManager
from risk.risk_manager import RiskManager
from risk.position_sizing import PositionSizer
from agents.market_agent import MarketAnalysisAgent
from agents.smc_agent import SMCLiquidityAgent
from agents.execution_agent import ExecutionAgent

@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    net_pnl_usd: float
    return_on_capital_pct: float
    max_drawdown_usd: float
    max_drawdown_pct: float
    expectancy_r: float
    trades: List[Dict[str, Any]] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)

class DeltaBacktester:
    """
    High-fidelity event-driven backtesting engine for Delta AI Scalper.
    Evaluates Agent 1, Agent 2, Risk Manager, and Agent 3 across historical price bars.
    """
    def __init__(
        self,
        symbol: str = "BTCUSD",
        product_id: int = 27,
        initial_capital: float = 10000.0,
        risk_per_trade_pct: float = 0.0025,
        daily_loss_limit_pct: float = 0.01,
        max_leverage: float = 25.0
    ):
        self.symbol = symbol
        self.product_id = product_id
        self.initial_capital = initial_capital
        
        self.risk_manager = RiskManager(
            risk_per_trade_pct=risk_per_trade_pct,
            daily_loss_limit_pct=daily_loss_limit_pct,
            max_leverage=max_leverage
        )
        self.risk_manager.daily_starting_equity = initial_capital
        
        self.client = DeltaExchangeClient(is_demo=True)
        self.order_manager = OrderManager(
            client=self.client,
            risk_manager=self.risk_manager,
            simulated=True,
            initial_balance=initial_capital
        )
        self.sizer = PositionSizer(risk_per_trade_pct=risk_per_trade_pct, max_leverage=max_leverage)
        
        self.agent1 = MarketAnalysisAgent()
        self.agent2 = SMCLiquidityAgent(min_rr=2.0)
        self.agent3 = ExecutionAgent(
            order_manager=self.order_manager,
            risk_manager=self.risk_manager,
            position_sizer=self.sizer,
            min_agent_score=75.0
        )

    def generate_synthetic_candles(self, num_bars: int = 400, start_price: float = 67000.0) -> pd.DataFrame:
        """
        Generates realistic Bitcoin market price action with trends, wicks, and volatility bursts.
        """
        np.random.seed(42)
        prices = [start_price]
        opens, highs, lows, closes, volumes = [], [], [], [], []

        for i in range(num_bars):
            # Market cycle: 0=bull impulse, 1=consolidation, 2=bear impulse, 3=recovery
            cycle = (i // 30) % 4
            trend = 0.0012 if cycle in [0, 3] else (-0.0012 if cycle == 2 else 0.0)
            volatility = 0.0025 if cycle in [0, 2] else 0.0012

            ret = np.random.normal(trend, volatility)
            p_open = prices[-1]
            p_close = p_open * (1.0 + ret)
            
            wick_u = p_open * np.random.exponential(volatility * 0.4)
            wick_l = p_open * np.random.exponential(volatility * 0.4)
            p_high = max(p_open, p_close) + wick_u
            p_low = min(p_open, p_close) - wick_l
            vol = np.random.uniform(50.0, 300.0)

            opens.append(round(p_open, 2))
            highs.append(round(p_high, 2))
            lows.append(round(p_low, 2))
            closes.append(round(p_close, 2))
            volumes.append(round(vol, 2))
            prices.append(p_close)

        return pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })

    async def run(self, df: Optional[pd.DataFrame] = None) -> BacktestResult:
        if df is None:
            df = self.generate_synthetic_candles(num_bars=350, start_price=67000.0)

        equity_curve = []
        warmup = 35

        for i in range(warmup, len(df)):
            sub_df = df.iloc[:i]
            cur_price = float(sub_df["close"].iloc[-1])

            # 1. Update Position Monitoring & Trailing Stops
            await self.order_manager.check_positions(cur_price)

            # 2. Evaluate Agents
            a1_sig = self.agent1.evaluate(sub_df)
            a2_sig = self.agent2.evaluate(sub_df)

            # 3. Execution Agent
            await self.agent3.evaluate_and_execute(
                symbol=self.symbol,
                product_id=self.product_id,
                agent1_sig=a1_sig,
                agent2_sig=a2_sig,
                spread_bps=0.8
            )

            # Record Equity
            eq = await self.order_manager.get_equity()
            equity_curve.append({"bar": i, "price": cur_price, "equity": eq})

        # Close any lingering positions at end of backtest
        if self.symbol in self.order_manager.positions:
            await self.order_manager.close_position(self.symbol, reason="BACKTEST_COMPLETED", exit_price=float(df["close"].iloc[-1]))

        trades = self.order_manager.closed_trades
        n_trades = len(trades)
        wins = [t for t in trades if t["net_pnl"] > 0]
        losses = [t for t in trades if t["net_pnl"] <= 0]

        win_rate = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
        gross_win = sum(t["net_pnl"] for t in wins)
        gross_loss = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
        net_pnl = sum(t["net_pnl"] for t in trades)
        ret_pct = (net_pnl / self.initial_capital) * 100.0

        # Calculate Max Drawdown
        equities = [c["equity"] for c in equity_curve] or [self.initial_capital]
        peak = self.initial_capital
        max_dd_usd = 0.0
        max_dd_pct = 0.0
        for e in equities:
            if e > peak:
                peak = e
            dd = peak - e
            dd_pct = (dd / peak) * 100.0
            if dd > max_dd_usd:
                max_dd_usd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        return BacktestResult(
            total_trades=n_trades,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            net_pnl_usd=round(net_pnl, 2),
            return_on_capital_pct=round(ret_pct, 2),
            max_drawdown_usd=round(max_dd_usd, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            expectancy_r=round(np.mean([t["net_pnl"] for t in trades]) / (self.initial_capital * 0.0025) if trades else 0.0, 2),
            trades=trades,
            equity_curve=equity_curve
        )
