from datetime import datetime, timezone
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

def current_utc() -> datetime:
    return datetime.now(timezone.utc)

class Agent1Signal(BaseModel):
    agent: Literal["orderflow"] = "orderflow"
    symbol: str
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    score: float = Field(ge=0.0, le=100.0)
    regime: str
    delta: float
    cvd_direction: Literal["UP", "DOWN", "FLAT", "BULLISH_DIV", "BEARISH_DIV"]
    orderbook_bias: Literal["BID", "ASK", "BALANCED"]
    liquidity_bias: Literal["SUPPORT", "RESISTANCE", "NEUTRAL"]
    gex_status: Literal["VERIFIED", "ESTIMATED", "UNAVAILABLE"]
    details: Dict[str, Any] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=current_utc)

class Agent2Signal(BaseModel):
    agent: Literal["technical_smc"] = "technical_smc"
    symbol: str
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    score: float = Field(ge=0.0, le=100.0)
    trend: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    structure: Literal["BOS", "CHoCH", "CONSOLIDATION", "RETEST"]
    liquidity_sweep: bool = False
    fvg: bool = False
    order_block: bool = False
    vwap: Literal["ABOVE", "BELOW", "AT_VWAP"]
    volume_profile: Literal["SUPPORT", "RESISTANCE", "VALUE_AREA_INSIDE"]
    kelly_fraction: float = Field(ge=0.0, le=1.0)
    details: Dict[str, Any] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=current_utc)

class Agent3Decision(BaseModel):
    decision: Literal["BUY", "SELL", "NO_TRADE"]
    symbol: str
    direction: Literal["LONG", "SHORT", "NEUTRAL"]
    confidence: float = Field(ge=0.0, le=100.0)
    risk_allowed: bool
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    position_size: float
    notional_usd: float
    agent1_score: float
    agent2_score: float
    market_regime: str
    liquidity_target: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    risk_violations: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=current_utc)

class TradeRecord(BaseModel):
    trade_id: str
    symbol: str
    setup: str
    direction: Literal["LONG", "SHORT"]
    entry_time: datetime
    exit_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    quantity: float
    notional_usd: float
    realized_pnl: float = 0.0
    realized_r: float = 0.0
    commission_usd: float = 0.0
    slippage_usd: float = 0.0
    agent1_score: float
    agent2_score: float
    fused_confidence: float
    market_regime: str
    exit_reason: Optional[str] = None
    status: Literal["OPEN", "CLOSED", "CANCELED"] = "OPEN"
    timestamp: datetime = Field(default_factory=current_utc)
