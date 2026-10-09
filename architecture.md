# Autonomous Crypto Scalping Agent — 3-Agent Architecture

## 1. System Architecture Overview

The system is an autonomous, multi-agent crypto scalping platform engineered to process high-frequency market microstructure and multi-timeframe technical structures, enforcing strict mathematical risk controls and requiring dual-agent consensus before any trade execution.

```
                         ┌─────────────────────────┐
                         │     CRYPTO EXCHANGE     │
                         │ Binance / Bybit / etc.  │
                         └────────────┬────────────┘
                                      │
                    Market Data       │ Orders / Fills
                                      │
             ┌────────────────────────▼────────────────────┐
             │             DATA INGESTION LAYER             │
             │                                               │
             │ WebSocket • REST • Order Book • Trades       │
             │ Candles • Funding • Open Interest • Options  │
             └───────────────┬──────────────────────────────┘
                             │
             ┌───────────────┴────────────────┐
             │                                │
             ▼                                ▼
┌─────────────────────────┐      ┌─────────────────────────┐
│ AGENT 1                 │      │ AGENT 2                 │
│ Market Microstructure   │      │ Technical + SMC         │
│ & Order Flow            │      │ + Liquidity             │
│                         │      │                         │
│ • Heat Map              │      │ • Multi-timeframe TA    │
│ • Time & Sales          │      │ • Smart Money Concepts  │
│ • Footprint             │      │ • Liquidity Sweeps      │
│ • Delta                 │      │ • Volume Profile (POC)  │
│ • CVD Divergence        │      │ • Market Profile (TPO)  │
│ • Order Book Imbalance  │      │ • VWAP & Bands          │
│ • Gamma Exposure (GEX)  │      │ • Volatility Regimes    │
│ • Market Regime         │      │ • Kelly Sizing Fraction │
└────────────┬────────────┘      └────────────┬────────────┘
             │                                │
             └───────────────┬────────────────┘
                             │ Structured JSON Signals
                             ▼
                 ┌─────────────────────────┐
                 │ AGENT 3                 │
                 │ DECISION + RISK +       │
                 │ EXECUTION               │
                 │                         │
                 │ • Signal Fusion         │
                 │ • Calibrated Confidence │
                 │ • Risk Engine Override  │
                 │ • Fractional Kelly Size │
                 │ • Dynamic SL/TP (R:R>=2)│
                 │ • Order Dispatch        │
                 │ • Position Lifecycle    │
                 │ • Multi-tier Kill Switch│
                 └────────────┬────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ EXCHANGE ORDER    │
                    │ ENGINE (LIVE/SIM)│
                    └──────────────────┘
```

---

## 2. Core Agent Specifications

### Agent 1: Market Microstructure & Order Flow Agent
- **Mission**: Determine immediate state and order flow dynamics (buyer/seller aggression, absorption, exhaustion, spoofing signals, order book liquidity distribution).
- **Core Modules**:
  1. **Order Book Analyzer**: Evaluates Bid/Ask depth, Top-of-Book spread, Order Book Imbalance ratio $OFI = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}$, and dynamic liquidity removal/spoofing heuristics.
  2. **Heat Map Engine**: Maps resting limit order clusters above/below price, identifying defense walls and liquidity vacuums.
  3. **Time & Sales Analyzer**: Computes aggressive buy/sell trade velocity, burst volume, and absorption/exhaustion pressure ratios.
  4. **Footprint Engine**: Quantifies delta per tick/price level, stacked bid/ask imbalances, and high-volume absorption nodes.
  5. **Cumulative Volume Delta (CVD)**: Real-time CVD tracking $CVD_t = CVD_{t-1} + \Delta_t$ and automatic divergence detection against price action.
  6. **Gamma Exposure (GEX)**: Real-time dealer gamma regime tracking (`VERIFIED`, `ESTIMATED`, `UNAVAILABLE`) based on Deribit/Binance options chains.
  7. **Market Regime Classifier**: Categorizes market into `TREND_UP`, `TREND_DOWN`, `RANGE`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `BREAKOUT`, `BREAKDOWN`, or `UNCERTAIN`.
- **Output Protocol**: Standardized machine-readable JSON containing direction (`LONG`/`SHORT`/`NEUTRAL`), score (0-100), CVD delta, and microstructure attributes.

---

