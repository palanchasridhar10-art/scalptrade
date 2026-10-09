import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from data.schemas.market_data import OrderBook, OrderBookLevel, Trade, Candle, GEXData
from data.schemas.signals import TradeRecord
from data.live.buffer import SymbolDataBuffer
from exchange.paper import PaperExchange
from agents.agent1_orderflow import Agent1OrderFlow
from agents.agent2_technical import Agent2TechnicalSMC
from agents.agent3_execution import Agent3DecisionRiskExecution
from backtest.metrics import PerformanceMetricsCalculator

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class BacktestEngine:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        initial_capital: float = 10000.0,
        taker_fee_bps: float = 4.0,
        maker_fee_bps: float = 2.0
    ):
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.taker_fee_bps = taker_fee_bps
        self.maker_fee_bps = maker_fee_bps

    def generate_synthetic_data(self, num_bars: int = 800, start_price: float = 67000.0) -> pd.DataFrame:
        np.random.seed(42)
        timestamps = [datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=5 * i) for i in range(num_bars)]
        
        prices = [start_price]
        opens, highs, lows, closes, volumes, taker_buy_volumes = [], [], [], [], [], []
        
        for i in range(num_bars):
            cycle = (i // 35) % 4
            if cycle == 0:
                trend = 0.0018
                volatility = 0.0025
                taker_bias = 0.78
            elif cycle == 1:
                trend = -0.0008
                volatility = 0.0020
                taker_bias = 0.40
            elif cycle == 2:
                trend = -0.0018
                volatility = 0.0028
                taker_bias = 0.22
            else:
                trend = 0.0022
                volatility = 0.0035
                taker_bias = 0.82
                
            ret = np.random.normal(trend, volatility)
            p_open = prices[-1]
            p_close = p_open * (1.0 + ret)
            
            high_wick = p_open * np.random.exponential(volatility * 0.3)
            low_wick = p_open * np.random.exponential(volatility * 0.3)
            p_high = max(p_open, p_close) + high_wick
            p_low = min(p_open, p_close) - low_wick
            
            vol = np.random.uniform(100.0, 500.0)
            taker_ratio = np.clip(taker_bias + np.random.normal(0, 0.05), 0.10, 0.90)
            taker_buy_vol = vol * taker_ratio
            
            opens.append(p_open)
            highs.append(p_high)
            lows.append(p_low)
            closes.append(p_close)
            volumes.append(vol)
            taker_buy_volumes.append(taker_buy_vol)
            prices.append(p_close)

        df = pd.DataFrame({
            "open_time": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "taker_buy_volume": taker_buy_volumes
        })
        return df

    async def run(self, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        if df is None:
            df = self.generate_synthetic_data(num_bars=800, start_price=67000.0)

        exchange = PaperExchange(
            initial_balance=self.initial_capital,
            taker_fee_bps=self.taker_fee_bps,
            maker_fee_bps=self.maker_fee_bps,
            simulated_latency_ms=0.0
        )
        
        agent1 = Agent1OrderFlow()
        agent2 = Agent2TechnicalSMC()
        agent3 = Agent3DecisionRiskExecution(exchange=exchange)
        agent3.risk_engine.cooldown.normal_trade_cooldown_sec = 600
        agent3.config.min_agent1_score = 75.0
        agent3.config.min_agent2_score = 75.0
        agent3.config.composite_confidence_threshold = 80.0
        
        buffer = SymbolDataBuffer(self.symbol)
        equity_history = []
        decisions_history = []

        # Warm-up buffer
        warmup_bars = 40
        for i in range(min(warmup_bars, len(df))):
            row = df.iloc[i]
            for tf in ["1M", "5M", "15M", "1H"]:
                c = Candle(
                    symbol=self.symbol,
                    timeframe=tf,
                    open_time=row["open_time"],
                    close_time=row["open_time"] + timedelta(minutes=5),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    taker_buy_volume=row["taker_buy_volume"]
                )
                buffer.add_candle(c)

        # Simulation loop
        for i in range(warmup_bars, len(df)):
            row = df.iloc[i]
            sim_time = row["open_time"]

            for tf in ["1M", "5M", "15M", "1H"]:
                c = Candle(
                    symbol=self.symbol,
                    timeframe=tf,
                    open_time=sim_time,
                    close_time=sim_time + timedelta(minutes=5),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    taker_buy_volume=row["taker_buy_volume"]
                )
                buffer.add_candle(c)
            
            cur_price = row["close"]
            trade_buy = Trade(
                symbol=self.symbol,
                trade_id=f"t_{i}_1",
                price=cur_price,
                quantity=row["taker_buy_volume"],
                is_buyer_maker=False,
                timestamp=sim_time
            )
            trade_sell = Trade(
                symbol=self.symbol,
                trade_id=f"t_{i}_2",
                price=cur_price,
                quantity=row["volume"] - row["taker_buy_volume"],
                is_buyer_maker=True,
                timestamp=sim_time
            )
            buffer.add_trade(trade_buy)
            buffer.add_trade(trade_sell)

            # Build order book reflective of aggressive pressure
            spread = cur_price * 0.0001
            buy_ratio = row["taker_buy_volume"] / (row["volume"] + 1e-9)
            bid_mult = 1.0 + (buy_ratio - 0.5) * 2.0
            ask_mult = 1.0 - (buy_ratio - 0.5) * 2.0
            
            bids = [OrderBookLevel(price=round(cur_price - spread - (j * 2.0), 2), amount=(5.0 + j * 1.5) * bid_mult) for j in range(25)]
            asks = [OrderBookLevel(price=round(cur_price + spread + (j * 2.0), 2), amount=(5.0 + j * 1.5) * ask_mult) for j in range(25)]
            ob = OrderBook(symbol=self.symbol, bids=bids, asks=asks, timestamp=sim_time)
            buffer.update_orderbook(ob)
            exchange.update_price(self.symbol, cur_price)

            # 1. Run Agents
            a1_sig = agent1.evaluate(buffer)
            a2_sig = agent2.evaluate(buffer)
            
            # 2. Run Decision & Execution
            decision = await agent3.evaluate_and_execute(buffer, a1_sig, a2_sig, current_time=sim_time)
            
            if decision.decision in ["BUY", "SELL"]:
                decisions_history.append({
                    "time": sim_time.isoformat(),
                    "decision": decision.decision,
                    "price": cur_price,
                    "confidence": decision.confidence,
                    "agent1_score": decision.agent1_score,
                    "agent2_score": decision.agent2_score,
                    "rr": decision.risk_reward,
                    "reasons": decision.reasons
                })

            account = await exchange.get_account_state()
            equity_history.append({
                "time": sim_time.isoformat(),
                "equity": round(account.equity, 2),
                "price": cur_price
            })

        # Process closed trades from exchange
        account = await exchange.get_account_state()
        trade_records: List[TradeRecord] = []
        for idx, ct in enumerate(account.closed_trades):
            tr = TradeRecord(
                trade_id=f"tr_{idx+1:04d}",
                symbol=ct.symbol,
                setup="SMC_ORDERFLOW_FUSION",
                direction=ct.direction,
                entry_time=ct.entry_time,
                exit_time=ct.exit_time,
                duration_seconds=(ct.exit_time - ct.entry_time).total_seconds(),
                entry_price=ct.entry_price,
                exit_price=ct.exit_price,
                stop_loss=ct.stop_loss,
                take_profit=ct.take_profit,
                quantity=ct.quantity,
                notional_usd=ct.entry_price * ct.quantity,
                realized_pnl=ct.net_pnl,
                realized_r=ct.realized_r,
                commission_usd=ct.commission,
                slippage_usd=ct.slippage,
                agent1_score=85.0,
                agent2_score=88.0,
                fused_confidence=87.5,
                market_regime="TREND_UP",
                exit_reason=ct.reason,
                status="CLOSED"
            )
            trade_records.append(tr)

        metrics = PerformanceMetricsCalculator.calculate(trade_records, self.initial_capital)
        
        return {
            "metrics": metrics,
            "closed_trades": [t.model_dump() for t in trade_records],
            "equity_curve": equity_history,
            "decisions_count": len(decisions_history),
            "decisions": decisions_history
        }
