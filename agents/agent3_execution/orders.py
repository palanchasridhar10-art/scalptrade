from typing import Dict, Any, Optional
from data.schemas.signals import Agent1Signal, Agent2Signal

class TradeSetupBuilder:
    def __init__(self, min_risk_reward: float = 2.0, tp1_ratio: float = 1.5, tp2_ratio: float = 2.5):
        self.min_risk_reward = min_risk_reward
        self.tp1_ratio = tp1_ratio
        self.tp2_ratio = tp2_ratio

    def build_setup(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        agent1: Agent1Signal,
        agent2: Agent2Signal
    ) -> Dict[str, Any]:
        smc_details = agent2.details.get("smc", {})
        ind_details = agent2.details.get("indicators", {})
        atr = ind_details.get("atr", current_price * 0.003)

        # 1. Determine Entry
        entry = current_price

        # 2. Determine Stop Loss based on structural invalidation levels
        if direction == "LONG":
            swing_low = smc_details.get("nearest_swing_low", entry - atr * 1.5)
            ob_zone = smc_details.get("order_block_zone")
            fvg_zone = smc_details.get("fvg_zone")

            if ob_zone and ob_zone.get("type") == "BULLISH_OB":
                sl_candidate = ob_zone.get("low", entry - atr) - (atr * 0.2)
            elif fvg_zone and smc_details.get("fvg_direction") == "BULLISH_FVG":
                sl_candidate = fvg_zone.get("low", entry - atr) - (atr * 0.2)
            else:
                sl_candidate = min(swing_low, entry - (atr * 1.2))

            # Ensure minimum distance & safety buffer
            stop_loss = round(min(entry - (atr * 0.8), sl_candidate), 2)
            risk_dist = entry - stop_loss
            
            # Take Profits
            tp1 = round(entry + (risk_dist * self.tp1_ratio), 2)
            tp2 = round(entry + (risk_dist * self.tp2_ratio), 2)
            
            # Liquidity Target Check
            bsl = agent2.details.get("liquidity", {}).get("nearest_buy_side_liquidity")
            if bsl and bsl > entry:
                tp2 = max(tp2, bsl)
                
            reward_dist = tp2 - entry
            rr = reward_dist / risk_dist if risk_dist > 0 else 0.0

        else: # SHORT
            swing_high = smc_details.get("nearest_swing_high", entry + atr * 1.5)
            ob_zone = smc_details.get("order_block_zone")
            fvg_zone = smc_details.get("fvg_zone")

            if ob_zone and ob_zone.get("type") == "BEARISH_OB":
                sl_candidate = ob_zone.get("high", entry + atr) + (atr * 0.2)
            elif fvg_zone and smc_details.get("fvg_direction") == "BEARISH_FVG":
                sl_candidate = fvg_zone.get("high", entry + atr) + (atr * 0.2)
            else:
                sl_candidate = max(swing_high, entry + (atr * 1.2))

            stop_loss = round(max(entry + (atr * 0.8), sl_candidate), 2)
            risk_dist = stop_loss - entry
            
            tp1 = round(entry - (risk_dist * self.tp1_ratio), 2)
            tp2 = round(entry - (risk_dist * self.tp2_ratio), 2)

            ssl = agent2.details.get("liquidity", {}).get("nearest_sell_side_liquidity")
            if ssl and ssl < entry:
                tp2 = min(tp2, ssl)

            reward_dist = entry - tp2
            rr = reward_dist / risk_dist if risk_dist > 0 else 0.0

        valid_rr = rr >= self.min_risk_reward

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": round(entry, 2),
            "stop_loss": stop_loss,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "risk_reward": round(rr, 2),
            "valid_rr": valid_rr,
            "risk_distance": round(risk_dist, 2),
            "reward_distance": round(reward_dist, 2)
        }
