"""Engine wrapper for Peak/Trough strategy to provide compatibility with trade_manager.
This is a lightweight adapter that allows existing trade_manager to interact with
peak_trough logic (get_signal, get_stop_loss_take_profit, process_dataframe).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple
import pandas as pd
from .peak_trough import generate_signal


@dataclass
class ChannelState:
    bot: float
    top: float
    avg: float
    trend: int


class PeakTroughEngine:
    def __init__(self, settings: dict = None):
        self.settings = settings or {}

    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        # For compatibility, add placeholder channel columns
        if 'channel_top' not in df:
            df['channel_top'] = df['high'].rolling(3, min_periods=1).max()
        if 'channel_bot' not in df:
            df['channel_bot'] = df['low'].rolling(3, min_periods=1).min()
        if 'channel_avg' not in df:
            df['channel_avg'] = (df['channel_top'] + df['channel_bot'])/2
        # trend placeholder: 1/-1/0
        df['channel_trend'] = 0
        # breakout signal placeholder
        df['breakout_signal'] = None
        df['volume_delta'] = 0
        return df

    def get_signal(self, df: pd.DataFrame, use_volume_confirmation: bool = False) -> Tuple[str, str]:
        # Convert df to OHLCV list for generate_signal
        ohlcv = []
        for idx, row in df.iterrows():
            ohlcv.append((int(idx.timestamp()) if hasattr(idx, 'timestamp') else 0, float(row['open']), float(row['high']), float(row['low']), float(row['close']), float(row.get('volume',0))))
        sig = generate_signal(ohlcv, self.settings)
        if not sig:
            return None, 'Kein Signal'
        return sig['signal'], f"peak_trough {sig['meta']}"

    def get_stop_loss_take_profit(self, df: pd.DataFrame, side: str, risk_reward: float) -> Tuple[float,float]:
        # Use last close and ATR to compute stop/tp similar to peak_trough
        ohlcv = []
        for idx, row in df.iterrows():
            ohlcv.append((0, float(row['open']), float(row['high']), float(row['low']), float(row['close']), float(row.get('volume',0))))
        # call generate_signal to get stop/tp
        sig = generate_signal(ohlcv, self.settings)
        if not sig:
            # fallback: small SL/TP around last close
            last_close = float(df['close'].iloc[-1])
            sl = last_close - 0.01*last_close if side=='long' else last_close + 0.01*last_close
            tp = last_close + (last_close - sl) * risk_reward if side=='long' else last_close - (sl - last_close) * risk_reward
            return sl, tp
        return sig['stop'], sig['tp']

    def get_channel_state(self, df: pd.DataFrame) -> ChannelState:
        cur = df.iloc[-1]
        return ChannelState(bot=float(cur['channel_bot']), top=float(cur['channel_top']), avg=float(cur['channel_avg']), trend=int(cur.get('channel_trend',0)))
