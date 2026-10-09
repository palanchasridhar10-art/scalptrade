from typing import Dict, Any

class KellyCriterion:
    def __init__(self, fraction_multiplier: float = 0.15, max_risk_cap: float = 0.005):
        self.fraction_multiplier = fraction_multiplier
        self.max_risk_cap = max_risk_cap

    def calculate(
        self,
        win_rate: float,       # p (e.g. 0.58)
        payoff_ratio: float,   # b = avg_win / avg_loss (e.g. 2.1)
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        Kelly Fraction: f* = (b * p - q) / b
        Where:
            p = win rate
            q = 1 - p
            b = payoff ratio
        """
        p = max(0.01, min(0.99, win_rate))
        q = 1.0 - p
        b = max(0.1, payoff_ratio)

        # Raw Full Kelly
        full_kelly = (b * p - q) / b

        # If negative expectancy, full kelly <= 0
        if full_kelly <= 0:
            return {
                "full_kelly": 0.0,
                "fractional_kelly": 0.0,
                "recommended_risk_pct": 0.0,
                "expectancy_r": round((p * b) - q, 3),
                "is_positive_expectancy": False
            }

        # Apply safety fraction multiplier (e.g. 0.15 = 15% Kelly)
        fractional_kelly = full_kelly * self.fraction_multiplier
        
        # Penalize low sample size
        sample_penalty = min(1.0, sample_size / 80.0) if sample_size < 80 else 1.0
        adjusted_fraction = fractional_kelly * sample_penalty

        # Hard risk cap (e.g. 0.50% account equity)
        recommended_risk = min(self.max_risk_cap, max(0.001, adjusted_fraction))

        expectancy_r = (p * b) - q

        return {
            "full_kelly": round(full_kelly, 4),
            "fractional_kelly": round(fractional_kelly, 4),
            "recommended_risk_pct": round(recommended_risk, 4),
            "expectancy_r": round(expectancy_r, 3),
            "is_positive_expectancy": expectancy_r > 0
        }
