import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "scalper.db"

class DatabaseManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Trades Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                setup TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                duration_seconds REAL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                quantity REAL NOT NULL,
                notional_usd REAL NOT NULL,
                realized_pnl REAL DEFAULT 0.0,
                realized_r REAL DEFAULT 0.0,
                commission_usd REAL DEFAULT 0.0,
                slippage_usd REAL DEFAULT 0.0,
                agent1_score REAL,
                agent2_score REAL,
                fused_confidence REAL,
                market_regime TEXT,
                exit_reason TEXT,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT NOT NULL
            )
            """)

            # Signals Log Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                score REAL NOT NULL,
                regime TEXT,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """)

            # Strategy Knowledge Matrix Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_memory (
                setup_id TEXT NOT NULL,
                market_regime TEXT NOT NULL,
                sample_size INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0.0,
                payoff_ratio REAL DEFAULT 0.0,
                expectancy_r REAL DEFAULT 0.0,
                profit_factor REAL DEFAULT 0.0,
                max_drawdown_pct REAL DEFAULT 0.0,
                status TEXT DEFAULT 'INCUBATING',
                last_updated TEXT NOT NULL,
                PRIMARY KEY (setup_id, market_regime)
            )
            """)

            conn.commit()

    def record_trade(self, trade_dict: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO trades (
                trade_id, symbol, setup, direction, entry_time, exit_time,
                duration_seconds, entry_price, exit_price, stop_loss, take_profit,
                quantity, notional_usd, realized_pnl, realized_r, commission_usd,
                slippage_usd, agent1_score, agent2_score, fused_confidence,
                market_regime, exit_reason, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_dict.get("trade_id"),
                trade_dict.get("symbol"),
                trade_dict.get("setup", "DEFAULT_SCALP"),
                trade_dict.get("direction"),
                trade_dict.get("entry_time"),
                trade_dict.get("exit_time"),
                trade_dict.get("duration_seconds", 0.0),
                trade_dict.get("entry_price"),
                trade_dict.get("exit_price"),
                trade_dict.get("stop_loss"),
                trade_dict.get("take_profit"),
                trade_dict.get("quantity"),
                trade_dict.get("notional_usd"),
                trade_dict.get("realized_pnl", 0.0),
                trade_dict.get("realized_r", 0.0),
                trade_dict.get("commission_usd", 0.0),
                trade_dict.get("slippage_usd", 0.0),
                trade_dict.get("agent1_score", 0.0),
                trade_dict.get("agent2_score", 0.0),
                trade_dict.get("fused_confidence", 0.0),
                trade_dict.get("market_regime", "UNKNOWN"),
                trade_dict.get("exit_reason"),
                trade_dict.get("status", "OPEN"),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()

    def get_recent_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def log_signal(self, agent: str, symbol: str, direction: str, score: float, regime: str, payload: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO signals_log (agent, symbol, direction, score, regime, raw_payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                agent, symbol, direction, score, regime,
                json.dumps(payload, default=str),
                datetime.now(timezone.utc).isoformat()
            ))
            conn.commit()
