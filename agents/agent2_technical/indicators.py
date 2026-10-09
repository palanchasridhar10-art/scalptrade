from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

class TechnicalIndicators:
    @staticmethod
    def calculate_ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0.0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def calculate_stoch_rsi(rsi_series: pd.Series, period: int = 14, k_period: int = 3, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        min_rsi = rsi_series.rolling(window=period).min()
        max_rsi = rsi_series.rolling(window=period).max()
        stoch_rsi = (rsi_series - min_rsi) / (max_rsi - min_rsi + 1e-9) * 100.0
        k = stoch_rsi.rolling(window=k_period).mean()
        d = k.rolling(window=d_period).mean()
        return k, d

    @staticmethod
    def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        hist = macd - macd_signal
        return macd, macd_signal, hist

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        atr = TechnicalIndicators.calculate_atr(df, period)
        plus_di = 100.0 * (pd.Series(plus_dm, index=df.index).rolling(window=period).mean() / (atr + 1e-9))
        minus_di = 100.0 * (pd.Series(minus_dm, index=df.index).rolling(window=period).mean() / (atr + 1e-9))
        
        dx = 100.0 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9))
        adx = dx.rolling(window=period).mean()
        return adx

    def analyze_all(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty or len(df) < 20:
            return {"valid": False}

        close = df["close"]
        ema20 = self.calculate_ema(close, 20).iloc[-1]
        ema50 = self.calculate_ema(close, 50).iloc[-1]
        ema200 = self.calculate_ema(close, min(200, len(df))).iloc[-1]
        
        rsi_series = self.calculate_rsi(close, 14)
        rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0
        
        k, d = self.calculate_stoch_rsi(rsi_series, 14, 3, 3)
        stoch_k = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50.0
        stoch_d = float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 50.0
        
        macd, macd_sig, hist = self.calculate_macd(close, 12, 26, 9)
        macd_val = float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0.0
        macd_hist = float(hist.iloc[-1]) if not pd.isna(hist.iloc[-1]) else 0.0
        
        atr_series = self.calculate_atr(df, 14)
        atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 0.0
        
        adx_series = self.calculate_adx(df, 14)
        adx = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else 20.0
        
        bb_up, bb_mid, bb_low = self.calculate_bollinger_bands(close, 20, 2.0)
        
        cur_price = float(close.iloc[-1])
        trend_score = 0
        if cur_price > ema20 > ema50:
            trend_score = 1  # Bullish
        elif cur_price < ema20 < ema50:
            trend_score = -1 # Bearish

        return {
            "valid": True,
            "current_price": cur_price,
            "ema20": round(float(ema20), 2),
            "ema50": round(float(ema50), 2),
            "ema200": round(float(ema200), 2),
            "rsi": round(rsi, 2),
            "stoch_k": round(stoch_k, 2),
            "stoch_d": round(stoch_d, 2),
            "macd": round(macd_val, 4),
            "macd_hist": round(macd_hist, 4),
            "atr": round(atr, 2),
            "adx": round(adx, 2),
            "bb_upper": round(float(bb_up.iloc[-1]), 2),
            "bb_lower": round(float(bb_low.iloc[-1]), 2),
            "trend_score": trend_score
        }
