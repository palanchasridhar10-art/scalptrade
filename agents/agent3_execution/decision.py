from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from data.schemas.signals import Agent1Signal, Agent2Signal
from config.settings import Agent3Config

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class DecisionFusionEngine:
    def __init__(self, config: Optional[Agent3Config] = None):
        self.config = config or Agent3Config()

    def fuse(
        self,
        agent1: Agent1Signal,
        agent2: Agent2Signal,
        spread_bps: float,
        data_is_fresh: bool = True
    ) -> Dict[str, Any]:
        """
        Fuses Agent 1 (Microstructure) and Agent 2 (Technical/SMC) signals.
        Returns agreement status, candidate direction, and composite confidence score.
        """
        reasons: List[str] = []
        violations: List[str] = []

        # Freshness check
        if not data_is_fresh:
            violations.append("Market data is stale (> 2000ms SLA)")
            return {
                "allowed": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "reasons": reasons,
                "violations": violations
            }

        # 1. Consensus check: Agent 1 and Agent 2 MUST agree on direction
        if agent1.direction == "NEUTRAL" or agent2.direction == "NEUTRAL":
            violations.append("One or both agents emitted NEUTRAL signal")
            return {
                "allowed": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "reasons": reasons,
                "violations": violations
            }

        if agent1.direction != agent2.direction:
            violations.append(f"Agent disagreement: Agent 1 is {agent1.direction}, Agent 2 is {agent2.direction}")
            return {
                "allowed": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "reasons": reasons,
                "violations": violations
            }

        # 2. Score threshold check (both >= 80)
        if agent1.score < self.config.min_agent1_score:
            violations.append(f"Agent 1 score ({agent1.score:.1f}) below threshold ({self.config.min_agent1_score:.1f})")
        if agent2.score < self.config.min_agent2_score:
            violations.append(f"Agent 2 score ({agent2.score:.1f}) below threshold ({self.config.min_agent2_score:.1f})")

        if violations:
            return {
                "allowed": False,
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "reasons": reasons,
                "violations": violations
            }

        # 3. Calculate Composite Confidence Score
        # Confidence = 0.35*S1 + 0.35*S2 + 0.10*Regime + 0.10*RR + 0.10*Execution
        weights = self.config.weights
        s1_part = (agent1.score / 100.0) * weights.agent1_weight
        s2_part = (agent2.score / 100.0) * weights.agent2_weight

        # Regime confirmation
        regime_score = 1.0 if agent1.regime in ["TREND_UP", "TREND_DOWN", "BREAKOUT"] else 0.7
        regime_part = regime_score * weights.regime_confirmation

        # Spread / Execution quality
        exec_score = 1.0 if spread_bps <= 2.0 else (0.8 if spread_bps <= 4.0 else 0.4)
        exec_part = exec_score * weights.execution_quality

        # Risk/Reward factor (estimated prior to sizing)
        rr_part = 1.0 * weights.risk_reward_quality

        total_confidence = (s1_part + s2_part + regime_part + exec_part + rr_part) * 100.0
        total_confidence = round(min(99.0, max(0.0, total_confidence)), 1)

        # 4. Check confidence against composite threshold (e.g. 85.0)
        if total_confidence < self.config.composite_confidence_threshold:
            violations.append(f"Composite confidence ({total_confidence:.1f}) below required threshold ({self.config.composite_confidence_threshold:.1f})")
            return {
                "allowed": False,
                "direction": "NEUTRAL",
                "confidence": total_confidence,
                "reasons": reasons,
                "violations": violations
            }

        reasons.extend(agent1.reasons[:3])
        reasons.extend(agent2.reasons[:3])
        reasons.append(f"Strong agent consensus ({agent1.direction}) with confidence {total_confidence:.1f}%")

        return {
            "allowed": True,
            "direction": agent1.direction,
            "confidence": total_confidence,
            "reasons": reasons,
            "violations": violations
        }
