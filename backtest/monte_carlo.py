from typing import List, Dict, Any
import numpy as np
import pandas as pd

class MonteCarloSimulator:
    def __init__(self, num_simulations: int = 1000, confidence_level: float = 0.95):
        self.num_simulations = num_simulations
        self.confidence_level = confidence_level

    def simulate(self, trade_pnls: List[float], initial_capital: float = 10000.0) -> Dict[str, Any]:
        if not trade_pnls or len(trade_pnls) < 10:
            return {
                "num_simulations": self.num_simulations,
                "median_max_drawdown_pct": 0.0,
                "var_95_max_drawdown_pct": 0.0,
                "risk_of_ruin_pct": 0.0,
                "median_ending_equity": initial_capital
            }

        simulated_max_dds = []
        ending_equities = []
        ruin_count = 0
        n_trades = len(trade_pnls)

        for _ in range(self.num_simulations):
            # Resample trade returns with replacement
            sampled = np.random.choice(trade_pnls, size=n_trades, replace=True)
            
            equity_path = [initial_capital]
            ruined = False
            for pnl in sampled:
                new_eq = equity_path[-1] + pnl
                if new_eq <= initial_capital * 0.70: # 30% drawdown as ruin threshold
                    ruined = True
                equity_path.append(new_eq)

            if ruined:
                ruin_count += 1

            ending_equities.append(equity_path[-1])
            
            # Max Drawdown
            eq_series = pd.Series(equity_path)
            peak = eq_series.cummax()
            dd_pct = (peak - eq_series) / peak
            simulated_max_dds.append(float(dd_pct.max()) * 100.0)

        median_dd = float(np.median(simulated_max_dds))
        var_95_dd = float(np.percentile(simulated_max_dds, self.confidence_level * 100.0))
        risk_of_ruin = (ruin_count / self.num_simulations) * 100.0
        median_ending = float(np.median(ending_equities))

        return {
            "num_simulations": self.num_simulations,
            "median_max_drawdown_pct": round(median_dd, 2),
            "var_95_max_drawdown_pct": round(var_95_dd, 2),
            "risk_of_ruin_pct": round(risk_of_ruin, 2),
            "median_ending_equity": round(median_ending, 2)
        }
