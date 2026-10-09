# Autonomous Scalping Agent — Memory System

## 1. Overview & Anti-Overfitting Principles

The agent memory architecture maintains hierarchical persistence for short-term microstructure buffers, episodic trade logs, and statistically validated strategy knowledge.

### Anti-Overfitting & Safety Invariants
1. **Sample Size Rigor**: No setup is promoted to "trusted" or active deployment without a minimum sample size of $N \ge 100$ trades evaluated under out-of-sample and walk-forward testing.
2. **No Anecdotal Bias**: The agent will never extrapolate from small streaks (e.g. "Pattern X won 3 times in a row, thus it is 100% reliable").
3. **Regime Stratification**: Performance is strictly partitioned by market regime (`TREND_UP`, `TREND_DOWN`, `RANGE`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `BREAKOUT`).
4. **Degradation Detection**: If rolling 30-trade Sharpe drops below 0.5 or rolling Win Rate drops $> 15\%$ below baseline, the strategy state enters `COOLING_DOWN` and risk is reduced by 50%.

---

## 2. Memory Tiers

### 2.1 Short-Term Real-Time Memory (Ring Buffer)
Maintained in-memory for active decision-making:
- **Candles Buffer**: Last 1,000 candles per timeframe (1M, 5M, 15M, 1H, 4H, 1D).
- **Trades Buffer**: Last 5,000 ticks/trades with buy/sell aggressive tagging.
- **Order Book Buffer**: Snapshot history of top 50 depth levels and imbalance ratios.
- **CVD & Delta Buffer**: Rolling cumulative volume delta with divergence markers.
- **Liquidity Buffer**: Active key levels (PDH, PDL, PWH, PWL, EQH, EQL, Order Blocks, FVGs).
- **Current Position State**: Live PnL, mark price, trailing stops, and invalidation triggers.

---

### 2.2 Episodic Trade Memory Schema
Persisted to SQLite/JSON storage upon every completed trade lifecycle:

```json
{
  "trade_id": "tr_20261006_btc_0042",
  "symbol": "BTCUSDT",
  "setup_type": "LIQUIDITY_SWEEP_FVG_CVD_DIV",
  "direction": "LONG",
  "entry_time": "2026-10-06T18:15:00Z",
  "exit_time": "2026-10-06T18:22:30Z",
  "duration_seconds": 450,
  "entry_price": 67120.50,
  "exit_price": 67680.00,
  "stop_loss": 66880.00,
  "take_profit_target": 67650.00,
  "realized_pnl_usd": 140.25,
  "realized_r_multiple": 2.33,
  "commission_usd": 1.85,
  "slippage_usd": 0.50,
  "agent1_score": 88.5,
  "agent2_score": 92.0,
  "fused_confidence": 89.8,
  "market_regime": "TREND_UP",
  "exit_reason": "TAKE_PROFIT_2_REACHED",
  "post_trade_notes": "Clean liquidity sweep below Asian low followed by bullish 5M FVG displacement and positive CVD divergence"
}
```

---

### 2.3 Strategy Memory Matrix (Validated Setups)
Persisted aggregated performance repository:

| Setup Identifier | Market Regime | Sample Size ($N$) | Win Rate | Payoff ($b$) | Expectancy ($R$) | Profit Factor | Max Drawdown | Status |
|---|---|---|---|---|---|---|---|---|
| `LIQUIDITY_SWEEP_FVG` | `TREND_UP` | 142 | 68.3% | 2.15 | +1.15 R | 2.41 | -3.8% | **VALIDATED** |
| `BOS_RETEST_ORDER_BLOCK` | `TREND_UP` | 98 | 64.2% | 2.40 | +1.18 R | 2.28 | -4.2% | **VALIDATED** |
| `RANGE_DEVIATION_VWAP` | `RANGE` | 185 | 71.8% | 1.65 | +0.90 R | 2.12 | -3.1% | **VALIDATED** |
| `BREAKOUT_OFI_SURGE` | `HIGH_VOLATILITY`| 62 | 53.2% | 2.80 | +1.02 R | 1.85 | -5.6% | **INCUBATING** |
| `COUNTER_TREND_EXHAUSTION` | `TREND_DOWN`| 45 | 42.0% | 1.90 | +0.21 R | 1.10 | -7.2% | **DISABLED** |

---

## 3. Memory Safety & Adaptation Protocols

1. **Strategy Status States**:
   - `INCUBATING`: $N < 80$, position sizing capped at $0.10\%$ risk.
   - `VALIDATED`: $N \ge 80$, positive expectancy $\ge 0.5 R$, full fractional Kelly allowed.
   - `COOLING_DOWN`: Consecutive losses $\ge 3$ or rolling DD $> 5\%$; risk halved.
   - `DISABLED`: Expectancy $< 0.1 R$ or Sharpe $< 0.5$; automatically halted.
2. **Review Triggers**:
   - Every 24 hours: Recalibration of win probability $p$ and payoff $b$ for Kelly calculations.
   - Every week: Full walk-forward analysis against recent out-of-sample data.
