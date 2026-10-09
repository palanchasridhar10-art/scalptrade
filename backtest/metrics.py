from typing import List, Dict, Any
import numpy as np
import pandas as pd
from data.schemas.signals import TradeRecord

class PerformanceMetricsCalculator:
    @staticmethod
    def calculate(trades: List[TradeRecord], initial_capital: float = 10000.0) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0.0,
                "loss_rate_pct": 0.0,
                "profit_factor": 0.0,
                "expectancy_usd": 0.0,
                "expectancy_r": 0.0,
                "average_win_usd": 0.0,
                "average_loss_usd": 0.0,
                "net_profit_usd": 0.0,
                "return_on_capital_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_usd": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "recovery_factor": 0.0,
                "total_commission_usd": 0.0,
                "total_slippage_usd": 0.0
            }

        pnls = [t.realized_pnl for t in trades]
        r_multiples = [t.realized_r for t in trades]
        
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        n_trades = len(pnls)
        n_wins = len(wins)
        n_losses = len(losses)
        
        win_rate = (n_wins / n_trades) * 100.0 if n_trades > 0 else 0.0
        loss_rate = (n_losses / n_trades) * 100.0 if n_trades > 0 else 0.0
        
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = abs(np.mean(losses)) if losses else 0.0
        
        # Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        p_win = n_wins / n_trades if n_trades > 0 else 0.0
        p_loss = n_losses / n_trades if n_trades > 0 else 0.0
        expectancy_usd = (p_win * avg_win) - (p_loss * avg_loss)
        expectancy_r = np.mean(r_multiples) if r_multiples else 0.0
        
        net_profit = sum(pnls)
        return_pct = (net_profit / initial_capital) * 100.0
        
        # Drawdown calculation
        equity_curve = [initial_capital]
        for p in pnls:
            equity_curve.append(equity_curve[-1] + p)
            
        equity_series = pd.Series(equity_curve)
        peak = equity_series.cummax()
        drawdown = peak - equity_series
        drawdown_pct = drawdown / peak
        
        max_dd_usd = float(drawdown.max())
        max_dd_pct = float(drawdown_pct.max()) * 100.0
        
        # Sharpe and Sortino
        returns = pd.Series(pnls) / initial_capital
        mean_ret = float(returns.mean()) if len(returns) > 0 else 0.0
        std_ret = float(returns.std()) if len(returns) > 1 else 0.0
        downside_std = float(returns[returns < 0].std()) if len(returns[returns < 0]) > 1 else 1e-6
        
        annual_factor = np.sqrt(365 * 10) # Assuming active scalper
        sharpe = (mean_ret / (std_ret + 1e-9)) * annual_factor if std_ret > 0 else 0.0
        sortino = (mean_ret / (downside_std + 1e-9)) * annual_factor if downside_std > 0 else 0.0
        
        calmar = (return_pct / max_dd_pct) if max_dd_pct > 0 else 0.0
        recovery = (net_profit / max_dd_usd) if max_dd_usd > 0 else 0.0
        
        total_comm = sum(t.commission_usd for t in trades)
        total_slip = sum(t.slippage_usd for t in trades)

        return {
            "total_trades": n_trades,
            "winning_trades": n_wins,
            "losing_trades": n_losses,
            "win_rate_pct": round(win_rate, 2),
            "loss_rate_pct": round(loss_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy_usd": round(expectancy_usd, 2),
            "expectancy_r": round(float(expectancy_r), 2),
            "average_win_usd": round(float(avg_win), 2),
            "average_loss_usd": round(float(avg_loss), 2),
            "net_profit_usd": round(net_profit, 2),
            "return_on_capital_pct": round(return_pct, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "max_drawdown_usd": round(max_dd_usd, 2),
            "sharpe_ratio": round(float(sharpe), 2),
            "sortino_ratio": round(float(sortino), 2),
            "calmar_ratio": round(float(calmar), 2),
            "recovery_factor": round(float(recovery), 2),
            "total_commission_usd": round(total_comm, 2),
            "total_slippage_usd": round(total_slip, 2)
        }
