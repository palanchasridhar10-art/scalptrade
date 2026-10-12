# Delta AI Scalper — Autonomous 3-Agent Trading Architecture

An institutional-grade autonomous crypto scalping system connected to **Delta Exchange India** (Production REST & Demo Testnet) with a specialized 3-Agent architecture and strict risk enforcement.

---

## 🧠 1. Three-Agent Trading Architecture

```
                          DELTA EXCHANGE API
                                   |
             +---------------------+---------------------+
             |                     |                     |
          Candles              Order Book            Live Trades
             |                     |                     |
             +---------------------+---------------------+
                                   |
                         +---------+---------+
                         |                   |
                    AGENT 1               AGENT 2
              AI MARKET ANALYSIS        SMC ANALYSIS
                         |                   |
                   Market Regime       Liquidity Sweeps
                   Volatility          BOS / CHoCH
                   Trend Probability   FVG / Order Blocks
                         |                   |
                         +---------+---------+
                                   |
                            SIGNAL VALIDATOR
                                   |
                             RISK MANAGER
                        (Absolute Veto Authority)
                                   |
                               AGENT 3
                           ORDER EXECUTION
                                   |
                          DELTA FUTURES API
                                   |
                         POSITION MONITORING
```

### 1.1 Agent 1 — AI Market Analysis
- **Market Regime**: Classifies real-time conditions into `TRENDING_BULLISH`, `TRENDING_BEARISH`, `RANGING`, and `HIGH_VOLATILITY`.
- **Volatility**: Evaluates Average True Range (ATR), Bollinger Band bandwidth, and volatility expansion.
- **Trend Probability**: Estimates multi-timeframe directional trend continuation probability ($0.0 - 1.0$).

### 1.2 Agent 2 — SMC & Liquidity Analysis
- **Liquidity Sweeps**: Identifies false breakouts above Buy-Side Liquidity (BSL) or below Sell-Side Liquidity (SSL) with long wick rejections.
- **Break of Structure (BOS)**: Detects trend expansion and impulse continuation.
- **Change of Character (CHoCH)**: Detects early structural trend shifts and reversals.
- **Fair Value Gaps (FVG)**: Quantifies 3-candle imbalance gaps and 50% Consequent Encroachment (CE) levels.
- **Order Blocks**: Locates unmitigated institutional order blocks.
- **Target Levels**: Generates exact Entry, Invalidation (Stop-Loss), and Take-Profit with mandatory $R:R \ge 2.0$.

### 1.3 Signal Validator & Risk Manager
- **Signal Validator**: Requires cross-agent consensus (direction agreement, confidence score $\ge 75.0$, $R:R \ge 2.0$).
- **Risk Manager**: Holds **absolute veto authority** to reject any trade, regardless of agent consensus.

### 1.4 Agent 3 — Execution
- **Position Sizing**: Dynamically calculates contracts adhering strictly to $0.25\%$ equity risk and max $25\times$ leverage.
- **Order Placement**: Executes bracket or market orders with atomic Stop-Loss and Take-Profit.
- **Position Monitoring**: Real-time mark price updates and trailing stop adjustments ($+1.2\text{ R}$ activation).
- **Duplicate-Order Prevention**: Idempotent client order IDs and in-flight locks.
- **Circuit Breaker**: Halts execution upon repeated API errors.

---

## ⚡ 2. Delta Exchange India API Endpoints

| Capability | Delta Exchange India URL | Protocol |
| :--- | :--- | :--- |
| **India Demo / Testnet REST** | `https://cdn-ind.testnet.deltaex.org` | HTTPS REST |
| **India Demo / Testnet WebSocket** | `wss://socket-ind.testnet.deltaex.org` | WSS |
| **India Production REST** | `https://api.india.delta.exchange` | HTTPS REST |
| **India Production WebSocket** | `wss://socket.india.delta.exchange` | WSS |

### HMAC SHA-256 Authentication
Private endpoints are signed using HMAC SHA-256:
$$\text{signature} = \text{HMAC-SHA256}(\text{api\_secret}, \text{METHOD} + \text{timestamp} + \text{path} + \text{query\_string} + \text{body})$$

---

## 🛡️ 3. Risk Management Settings (Configurable)

| Parameter | Setting | Description |
| :--- | :--- | :--- |
| **Risk per trade** | **0.25% of account equity** | Calculated dynamically via Stop-Loss distance |
| **Daily loss limit** | **1.0%** | Trading halted for day if cumulative loss exceeds 1% |
| **Maximum simultaneous positions** | **1** | Only 1 active open contract permitted at a time |
| **Maximum leverage** | **25x** | Notional capped at $25\times$ account equity |
| **Stop-loss** | **Strictly Required** | Rejected if missing or invalid |
| **Take-profit** | **Strictly Required** | Rejected if missing or invalid |
| **Repeated API error threshold** | **3 errors** | Disables trading if consecutive errors reach 3 |
| **Minimum Risk:Reward Ratio** | **2.0 R:R** | Discards setups with $R:R < 2.0$ |

---

## 💻 4. Project Structure

```
delta-ai-scalper/
│
├── agents/
│   ├── market_agent.py          # Agent 1: Regime, Volatility, Trend Probability
│   ├── smc_agent.py             # Agent 2: SMC, Sweeps, BOS, CHoCH, FVG, Levels
│   └── execution_agent.py       # Agent 3: Signal Validator, Risk Review, Execution
│
├── market_data/
│   ├── delta_websocket.py       # Live WebSocket client (Orderbook, Trades, Candles)
│   ├── orderbook.py             # L2 Orderbook, Depth Imbalance, Wall Defense
│   └── trade_flow.py            # Cumulative Volume Delta (CVD) Tracker
│
├── strategies/
│   ├── liquidity_sweep.py       # BSL / SSL Stop-Hunt Sweeps with Wick Rejections
│   ├── fair_value_gap.py        # 3-Candle Imbalance Gaps & Consequent Encroachment
│   └── market_structure.py      # BOS, CHoCH, Order Blocks, Premium/Discount Zones
│
├── risk/
│   ├── position_sizing.py       # 0.25% Equity Risk Sizing & 25x Leverage Cap
│   └── risk_manager.py          # Independent Risk Manager with Absolute Veto Authority
│
├── exchange/
│   ├── delta_client.py          # Async Delta Exchange REST Client with HMAC SHA-256
│   └── order_manager.py         # Duplicate Prevention, Atomic SL/TP & Trailing Stops
│
├── backtesting/
│   └── backtest.py              # Event-Driven Walk-Forward Backtester
│
├── tests/                       # Complete 12-test Unit & Integration Suite
├── .env.example                 # Environment configuration template
├── requirements.txt             # Python dependencies
├── README.md                    # System documentation
└── main.py                      # CLI entry point (DEMO, LIVE, PAPER, BACKTEST)
```

---

## 🚀 5. Getting Started

### 5.1 Installation
```bash
cd delta-ai-scalper
pip install -r requirements.txt
cp .env.example .env
```

### 5.2 Running the Backtester
```bash
python main.py --mode BACKTEST --symbol BTCUSD
```

### 5.3 Running on Delta Exchange India Demo / Testnet
```bash
python main.py --mode DEMO --symbol BTCUSD --product_id 27
```

### 5.4 Running in Simulated Paper Mode
```bash
python main.py --mode PAPER --symbol BTCUSD
```

### 5.5 Running Unit Tests
```bash
pytest tests/ -v
```