### Agent 2: Technical, Smart Money Concepts & Liquidity Agent
- **Mission**: Identify high-probability structural setups across multiple timeframes (1D, 4H, 1H, 15M, 5M, 1M) and validate macroeconomic momentum alignment.
- **Core Modules**:
  1. **Multi-Timeframe Trend & Momentum**: EMA 20/50/200, VWAP/Anchored VWAP, RSI, Stochastic RSI, MACD, Rate of Change (ROC), ADX.
  2. **Smart Money Concepts (SMC)**: Swing High/Low detection, Break of Structure (BOS), Change of Character (CHoCH), Bullish/Bearish Order Blocks (OB), Fair Value Gaps (FVG), Premium/Discount equilibrium zones, and Liquidity Sweeps.
  3. **Liquidity Engine**: Dynamic tracking of PDH/PDL, PWH/PWL, Equal Highs/Lows (EQH/EQL), Session Highs/Lows, and Internal vs External liquidity targets.
  4. **Volume Profile & Market Profile**: Real-time Point of Control (POC), Value Area High (VAH), Value Area Low (VAL), High Volume Nodes (HVN), Low Volume Nodes (LVN), and TPO single prints.
  5. **Volatility Engine**: Realized volatility, Parkinson volatility, and ATR dynamic bands.
  6. **Kelly Criterion Calculation**: Computes optimal theoretical allocation $f^* = \frac{bp - q}{b}$ scaled by safety multiplier (0.10 - 0.25).
- **Output Protocol**: Standardized machine-readable JSON containing direction, score (0-100), structural trigger (e.g. `LIQUIDITY_SWEEP_FVG`), and key price levels.

---

### Agent 3: Decision, Risk & Execution Agent
- **Mission**: The sole authorized entity for order placement. Fuses Agent 1 & Agent 2 signals, enforces hard risk limits, calibrates execution probability, calculates precise Entry/SL/TP (minimum 2.0 R:R), and actively manages trade lifecycle.
- **Core Modules**:
  1. **Signal Fusion & Confidence Calibration**: Requires both Agent 1 and Agent 2 to agree on direction and exceed minimum score thresholds ($\ge 80$). Computes weighted confidence score.
  2. **Risk Management Engine**: Absolute authority over execution. Enforces `MAX_RISK_PER_TRADE` (0.25% - 0.50%), `MAX_DAILY_LOSS` (1.0% - 2.0%), max correlated exposure, spread/slippage thresholds, and stale data barriers.
  3. **Position Sizing & Order Constructor**: Synthesizes fractional Kelly sizing with hard percentage caps, setting multi-tier Take Profit targets ($TP_1, TP_2$) and structural Stop Losses.
  4. **Execution Engine**: Handles async order submission, fill verification, slippage tracking, and immediate post-fill OCO protective orders.
  5. **Active Position Monitor**: Real-time tracking of mark price, trailing stop-loss, time-based decay stops, structure invalidation exits, and target fill triggers.
  6. **Emergency Kill Switch**: Multi-tier instant shutdown (Manual & Automatic triggered by daily drawdown, exchange disconnect, or stale feed).

---

## 3. Communication Protocol

All inter-agent signals and execution commands are serialized as validated Pydantic JSON schemas.

### Signal Schema (Agent 1 & Agent 2 $\rightarrow$ Agent 3)
```json
{
  "agent_id": "agent1_orderflow",
  "symbol": "BTCUSDT",
  "direction": "LONG",
  "score": 87.5,
  "regime": "TREND_UP",
  "metrics": {
    "delta_1m": 15420.5,
    "cvd_trend": "BULLISH_DIVERGENCE",
    "orderbook_imbalance": 0.38,
    "liquidity_bias": "BID_SUPPORTED",
    "gex_status": "ESTIMATED"
  },
  "timestamp": "2026-10-06T18:30:00Z"
}
```

### Trade Candidate Schema (Agent 3 Output)
```json
{
  "trade_id": "trade_20261006_001",
  "symbol": "BTCUSDT",
  "direction": "LONG",
  "entry_price": 67000.0,
  "stop_loss": 66600.0,
  "take_profit_1": 67400.0,
  "take_profit_2": 67800.0,
  "risk_reward_ratio": 2.0,
  "position_size_usd": 250.0,
  "agent1_score": 87.5,
  "agent2_score": 91.0,
  "confidence_score": 89.2,
  "market_regime": "TREND_UP",
  "reasons": [
    "sell_side_liquidity_sweep",
    "bullish_displacement_fvg",
    "positive_delta_cvd_confirmation",
    "vwap_reclaim"
  ],
  "timestamp": "2026-10-06T18:30:01Z"
}
```

---

## 4. Execution & Safety Rules

1. **Rule 1 (No LLM Trading Decisions)**: Execution is 100% algorithmic and deterministic. LLMs are used solely for synthesis and explanation.
2. **Rule 2 (No Fabricated Data)**: If any required feed is missing or latency $> 2000\text{ ms}$, the system outputs `DATA_UNAVAILABLE` and aborts all trade generation.
3. **Rule 3 (Consensus Mandatory)**: $\text{Agent 1 Direction} \ne \text{Agent 2 Direction} \implies \text{NO TRADE}$.
4. **Rule 4 (Absolute Risk Veto)**: Risk limit violation immediately cancels trade candidate regardless of agent scores.
5. **Rule 5 (Fill Confirmation Mandatory)**: Position manager verifies exchange fill event and account state before registering open position.
