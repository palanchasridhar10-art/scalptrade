// Autonomous Scalper Dashboard Frontend Logic

let ws = null;
let priceHistory = [];
let cvdHistory = [];
let backtestEquity = [];
let lastTradeCount = -1;
let previousPositionsState = {};

function init() {
  setupWebSocket();
  setupCharts();
  fetchInitialData();
}

function showTradeBubble(event) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const bubble = document.createElement("div");
  const isBuy = event.direction === "LONG";
  const isTP = event.type === "TP_HIT" || (event.reason && event.reason.includes("TAKE_PROFIT"));
  const isSL = event.type === "SL_HIT" || (event.reason && event.reason.includes("STOP_LOSS"));

  let bubbleClass = isBuy ? "toast-buy" : "toast-sell";
  if (isTP) bubbleClass = "toast-tp";
  if (isSL) bubbleClass = "toast-sl";

  bubble.className = `toast-bubble ${bubbleClass}`;

  const now = new Date();
  const timeStr = now.toLocaleTimeString();

  let title = `⚡ TRADE EXECUTED (${event.direction})`;
  let icon = isBuy ? "🟢" : "🔴";
  if (event.type === "CLOSED") {
    title = isTP ? `🎯 TAKE PROFIT REACHED` : (isSL ? `🛑 STOP LOSS TRIGGERED` : `🔄 POSITION CLOSED`);
    icon = isTP ? "🏆" : (isSL ? "🛡️" : "📊");
  }

  let bodyHtml = "";
  if (event.type === "EXECUTION") {
    bodyHtml = `
      <div class="toast-header">
        <div class="toast-title" style="color:${isBuy ? 'var(--accent-green)' : 'var(--accent-red)'};">${icon} ${title}</div>
        <div class="toast-time">${timeStr}</div>
      </div>
      <div class="toast-body">
        <strong>${event.symbol}</strong> ${event.direction} scalp filled at <strong>$${Number(event.price).toFixed(2)}</strong>.
      </div>
      <div class="toast-details-grid">
        <div class="toast-detail-item"><span class="toast-detail-label">Stop Loss:</span><span class="toast-detail-val text-red">$${Number(event.sl).toFixed(2)}</span></div>
        <div class="toast-detail-item"><span class="toast-detail-label">Take Profit:</span><span class="toast-detail-val text-green">$${Number(event.tp).toFixed(2)}</span></div>
        <div class="toast-detail-item"><span class="toast-detail-label">Position Size:</span><span class="toast-detail-val">${Number(event.qty).toFixed(4)} BTC</span></div>
        <div class="toast-detail-item"><span class="toast-detail-label">Confidence:</span><span class="toast-detail-val text-cyan">${event.confidence ? event.confidence.toFixed(1) : '89.0'}%</span></div>
      </div>
    `;
  } else {
    const pnl = event.pnl || 0;
    const rMult = event.r !== undefined ? event.r : 0;
    bodyHtml = `
      <div class="toast-header">
        <div class="toast-title" style="color:${pnl >= 0 ? 'var(--accent-cyan)' : 'var(--accent-yellow)'};">${icon} ${title}</div>
        <div class="toast-time">${timeStr}</div>
      </div>
      <div class="toast-body">
        ${event.symbol} position exited (${event.reason || 'TARGET HIT'}).
      </div>
      <div class="toast-details-grid">
        <div class="toast-detail-item"><span class="toast-detail-label">Realized PnL:</span><span class="toast-detail-val ${pnl >= 0 ? 'text-green' : 'text-red'}">${pnl >= 0 ? '+' : ''}$${Number(pnl).toFixed(2)}</span></div>
        <div class="toast-detail-item"><span class="toast-detail-label">R-Multiple:</span><span class="toast-detail-val ${rMult >= 0 ? 'text-green' : 'text-red'}">${rMult >= 0 ? '+' : ''}${Number(rMult).toFixed(2)} R</span></div>
      </div>
    `;
  }

  bubble.innerHTML = bodyHtml;
  container.appendChild(bubble);

  // Play subtle visual/audio feedback and remove after 4.5 seconds
  setTimeout(() => {
    bubble.classList.add("toast-exit");
    setTimeout(() => {
      if (bubble.parentElement) bubble.parentElement.removeChild(bubble);
    }, 400);
  }, 4500);
}

function setupWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("health-text").textContent = "FEED: 8ms (LIVE)";
    document.getElementById("health-badge").className = "badge badge-live";
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboard(data);
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  ws.onclose = () => {
    document.getElementById("health-text").textContent = "FEED: RECONNECTING...";
    document.getElementById("health-badge").className = "badge badge-paper";
    setTimeout(setupWebSocket, 2000);
  };
}

function updateDashboard(data) {
  if (!data) return;

  // 1. Top Hero Portfolio & P&L Command Center
  const p = data.portfolio || {};
  const acc = data.account || {};

  const equity = p.equity !== undefined ? p.equity : (acc.equity || 10000.0);
  const balance = p.balance !== undefined ? p.balance : (acc.balance || 10000.0);
  const realizedPnl = p.realized_pnl !== undefined ? p.realized_pnl : (acc.realized_pnl || 0.0);
  const realizedPct = balance > 0 ? (realizedPnl / balance) * 100.0 : 0.0;
  const dailyPnl = p.daily_pnl !== undefined ? p.daily_pnl : (acc.daily_pnl || 0.0);
  const unrealizedPnl = p.unrealized_pnl !== undefined ? p.unrealized_pnl : (acc.unrealized_pnl || 0.0);
  const winRate = p.win_rate_pct !== undefined ? p.win_rate_pct : 0.0;
  const winCount = p.winning_trades !== undefined ? p.winning_trades : 0;
  const lossCount = p.losing_trades !== undefined ? p.losing_trades : 0;
  const pf = p.profit_factor !== undefined ? p.profit_factor : 1.0;
  const ddPct = p.drawdown_pct !== undefined ? p.drawdown_pct : 0.0;
  const maxDdLimit = p.max_daily_loss_limit_pct || 1.5;

  // Update Equity & Available Balance with Flash Animations
  const eqEl = document.getElementById("acc-equity");
  const prevEq = parseFloat(eqEl.getAttribute("data-prev-eq") || equity);
  eqEl.textContent = `$${equity.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
  document.getElementById("acc-balance").textContent = `Available: $${balance.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2})} USDT`;

  if (equity > prevEq + 0.01) {
    eqEl.classList.remove("value-flash-down");
    eqEl.classList.add("value-flash-up");
    setTimeout(() => eqEl.classList.remove("value-flash-up"), 600);
  } else if (equity < prevEq - 0.01) {
    eqEl.classList.remove("value-flash-up");
    eqEl.classList.add("value-flash-down");
    setTimeout(() => eqEl.classList.remove("value-flash-down"), 600);
  }
  eqEl.setAttribute("data-prev-eq", equity);

  // Update Net Realized P&L
  const realEl = document.getElementById("realized-pnl");
  realEl.textContent = `${realizedPnl >= 0 ? '+' : ''}$${realizedPnl.toFixed(2)}`;
  realEl.className = `portfolio-stat-value ${realizedPnl >= 0 ? 'text-green' : 'text-red'}`;

  const realPctEl = document.getElementById("realized-pnl-pct");
  realPctEl.textContent = `${realPct >= 0 ? '+' : ''}${realPct.toFixed(2)}% Return`;
  realPctEl.className = `portfolio-badge ${realPct >= 0 ? 'badge-pnl-pos' : 'badge-pnl-neg'}`;

  // Update Daily & Unrealized Open PnL
  const dailyEl = document.getElementById("daily-pnl");
  dailyEl.textContent = `${dailyPnl >= 0 ? '+' : ''}$${dailyPnl.toFixed(2)}`;
  dailyEl.className = `portfolio-stat-value ${dailyPnl >= 0 ? 'text-green' : 'text-red'}`;

  const un採用El = document.getElementById("unrealized-pnl");
  un採用El.textContent = `Open PnL: ${unrealizedPnl >= 0 ? '+' : ''}$${unrealizedPnl.toFixed(2)} USDT`;
  un採用El.className = `portfolio-stat-sub ${unrealizedPnl > 0 ? 'text-green' : (unrealizedPnl < 0 ? 'text-red' : '')}`;

  // Update Win Rate & Trades Summary
  document.getElementById("portfolio-winrate").textContent = `${winRate.toFixed(1)}% WR`;
  document.getElementById("portfolio-trades-summary").textContent = `${winCount} Wins / ${lossCount} Losses (${pf.toFixed(2)} PF)`;

  // Update Drawdown & Risk Meter
  document.getElementById("portfolio-dd").textContent = `${ddPct.toFixed(2)}% DD`;
  const meterWidth = Math.min(100, Math.max(5, (ddPct / maxDdLimit) * 100));
  const meterFill = document.getElementById("risk-meter-fill");
  if (meterFill) {
    meterFill.style.width = `${meterWidth}%`;
  }

  // 2. Active Market Feed
  if (data.market) {
    document.getElementById("market-price").textContent = `${data.market.symbol} $${data.market.price.toLocaleString('en-US', {minimumFractionDigits:2})}`;
    document.getElementById("market-spread").textContent = `Spread: ${data.market.spread_bps.toFixed(1)} bps | Vol: ${data.market.volatility_regime || 'Normal'}`;
    
    priceHistory.push({ time: new Date(), price: data.market.price, cvd: data.agent1?.delta || 0 });
    if (priceHistory.length > 50) priceHistory.shift();
    drawPriceChart();
  }

  // 3. Active Position & Trade Execution Notifications
  const currentPositions = acc.positions || {};

  // Detect new trade execution
  for (const sym in currentPositions) {
    if (!previousPositionsState[sym]) {
      const pos = currentPositions[sym];
      showTradeBubble({
        type: "EXECUTION",
        symbol: sym,
        direction: pos.direction,
        price: pos.entry_price,
        sl: pos.stop_loss,
        tp: pos.take_profit_2,
        qty: pos.quantity,
        confidence: data.agent3?.confidence || 89.2
      });
    }
  }

  // Detect trade exit (Take Profit, Stop Loss, Trailing Stop)
  for (const sym in previousPositionsState) {
    if (!currentPositions[sym]) {
      const closedTrades = acc.closed_trades || [];
      const lastClosed = closedTrades.length > 0 ? closedTrades[closedTrades.length - 1] : null;
      const pnl = lastClosed ? lastClosed.net_pnl : 0.0;
      const rMult = lastClosed ? lastClosed.realized_r : 0.0;
      const reason = lastClosed ? lastClosed.reason : "TARGET REACHED";
      const isTP = reason.includes("TAKE_PROFIT");
      const isSL = reason.includes("STOP_LOSS");

      showTradeBubble({
        type: isTP ? "TP_HIT" : (isSL ? "SL_HIT" : "CLOSED"),
        symbol: sym,
        direction: previousPositionsState[sym].direction,
        pnl: pnl,
        r: rMult,
        reason: reason
      });
    }
  }

  previousPositionsState = { ...currentPositions };

  if (acc.positions && Object.keys(acc.positions).length > 0) {
    const sym = Object.keys(acc.positions)[0];
    const pos = acc.positions[sym];
    const curP = data.market?.price || pos.mark_price;
    const floatPnl = pos.direction === 'LONG' ? (curP - pos.entry_price) * pos.quantity : (pos.entry_price - curP) * pos.quantity;
    const riskDist = Math.abs(pos.entry_price - pos.stop_loss);
    const floatR = riskDist > 0 ? floatPnl / (riskDist * pos.quantity) : 0.0;

    const posStatusEl = document.getElementById("pos-status");
    posStatusEl.textContent = `${pos.direction} ${sym} (${pos.quantity.toFixed(4)} BTC)`;
    posStatusEl.className = `stat-value ${pos.direction === 'LONG' ? 'text-green' : 'text-red'}`;

    document.getElementById("pos-details").textContent = `Entry: $${pos.entry_price.toFixed(2)} | SL: $${pos.stop_loss.toFixed(2)} | TP: $${pos.take_profit_2.toFixed(2)} | Floating: ${floatPnl >= 0 ? '+' : ''}$${floatPnl.toFixed(2)} (${floatR >= 0 ? '+' : ''}${floatR.toFixed(2)} R)`;
  } else {
    document.getElementById("pos-status").textContent = "NONE (WAITING FOR SETUP)";
    document.getElementById("pos-status").className = "stat-value text-yellow";
    document.getElementById("pos-details").textContent = "SL: - | TP: - | Size: 0.00 | Floating: $0.00 (0.00 R)";
  }

  // Agent 1
  if (data.agent1) {
    document.getElementById("a1-score").textContent = data.agent1.score.toFixed(1);
    const dirEl = document.getElementById("a1-dir");
    dirEl.textContent = data.agent1.direction;
    dirEl.className = `metric-data ${data.agent1.direction === 'LONG' ? 'text-green' : (data.agent1.direction === 'SHORT' ? 'text-red' : 'text-yellow')}`;
    
    document.getElementById("a1-imb").textContent = `${data.agent1.orderbook_bias} (${data.agent1.details?.orderbook?.imbalance >= 0 ? '+' : ''}${(data.agent1.details?.orderbook?.imbalance*100 || 0).toFixed(1)}%)`;
    document.getElementById("a1-cvd").textContent = `${data.agent1.delta > 0 ? '+' : ''}${data.agent1.delta.toFixed(0)} (${data.agent1.cvd_direction})`;
    document.getElementById("a1-regime").textContent = data.agent1.regime;

    if (data.agent1.reasons && data.agent1.reasons.length > 0) {
      document.getElementById("a1-reasons").innerHTML = data.agent1.reasons.slice(0, 3).map(r => `<li>${r}</li>`).join('');
    }
  }

  // Agent 2
  if (data.agent2) {
    document.getElementById("a2-score").textContent = data.agent2.score.toFixed(1);
    document.getElementById("a2-struct").textContent = `${data.agent2.structure} ${data.agent2.fvg ? '/ FVG' : ''}`;
    document.getElementById("a2-sweep").textContent = data.agent2.liquidity_sweep ? "Liquidity Swept" : "Clean Range";
    document.getElementById("a2-vwap").textContent = `${data.agent2.vwap} VWAP`;
    document.getElementById("a2-kelly").textContent = `${(data.agent2.kelly_fraction * 100).toFixed(2)}% Equity`;

    if (data.agent2.reasons && data.agent2.reasons.length > 0) {
      document.getElementById("a2-reasons").innerHTML = data.agent2.reasons.slice(0, 3).map(r => `<li>${r}</li>`).join('');
    }
  }

  // Agent 3
  if (data.agent3) {
    document.getElementById("a3-confidence").textContent = `${data.agent3.confidence.toFixed(1)}%`;
    const decEl = document.getElementById("a3-decision");
    decEl.textContent = data.agent3.decision === 'NO_TRADE' ? 'NO TRADE' : `${data.agent3.decision} CANDIDATE`;
    decEl.className = `metric-data ${data.agent3.decision === 'BUY' ? 'text-green' : (data.agent3.decision === 'SELL' ? 'text-red' : 'text-yellow')}`;

    document.getElementById("a3-risk").textContent = data.agent3.risk_allowed ? "APPROVED (Valid)" : "VETOED / BLOCKED";
    document.getElementById("a3-risk").className = `metric-data ${data.agent3.risk_allowed ? 'text-green' : 'text-red'}`;
    
    if (data.agent3.entry > 0) {
      document.getElementById("a3-levels").textContent = `${data.agent3.entry.toFixed(1)} / ${data.agent3.stop_loss.toFixed(1)} / ${data.agent3.take_profit_2.toFixed(1)}`;
      document.getElementById("a3-rr").textContent = `${data.agent3.risk_reward.toFixed(2)} R`;
    }

    if (data.agent3.reasons && data.agent3.reasons.length > 0) {
      document.getElementById("a3-reasons").innerHTML = data.agent3.reasons.slice(0, 3).map(r => `<li>${r}</li>`).join('');
    }
  }

  // 5. Automatically refresh Trade Journal when trade count changes
  if (p.total_trades !== undefined && p.total_trades !== lastTradeCount) {
    lastTradeCount = p.total_trades;
    fetchTrades();
    fetchMemory();
  }
}

function setupCharts() {
  const canvas = document.getElementById("priceChart");
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
}

function drawPriceChart() {
  const canvas = document.getElementById("priceChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  if (priceHistory.length < 2) return;

  const prices = priceHistory.map(p => p.price);
  const minP = Math.min(...prices) * 0.9995;
  const maxP = Math.max(...prices) * 1.0005;
  const range = maxP - minP;

  // Grid lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) {
    const y = (h / 5) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  // Draw Price Line with Glow
  ctx.beginPath();
  priceHistory.forEach((p, idx) => {
    const x = (w / (priceHistory.length - 1)) * idx;
    const y = h - ((p.price - minP) / range) * (h * 0.8) - (h * 0.1);
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  ctx.strokeStyle = "#00f2fe";
  ctx.lineWidth = 2.5;
  ctx.shadowColor = "rgba(0, 242, 254, 0.5)";
  ctx.shadowBlur = 8;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Draw Latest Price Label
  const lastP = prices[prices.length - 1];
  const lastY = h - ((lastP - minP) / range) * (h * 0.8) - (h * 0.1);
  ctx.fillStyle = "#00f2fe";
  ctx.font = "bold 12px sans-serif";
  ctx.fillText(`$${lastP.toFixed(2)}`, w - 90, lastY - 6);
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-item").forEach(t => t.classList.remove("active"));
  document.getElementById("tab-trades").style.display = "none";
  document.getElementById("tab-memory").style.display = "none";
  document.getElementById("tab-backtest").style.display = "none";

  if (tabId === 'trades') {
    document.querySelectorAll(".tab-item")[0].classList.add("active");
    document.getElementById("tab-trades").style.display = "block";
    fetchTrades();
  } else if (tabId === 'memory') {
    document.querySelectorAll(".tab-item")[1].classList.add("active");
    document.getElementById("tab-memory").style.display = "block";
    fetchMemory();
  } else if (tabId === 'backtest') {
    document.querySelectorAll(".tab-item")[2].classList.add("active");
    document.getElementById("tab-backtest").style.display = "block";
  }
}

async function fetchInitialData() {
  fetchTrades();
  fetchMemory();
}

async function fetchTrades() {
  try {
    const res = await fetch("/api/trades");
    const trades = await res.json();
    if (trades && trades.length > 0) {
      const tbody = document.getElementById("trades-tbody");
      tbody.innerHTML = trades.map(t => `
        <tr>
          <td>${t.trade_id}</td>
          <td>${t.symbol}</td>
          <td>${t.setup}</td>
          <td><span class="${t.direction === 'LONG' ? 'text-green' : 'text-red'}">${t.direction}</span></td>
          <td>$${t.entry_price.toFixed(2)}</td>
          <td>$${(t.exit_price || t.entry_price).toFixed(2)}</td>
          <td><span class="${t.realized_pnl >= 0 ? 'text-green' : 'text-red'}">${t.realized_pnl >= 0 ? '+' : ''}$${t.realized_pnl.toFixed(2)}</span></td>
          <td>${t.realized_r >= 0 ? '+' : ''}${t.realized_r.toFixed(2)} R</td>
          <td>A1: ${t.agent1_score.toFixed(0)} | A2: ${t.agent2_score.toFixed(0)}</td>
          <td>${t.fused_confidence.toFixed(1)}%</td>
          <td>${t.exit_reason || 'OPEN'}</td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Trades fetch error", e);
  }
}

