from pathlib import Path
from typing import List, Optional
import os
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class TimeframesConfig(BaseModel):
    macro: str = "1D"
    major_structure: str = "4H"
    directional_bias: str = "1H"
    setup: str = "15M"
    entry_refinement: str = "5M"
    micro_execution: str = "1M"

class Agent1Weights(BaseModel):
    orderbook_imbalance: float = 20.0
    timesales_velocity: float = 20.0
    cvd_divergence: float = 20.0
    footprint_imbalance: float = 15.0
    liquidity_heatmap: float = 15.0
    regime_alignment: float = 10.0

class Agent1Config(BaseModel):
    weights: Agent1Weights = Field(default_factory=Agent1Weights)
    min_orderbook_depth_levels: int = 20
    imbalance_ratio_trigger: float = 0.25
    absorption_volume_multiple: float = 2.5
    cvd_divergence_lookback_bars: int = 20
    gex_weight_multiplier: float = 1.0

class Agent2Weights(BaseModel):
    smc_structure: float = 20.0
    liquidity_sweeps: float = 15.0
    mtf_trend_alignment: float = 15.0
    volume_profile: float = 10.0
    market_profile: float = 10.0
    vwap_position: float = 10.0
    momentum_rsi_macd: float = 10.0
    volatility_regime: float = 10.0

class Agent2Indicators(BaseModel):
    ema_fast: int = 20
    ema_mid: int = 50
    ema_slow: int = 200
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_period: int = 14
    adx_threshold: float = 22.0
    volume_profile_bins: int = 50
    value_area_pct: float = 0.70

class Agent2Config(BaseModel):
    weights: Agent2Weights = Field(default_factory=Agent2Weights)
    indicators: Agent2Indicators = Field(default_factory=Agent2Indicators)

class Agent3Weights(BaseModel):
    agent1_weight: float = 0.35
    agent2_weight: float = 0.35
    regime_confirmation: float = 0.10
    risk_reward_quality: float = 0.10
    execution_quality: float = 0.10

class Agent3Config(BaseModel):
    weights: Agent3Weights = Field(default_factory=Agent3Weights)
    min_agent1_score: float = 80.0
    min_agent2_score: float = 80.0
    composite_confidence_threshold: float = 85.0
    min_risk_reward: float = 2.0
    tp1_ratio: float = 1.5
    tp2_ratio: float = 2.5
    partial_take_profit_pct: float = 0.50
    trailing_stop_activation_r: float = 1.2

class RiskLimits(BaseModel):
    max_risk_per_trade_pct: float = 0.005
    min_risk_per_trade_pct: float = 0.001
    max_daily_loss_pct: float = 0.015
    max_weekly_loss_pct: float = 0.040
    max_open_positions: int = 2
    max_correlated_exposure_pct: float = 0.010
    max_leverage: float = 3.0
    max_slippage_bps: float = 5.0
    max_spread_bps: float = 4.0
    max_position_size_usd: float = 50000.0

class KellyConfig(BaseModel):
    fraction_multiplier: float = 0.15
    min_sample_size: int = 50
    default_win_rate: float = 0.58
    default_payoff_ratio: float = 2.1

class CooldownConfig(BaseModel):
    normal_trade_cooldown_sec: int = 180
    two_consecutive_losses_risk_reduction: float = 0.50
    three_consecutive_losses_pause_sec: int = 3600
    four_consecutive_losses_kill_switch: bool = True

class EmergencyConfig(BaseModel):
    stale_data_timeout_ms: int = 2000
    max_unrealized_drawdown_pct: float = 0.030
    abnormal_volatility_atr_multiple: float = 3.5
    order_rejection_limit_per_hour: int = 3

class SymbolConfig(BaseModel):
    symbol: str
    base_asset: str = "BTC"
    quote_asset: str = "USDT"
    tick_size: float = 0.10
    step_size: float = 0.001
    min_notional: float = 10.0
    max_leverage: int = 20
    is_active: bool = True
    priority: int = 1

class SystemSettings(BaseModel):
    trading_mode: str = os.getenv("TRADING_MODE", "PAPER")
    exchange_name: str = os.getenv("EXCHANGE_NAME", "binance")
    exchange_api_key: str = os.getenv("EXCHANGE_API_KEY", "")
    exchange_api_secret: str = os.getenv("EXCHANGE_API_SECRET", "")
    exchange_api_passphrase: Optional[str] = os.getenv("EXCHANGE_API_PASSPHRASE", None)
    withdrawals_disabled: bool = os.getenv("WITHDRAWALS_DISABLED", "true").lower() == "true"
    read_only_mode: bool = os.getenv("READ_ONLY_MODE", "false").lower() == "true"
    
    initial_capital: float = float(os.getenv("INITIAL_CAPITAL", "10000.0"))
    account_currency: str = os.getenv("ACCOUNT_CURRENCY", "USDT")
    
    timeframes: TimeframesConfig = Field(default_factory=TimeframesConfig)
    agent1: Agent1Config = Field(default_factory=Agent1Config)
    agent2: Agent2Config = Field(default_factory=Agent2Config)
    agent3: Agent3Config = Field(default_factory=Agent3Config)
    risk_limits: RiskLimits = Field(default_factory=RiskLimits)
    kelly: KellyConfig = Field(default_factory=KellyConfig)
    cooldown: CooldownConfig = Field(default_factory=CooldownConfig)
    emergency: EmergencyConfig = Field(default_factory=EmergencyConfig)
    active_symbols: List[SymbolConfig] = Field(default_factory=list)

def load_settings() -> SystemSettings:
    settings = SystemSettings()
    
    strat_path = BASE_DIR / "config" / "strategy.yaml"
    if strat_path.exists():
        with open(strat_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if "timeframes" in data:
                settings.timeframes = TimeframesConfig(**data["timeframes"])
            if "agent1_orderflow" in data:
                settings.agent1 = Agent1Config(**data["agent1_orderflow"])
            if "agent2_technical_smc" in data:
                settings.agent2 = Agent2Config(**data["agent2_technical_smc"])
            if "agent3_decision" in data:
                settings.agent3 = Agent3Config(**data["agent3_decision"])
                
    risk_path = BASE_DIR / "config" / "risk.yaml"
    if risk_path.exists():
        with open(risk_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if "limits" in data:
                settings.risk_limits = RiskLimits(**data["limits"])
            if "kelly" in data:
                settings.kelly = KellyConfig(**data["kelly"])
            if "cooldown" in data:
                settings.cooldown = CooldownConfig(**data["cooldown"])
            if "emergency_triggers" in data:
                settings.emergency = EmergencyConfig(**data["emergency_triggers"])
                
    sym_path = BASE_DIR / "config" / "symbols.yaml"
    if sym_path.exists():
        with open(sym_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            if "active_symbols" in data:
                settings.active_symbols = [SymbolConfig(**s) for s in data["active_symbols"]]
                
    return settings
