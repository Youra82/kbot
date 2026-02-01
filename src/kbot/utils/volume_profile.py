# src/kbot/utils/volume_profile.py
# Volume Profile Analyse für KBot
# Basierend auf dem TradingView Volume Profile Indicator

import pandas as pd
import numpy as np


def calculate_volume_profile(df: pd.DataFrame, lookback: int = 200, num_bins: int = 50) -> dict:
    """
    Berechnet das Volume Profile für die letzten 'lookback' Kerzen.
    
    Args:
        df: OHLCV DataFrame mit Spalten: open, high, low, close, volume
        lookback: Anzahl der Kerzen für die Berechnung (Standard: 200)
        num_bins: Anzahl der Preis-Bins für das Volumen-Histogramm (Standard: 50)
    
    Returns:
        Dictionary mit:
        - poc: Point of Control (Preis mit höchstem Volumen)
        - vah: Value Area High (obere Grenze der 68% Volumen-Zone)
        - val: Value Area Low (untere Grenze der 68% Volumen-Zone)
        - volumes: Array mit Volumen pro Preis-Level
        - price_levels: Array mit Preis-Levels
    """
    # Letzte 'lookback' Kerzen verwenden
    data = df.tail(lookback).copy()
    
    if len(data) < 10:
        return {
            'poc': df['close'].iloc[-1] if len(df) > 0 else 0,
            'vah': df['close'].iloc[-1] if len(df) > 0 else 0,
            'val': df['close'].iloc[-1] if len(df) > 0 else 0,
            'volumes': [],
            'price_levels': []
        }
    
    # Höchster und niedrigster Preis im Lookback
    highest_price = data['high'].max()
    lowest_price = data['low'].min()
    
    # Preis-Intervall pro Bin
    price_range = highest_price - lowest_price
    if price_range == 0:
        price_range = 0.01  # Fallback für flache Märkte
    
    price_interval = price_range / (num_bins - 1)
    
    # Preis-Levels erstellen
    price_levels = [lowest_price + (i * price_interval) for i in range(num_bins)]
    
    # Volumen pro Preis-Level berechnen
    volumes = [0.0] * num_bins
    
    for idx, row in data.iterrows():
        candle_low = row['low']
        candle_high = row['high']
        candle_volume = row['volume']
        
        # Verteile Volumen auf alle Preis-Levels, die die Kerze berührt
        for i, price_level in enumerate(price_levels):
            if candle_low <= price_level <= candle_high:
                volumes[i] += candle_volume
    
    # Point of Control (PoC) - Preis mit höchstem Volumen
    max_volume_idx = volumes.index(max(volumes)) if volumes else 0
    poc = price_levels[max_volume_idx] if price_levels else data['close'].iloc[-1]
    
    # Value Area Berechnung (68% des Gesamtvolumens)
    total_volume = sum(volumes)
    va_target = total_volume * 0.68  # 68% Value Area
    
    # Starte beim PoC und expandiere nach oben und unten
    va_sum = volumes[max_volume_idx] if volumes else 0
    va_up_idx = max_volume_idx
    va_dn_idx = max_volume_idx
    
    while va_sum < va_target:
        # Volumen oben und unten vom aktuellen Bereich
        vol_up = volumes[va_up_idx + 1] if va_up_idx < num_bins - 1 else 0
        vol_dn = volumes[va_dn_idx - 1] if va_dn_idx > 0 else 0
        
        if vol_up == 0 and vol_dn == 0:
            break
        
        # Expandiere in Richtung des höheren Volumens
        if vol_up >= vol_dn:
            va_sum += vol_up
            va_up_idx += 1
        else:
            va_sum += vol_dn
            va_dn_idx -= 1
    
    # Value Area High & Low
    vah = price_levels[va_up_idx] if price_levels else poc
    val = price_levels[va_dn_idx] if price_levels else poc
    
    return {
        'poc': poc,
        'vah': vah,
        'val': val,
        'volumes': volumes,
        'price_levels': price_levels,
        'total_volume': total_volume
    }


def check_price_near_level(current_price: float, level: float, tolerance_pct: float = 0.5) -> bool:
    """
    Prüft ob der aktuelle Preis nahe an einem Level ist.
    
    Args:
        current_price: Aktueller Preis
        level: Volume Profile Level (PoC, VAH, VAL)
        tolerance_pct: Toleranz in Prozent (Standard: 0.5%)
    
    Returns:
        True wenn Preis innerhalb der Toleranz liegt
    """
    tolerance = level * (tolerance_pct / 100)
    return abs(current_price - level) <= tolerance


def get_volume_profile_signal(df: pd.DataFrame, current_price: float, lookback: int = 200) -> dict:
    """
    Berechnet Volume Profile und gibt Trading-Signale zurück.
    
    Args:
        df: OHLCV DataFrame
        current_price: Aktueller Preis
        lookback: Lookback-Periode für Volume Profile
    
    Returns:
        Dictionary mit:
        - poc, vah, val: Volume Profile Levels
        - near_poc: True wenn Preis nahe PoC
        - near_vah: True wenn Preis nahe VAH (Short-Zone)
        - near_val: True wenn Preis nahe VAL (Long-Zone)
        - position_in_va: 'above', 'inside', 'below' Value Area
    """
    vp = calculate_volume_profile(df, lookback=lookback)
    
    poc = vp['poc']
    vah = vp['vah']
    val = vp['val']
    
    # Prüfe Nähe zu Levels (0.5% Toleranz)
    near_poc = check_price_near_level(current_price, poc, tolerance_pct=0.5)
    near_vah = check_price_near_level(current_price, vah, tolerance_pct=0.5)
    near_val = check_price_near_level(current_price, val, tolerance_pct=0.5)
    
    # Position relativ zur Value Area
    if current_price > vah:
        position_in_va = 'above'
    elif current_price < val:
        position_in_va = 'below'
    else:
        position_in_va = 'inside'
    
    return {
        'poc': poc,
        'vah': vah,
        'val': val,
        'near_poc': near_poc,
        'near_vah': near_vah,
        'near_val': near_val,
        'position_in_va': position_in_va
    }