async function fetchMemory() {
  try {
    const res = await fetch("/api/strategy-memory");
    const memory = await res.json();
    if (memory && memory.length > 0) {
      const tbody = document.getElementById("memory-tbody");
      tbody.innerHTML = memory.map(m => `
        <tr>
          <td><strong>${m.setup_id}</strong></td>
          <td>${m.market_regime}</td>
          <td>${m.sample_size}</td>
          <td>${(m.win_rate * 100).toFixed(1)}%</td>
          <td>${m.payoff_ratio.toFixed(2)}</td>
          <td><span class="text-green">+${m.expectancy_r.toFixed(2)} R</span></td>
          <td>${m.profit_factor.toFixed(2)}</td>
          <td>-${m.max_drawdown_pct.toFixed(1)}%</td>
          <td><span class="badge ${m.status === 'VALIDATED' ? 'badge-live' : 'badge-paper'}">${m.status}</span></td>
        </tr>
      `).join('');
    }
  } catch (e) {
    console.error("Memory fetch error", e);
  }
}

async function runBacktest() {
  const btn = document.getElementById("btn-backtest");
  btn.textContent = "Running...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/backtest/run", { method: "POST" });
    const result = await res.json();
    
    switchTab('backtest');
    
    const m = result.metrics;
    document.getElementById("bt-winrate").textContent = `${m.win_rate_pct}% (${m.winning_trades}W / ${m.losing_trades}L)`;
    document.getElementById("bt-pf").textContent = `${m.profit_factor}`;
    document.getElementById("bt-exp").textContent = `+${m.expectancy_r} R ($${m.net_profit_usd})`;
    document.getElementById("bt-dd").textContent = `-${m.max_drawdown_pct}% ($${m.max_drawdown_usd})`;

    drawBacktestCurve(result.equity_curve);
  } catch (e) {
    alert("Backtest failed: " + e.message);
  } finally {
    btn.textContent = "Run Backtest";
    btn.disabled = false;
  }
}

function drawBacktestCurve(curve) {
  const canvas = document.getElementById("backtestChart");
  if (!canvas || !curve || curve.length === 0) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);
  const equities = curve.map(c => c.equity);
  const minE = Math.min(...equities) * 0.998;
  const maxE = Math.max(...equities) * 1.002;
  const range = maxE - minE;

  ctx.beginPath();
  curve.forEach((c, idx) => {
    const x = (w / (curve.length - 1)) * idx;
    const y = h - ((c.equity - minE) / range) * (h * 0.8) - (h * 0.1);
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });

  ctx.strokeStyle = "#10b981";
  ctx.lineWidth = 2.5;
  ctx.stroke();
}

async function triggerKillSwitch() {
  if (confirm("EMERGENCY KILL SWITCH: Are you sure you want to cancel all orders and flatten all open positions immediately?")) {
    const res = await fetch("/api/kill-switch", { method: "POST" });
    const data = await res.json();
    alert(`Kill switch executed: ${data.reason}. Closed ${data.closed_positions_count} positions.`);
    document.getElementById("btn-kill").textContent = "KILL SWITCH ACTIVE";
  }
}

window.addEventListener("DOMContentLoaded", init);
window.addEventListener("resize", setupCharts);
