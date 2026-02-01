# src/kbot/strategy/volume_channel_engine.py
# =============================================================================
# Volume Channel Flow Engine
# Basierend auf dem Pine Script "Volume Channel Flow [ChartPrime]"
# =============================================================================

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, List


@dataclass
class VolumeProfileData:
    """Volume Profile Daten für ein Kanal-Segment."""
    poc: float           # Point of Control (Preis mit höchstem Volumen)
    poc_volume: float    # Volumen am POC
    value_area_high: float
    value_area_low: float
    total_volume: float
    delta: float         # Volume Delta (Kauf - Verkauf)
    is_bullish: bool     # Delta > 0


@dataclass
class ChannelState:
    """Aktueller Zustand des Volume Channel."""
    top: float
    bot: float
    avg: float
    trend: bool          # True = Bullish, False = Bearish
    count: int           # Anzahl Kerzen im aktuellen Kanal
    start_idx: int       # Start-Index des aktuellen Kanals
    volume_profile: Optional[VolumeProfileData]


class VolumeChannelEngine:
    """
    Volume Channel Flow Engine
    
    Berechnet einen ATR-basierten dynamischen Kanal mit integriertem
    Volume Profile und Volume Delta für Trade-Signale.
    
    Strategie:
    - Kanal basiert auf ATR * width um HL2 (Typical Price)
    - Breakout über Kanal = LONG Signal
    - Breakout unter Kanal = SHORT Signal
    - Volume Delta bestätigt Richtung
    - POC dient als wichtiges Support/Resistance Level
    """
    
    def __init__(self, settings: dict = None):
        """
        Args:
            settings: Dictionary mit Konfiguration
                - atr_period: ATR Periode (Standard: 200)
                - channel_width: Kanal-Breite Multiplikator (Standard: 3.0)
                - min_channel_length: Mindestlänge für VP Berechnung (Standard: 10)
                - volume_bins: Anzahl Bins für VP (Standard: 30)
        """
        settings = settings or {}
        self.atr_period = settings.get('atr_period', 200)
        self.channel_width = settings.get('channel_width', 3.0)
        self.min_channel_length = settings.get('min_channel_length', 10)
        self.volume_bins = settings.get('volume_bins', 30)
    
    def calculate_atr(self, df: pd.DataFrame, period: int = None) -> pd.Series:
        """Berechnet ATR (Average True Range)."""
        period = period or self.atr_period
        
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = abs(high - close)
        tr3 = abs(low - close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr
    
    def calculate_volume_profile(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> Optional[VolumeProfileData]:
        """
        Berechnet Volume Profile für ein Kanal-Segment.
        
        Args:
            df: OHLCV DataFrame
            start_idx: Start-Index des Segments
            end_idx: End-Index des Segments
        
        Returns:
            VolumeProfileData oder None
        """
        if end_idx - start_idx < self.min_channel_length:
            return None
        
        segment = df.iloc[start_idx:end_idx]
        if len(segment) == 0:
            return None
        
        top = segment['high'].max()
        bot = segment['low'].min()
        
        if top <= bot:
            return None
        
        step = (top - bot) / self.volume_bins
        volumes = np.zeros(self.volume_bins)
        deltas = np.zeros(self.volume_bins)
        
        for _, row in segment.iterrows():
            close = row['close']
            open_price = row['open']
            vol = row['volume']
            
            # Finde den Bin für diesen Close
            for i in range(self.volume_bins):
                mid = bot + step * i + step / 2
                if abs(close - mid) <= step:
                    volumes[i] += vol
                    # Delta: positiv wenn bullish (close > open), negativ wenn bearish
                    deltas[i] += vol if close > open_price else -vol
                    break
        
        # POC finden (Bin mit höchstem Volumen)
        poc_idx = int(np.argmax(volumes))
        poc = bot + step * poc_idx + step / 2
        poc_volume = volumes[poc_idx]
        
        # Value Area (70% des Volumens um POC)
        total_volume = volumes.sum()
        if total_volume == 0:
            return None
        
        va_target = total_volume * 0.7
        va_volume = volumes[poc_idx]
        va_low_idx = poc_idx
        va_high_idx = poc_idx
        
        while va_volume < va_target:
            low_vol = volumes[va_low_idx - 1] if va_low_idx > 0 else 0
            high_vol = volumes[va_high_idx + 1] if va_high_idx < self.volume_bins - 1 else 0
            
            if low_vol == 0 and high_vol == 0:
                break
            
            if high_vol >= low_vol and va_high_idx < self.volume_bins - 1:
                va_high_idx += 1
                va_volume += high_vol
            elif va_low_idx > 0:
                va_low_idx -= 1
                va_volume += low_vol
            else:
                break
        
        val = bot + step * va_low_idx
        vah = bot + step * (va_high_idx + 1)
        
        # Gesamtes Delta
        total_delta = deltas.sum()
        is_bullish = total_delta > 0
        
        return VolumeProfileData(
            poc=poc,
            poc_volume=poc_volume,
            value_area_high=vah,
            value_area_low=val,
            total_volume=total_volume,
            delta=total_delta,
            is_bullish=is_bullish
        )
    
    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Verarbeitet den DataFrame und fügt Channel-Indikatoren hinzu.
        
        Returns:
            DataFrame mit zusätzlichen Spalten:
            - channel_top: Obere Kanalgrenze
            - channel_bot: Untere Kanalgrenze
            - channel_avg: Kanal-Mittellinie
            - channel_trend: 1 = Bullish, -1 = Bearish, 0 = Neutral
            - breakout_signal: 1 = Long Breakout, -1 = Short Breakout, 0 = Kein Signal
            - volume_delta: Kumuliertes Volume Delta
            - poc: Point of Control des aktuellen Segments
        """
        df = df.copy()
        
        # ATR berechnen
        atr = self.calculate_atr(df)
        
        # Initialisiere Spalten
        df['channel_top'] = np.nan
        df['channel_bot'] = np.nan
        df['channel_avg'] = np.nan
        df['channel_trend'] = 0
        df['breakout_signal'] = 0
        df['volume_delta'] = 0.0
        df['poc'] = np.nan
        
        # Channel Berechnung
        start_idx = self.atr_period + 1
        if len(df) <= start_idx:
            return df
        
        # Initialer Kanal
        hl2 = (df['high'].iloc[start_idx] + df['low'].iloc[start_idx]) / 2
        current_atr = atr.iloc[start_idx] * self.channel_width
        
        top = hl2 + current_atr
        bot = hl2 - current_atr
        trend = None
        channel_start = start_idx
        
        for i in range(start_idx, len(df)):
            close = df['close'].iloc[i]
            hl2_i = (df['high'].iloc[i] + df['low'].iloc[i]) / 2
            atr_i = atr.iloc[i] * self.channel_width
            
            prev_avg = (top + bot) / 2
            
            # Breakout Detection
            if close > top:
                # Bullish Breakout - neuer Kanal
                df.loc[df.index[i], 'breakout_signal'] = 1
                
                # Volume Profile für abgeschlossenes Segment berechnen
                if i - channel_start >= self.min_channel_length:
                    vp = self.calculate_volume_profile(df, channel_start, i)
                    if vp:
                        df.loc[df.index[i], 'volume_delta'] = vp.delta
                
                # Neuer Kanal
                top = hl2_i + atr_i
                bot = hl2_i - atr_i
                trend = True
                channel_start = i
                
            elif close < bot:
                # Bearish Breakout - neuer Kanal
                df.loc[df.index[i], 'breakout_signal'] = -1
                
                # Volume Profile für abgeschlossenes Segment berechnen
                if i - channel_start >= self.min_channel_length:
                    vp = self.calculate_volume_profile(df, channel_start, i)
                    if vp:
                        df.loc[df.index[i], 'volume_delta'] = vp.delta
                
                # Neuer Kanal
                top = hl2_i + atr_i
                bot = hl2_i - atr_i
                trend = False
                channel_start = i
            
            # Werte setzen
            df.loc[df.index[i], 'channel_top'] = top
            df.loc[df.index[i], 'channel_bot'] = bot
            df.loc[df.index[i], 'channel_avg'] = (top + bot) / 2
            
            if trend is True:
                df.loc[df.index[i], 'channel_trend'] = 1
            elif trend is False:
                df.loc[df.index[i], 'channel_trend'] = -1
        
        # POC für aktuelles Segment berechnen
        if len(df) > channel_start + self.min_channel_length:
            vp = self.calculate_volume_profile(df, channel_start, len(df))
            if vp:
                for i in range(channel_start, len(df)):
                    df.loc[df.index[i], 'poc'] = vp.poc
        
        return df
    
    def get_signal(self, df: pd.DataFrame, use_volume_confirmation: bool = True) -> Tuple[Optional[str], str]:
        """
        Ermittelt das aktuelle Trading-Signal.
        
        Args:
            df: Verarbeiteter DataFrame
            use_volume_confirmation: Ob Volume Delta zur Bestätigung genutzt werden soll
        
        Returns:
            Tuple: (signal, reason)
            signal: 'long', 'short', oder None
            reason: Begründung für das Signal
        """
        if len(df) < 2:
            return None, "Nicht genug Daten"
        
        # Letzte abgeschlossene Kerze
        current = df.iloc[-2]
        
        breakout = current['breakout_signal']
        trend = current['channel_trend']
        delta = current['volume_delta']
        
        if breakout == 0:
            return None, "Kein Breakout-Signal"
        
        if breakout == 1:
            # Long Breakout
            if use_volume_confirmation and delta < 0:
                return None, f"Long Breakout abgelehnt: Volume Delta negativ ({delta:.0f})"
            
            return 'long', f"LONG: Breakout über Kanal, Trend bullish, Delta={delta:.0f}"
        
        elif breakout == -1:
            # Short Breakout
            if use_volume_confirmation and delta > 0:
                return None, f"Short Breakout abgelehnt: Volume Delta positiv ({delta:.0f})"
            
            return 'short', f"SHORT: Breakout unter Kanal, Trend bearish, Delta={delta:.0f}"
        
        return None, "Kein Signal"
    
    def get_stop_loss_take_profit(self, df: pd.DataFrame, side: str, 
                                   risk_reward: float = 2.0) -> Tuple[float, float]:
        """
        Berechnet Stop-Loss und Take-Profit basierend auf Kanal.
        
        Args:
            df: Verarbeiteter DataFrame
            side: 'long' oder 'short'
            risk_reward: Risk-Reward Verhältnis (Standard: 2.0)
        
        Returns:
            Tuple: (stop_loss, take_profit)
        """
        current = df.iloc[-1]
        entry = current['close']
        top = current['channel_top']
        bot = current['channel_bot']
        poc = current['poc'] if not pd.isna(current['poc']) else (top + bot) / 2
        
        if side == 'long':
            # SL unter dem Kanal-Boden
            stop_loss = bot
            sl_distance = entry - stop_loss
            take_profit = entry + (sl_distance * risk_reward)
        else:
            # SL über dem Kanal-Top
            stop_loss = top
            sl_distance = stop_loss - entry
            take_profit = entry - (sl_distance * risk_reward)
        
        return stop_loss, take_profit
    
    def get_channel_state(self, df: pd.DataFrame) -> Optional[ChannelState]:
        """Gibt den aktuellen Kanal-Zustand zurück."""
        if len(df) < self.atr_period + 2:
            return None
        
        current = df.iloc[-1]
        
        return ChannelState(
            top=current['channel_top'],
            bot=current['channel_bot'],
            avg=current['channel_avg'],
            trend=current['channel_trend'] == 1,
            count=0,  # TODO: Track count
            start_idx=0,
            volume_profile=None
        )
