#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Fibonacci Bollinger Bands + Volume Profile Trading Bot

import sys
import argparse
import pandas as pd
import numpy as np
import datetime
import ccxt

# --- Hilfsfunktion: Kursdaten laden (Bitget via ccxt) ---
def load_ohlcv(symbol, start, end, timeframe):
    exchange = ccxt.bitget()
    # Bitget-Symbole sind z.B. BTC/USDT:USDT
    # Konvertiere Input (z.B. BTCUSDT oder BTC) zum richtigen Format
    if '/' not in symbol:
        # Entferne 'USDT' am Ende wenn vorhanden
        if symbol.upper().endswith('USDT'):
            symbol = symbol[:-4]
        symbol = symbol.upper() + '/USDT:USDT'
    elif not symbol.endswith(':USDT'):
        symbol = symbol + ':USDT'
    
    since = int(pd.Timestamp(start).timestamp() * 1000)
    end_ts = int(pd.Timestamp(end).timestamp() * 1000)
    tf_map = {'1d':'1d','4h':'4h','1h':'1h','6h':'6h','30m':'30m','15m':'15m','5m':'5m','10m':'10m','2h':'2h'}
    tf = tf_map.get(timeframe, '1d')
    
    # TitanBot's überlegene Logik: parse_timeframe() für korrekte Zeitberechnung
    timeframe_duration_in_ms = exchange.parse_timeframe(tf) * 1000
    
    all_ohlcv = []
    limit = 500
    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv += ohlcv
        last = ohlcv[-1][0]
        # Fix: Nutze parse_timeframe() statt +1ms (TitanBot's Method)
        since = last + timeframe_duration_in_ms
    if not all_ohlcv:
        raise Exception(f"Keine Daten von Bitget für {symbol} im Zeitraum {start} bis {end}")
    df = pd.DataFrame(all_ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    return df[['open','high','low','close','volume']]


# =============================================================================
# VOLUME PROFILE - Berechnung von PoC, VAH, VAL
# =============================================================================
def calculate_volume_profile(df, num_bars=50, va_percent=68):
    """
    Berechnet das Volume Profile für einen DataFrame.
    
    Args:
        df: OHLCV DataFrame
        num_bars: Anzahl der Preis-Level für das Profil
        va_percent: Prozentsatz für die Value Area (Standard: 68%)
    
    Returns:
        dict mit:
            - poc: Point of Control (Preis mit höchstem Volumen)
            - vah: Value Area High
            - val: Value Area Low
            - volumes: Array mit Volumen pro Level
            - price_levels: Array mit Preis-Levels
    """
    if len(df) < 10:
        return None
    
    price_min = df['low'].min()
    price_max = df['high'].max()
    price_range = price_max - price_min
    
    if price_range <= 0:
        return None
    
    interval = price_range / num_bars
    volumes = np.zeros(num_bars)
    
    # Berechne Volumen pro Preis-Level
    for i in range(len(df)):
        row_low = df['low'].iloc[i]
        row_high = df['high'].iloc[i]
        row_volume = df['volume'].iloc[i]
        
        # Verteile Volumen auf alle Levels, die von der Kerze berührt werden
        for j in range(num_bars):
            price_level = price_min + interval * j
            price_level_high = price_level + interval
            
            # Prüfe ob Level von Kerze berührt wird
            if row_low <= price_level_high and row_high >= price_level:
                # Anteil der Kerze, der dieses Level berührt
                overlap_low = max(row_low, price_level)
                overlap_high = min(row_high, price_level_high)
                candle_range = row_high - row_low if row_high > row_low else 1
                overlap_pct = (overlap_high - overlap_low) / candle_range
                volumes[j] += row_volume * max(0, overlap_pct)
    
    # Point of Control (PoC) - Level mit höchstem Volumen
    poc_idx = np.argmax(volumes)
    poc_price = price_min + interval * (poc_idx + 0.5)
    
    # Value Area Berechnung (68% des Volumens um PoC)
    total_vol = volumes.sum()
    if total_vol == 0:
        return None
    
    va_vol = total_vol * (va_percent / 100)
    va_up, va_dn = poc_idx, poc_idx
    va_sum = volumes[poc_idx]
    
    while va_sum < va_vol:
        v_up = volumes[va_up + 1] if va_up < num_bars - 1 else 0
        v_dn = volumes[va_dn - 1] if va_dn > 0 else 0
        
        if v_up == 0 and v_dn == 0:
            break
        
        if v_up >= v_dn and va_up < num_bars - 1:
            va_sum += v_up
            va_up += 1
        elif va_dn > 0:
            va_sum += v_dn
            va_dn -= 1
        else:
            break
    
    vah = price_min + interval * (va_up + 1)  # Value Area High
    val = price_min + interval * va_dn         # Value Area Low
    
    # Preis-Levels für Referenz
    price_levels = [price_min + interval * (i + 0.5) for i in range(num_bars)]
    
    return {
        'poc': poc_price,
        'vah': vah,
        'val': val,
        'volumes': volumes,
        'price_levels': np.array(price_levels),
        'price_min': price_min,
        'price_max': price_max,
        'interval': interval
    }


def get_volume_at_price(vp, price):
    """Gibt das relative Volumen an einem bestimmten Preis zurück (0-1)."""
    if vp is None:
        return 0.5
    
    # Finde das nächste Level
    idx = int((price - vp['price_min']) / vp['interval'])
    idx = max(0, min(idx, len(vp['volumes']) - 1))
    
    max_vol = vp['volumes'].max()
    if max_vol == 0:
        return 0.5
    
    return vp['volumes'][idx] / max_vol


def is_near_level(price, level, tolerance_pct=0.5):
    """Prüft ob ein Preis nahe an einem Level ist."""
    if level == 0:
        return False
    return abs(price - level) / level < (tolerance_pct / 100)


# =============================================================================
# FIBONACCI BOLLINGER BANDS
# =============================================================================
def fibonacci_bollinger_bands(df, length=200, mult=3.0):
    """
    Fibonacci Bollinger Bands Strategy:
    - VWMA als Basis
    - 6 Fibonacci-Level oben und unten (0.236, 0.382, 0.5, 0.618, 0.764, 1.0)
    
    Args:
        df: OHLC DataFrame
        length: VWMA-Periode (Standard: 200)
        mult: Standardabweichungs-Multiplikator (Standard: 3.0)
    
    Returns:
        DataFrame mit Bändern: upper_1-6, lower_1-6, basis
    """
    # Berechne VWMA (Volume Weighted Moving Average)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    vwma = (typical_price * df['volume']).rolling(window=length).sum() / df['volume'].rolling(window=length).sum()
    
    # Berechne Standardabweichung
    src = (df['high'] + df['low'] + df['close']) / 3  # hlc3
    stdev = src.rolling(window=length).std()
    
    # Basis und Deviation
    basis = vwma
    dev = mult * stdev
    
    # Fibonacci-Level
    fib_levels = [0.236, 0.382, 0.5, 0.618, 0.764, 1.0]
    
    bands = pd.DataFrame(index=df.index)
    bands['basis'] = basis
    bands['dev'] = dev
    
    for i, fib in enumerate(fib_levels, start=1):
        bands[f'upper_{i}'] = basis + (fib * dev)
        bands[f'lower_{i}'] = basis - (fib * dev)
    
    bands['type'] = 'fibonacci'
    
    return bands[['basis', 'dev', 'upper_1', 'upper_2', 'upper_3', 'upper_4', 'upper_5', 'upper_6',
                  'lower_1', 'lower_2', 'lower_3', 'lower_4', 'lower_5', 'lower_6', 'type']]


# =============================================================================
# KOMBINIERTE STRATEGIE: Fib BB + Volume Profile
# =============================================================================
def get_signal_strength(price, bands, vp, i):
    """
    Berechnet die Signalstärke basierend auf Fib BB + Volume Profile Konfluenz.
    
    Returns:
        tuple: (signal_type, strength, reason)
        - signal_type: 'STRONG_LONG', 'WEAK_LONG', 'STRONG_SHORT', 'WEAK_SHORT', 'NO_SIGNAL'
        - strength: 0.0 - 1.0
        - reason: Begründung für das Signal
    """
    if pd.isna(bands['basis'].iloc[i]) or vp is None:
        return ('NO_SIGNAL', 0.0, 'Keine Daten')
    
    lower_6 = bands['lower_6'].iloc[i]
    upper_6 = bands['upper_6'].iloc[i]
    lower_3 = bands['lower_3'].iloc[i]
    upper_3 = bands['upper_3'].iloc[i]
    
    poc = vp['poc']
    vah = vp['vah']
    val = vp['val']
    
    # Volumen an aktuellem Preis
    vol_at_price = get_volume_at_price(vp, price)
    
    # --- LONG SIGNALS ---
    if price <= lower_6:
        near_val = is_near_level(price, val, tolerance_pct=1.0)
        near_poc = is_near_level(price, poc, tolerance_pct=1.0)
        high_volume = vol_at_price > 0.5
        
        if (near_val or near_poc) and high_volume:
            return ('STRONG_LONG', 1.0, f'Fib lower_6 + VP Konfluenz (VAL/PoC) + High Vol')
        elif near_val or near_poc:
            return ('STRONG_LONG', 0.85, f'Fib lower_6 + VP Level (VAL/PoC)')
        elif high_volume:
            return ('WEAK_LONG', 0.6, f'Fib lower_6 + High Volume Zone')
        else:
            return ('WEAK_LONG', 0.4, f'Fib lower_6 ohne VP Bestätigung')
    
    # Entry bei lower_3 nur wenn starke VP Konfluenz
    elif price <= lower_3 and price > lower_6:
        near_val = is_near_level(price, val, tolerance_pct=0.5)
        near_poc = is_near_level(price, poc, tolerance_pct=0.5)
        
        if near_val or near_poc:
            return ('WEAK_LONG', 0.5, f'Fib lower_3 + starke VP Konfluenz')
    
    # --- SHORT SIGNALS ---
    elif price >= upper_6:
        near_vah = is_near_level(price, vah, tolerance_pct=1.0)
        near_poc = is_near_level(price, poc, tolerance_pct=1.0)
        high_volume = vol_at_price > 0.5
        
        if (near_vah or near_poc) and high_volume:
            return ('STRONG_SHORT', 1.0, f'Fib upper_6 + VP Konfluenz (VAH/PoC) + High Vol')
        elif near_vah or near_poc:
            return ('STRONG_SHORT', 0.85, f'Fib upper_6 + VP Level (VAH/PoC)')
        elif high_volume:
            return ('WEAK_SHORT', 0.6, f'Fib upper_6 + High Volume Zone')
        else:
            return ('WEAK_SHORT', 0.4, f'Fib upper_6 ohne VP Bestätigung')
    
    # Entry bei upper_3 nur wenn starke VP Konfluenz
    elif price >= upper_3 and price < upper_6:
        near_vah = is_near_level(price, vah, tolerance_pct=0.5)
        near_poc = is_near_level(price, poc, tolerance_pct=0.5)
        
        if near_vah or near_poc:
            return ('WEAK_SHORT', 0.5, f'Fib upper_3 + starke VP Konfluenz')
    
    return ('NO_SIGNAL', 0.0, 'Kein Signal')


# =============================================================================
# BACKTEST MIT VOLUME PROFILE INTEGRATION
# =============================================================================
def fib_vp_backtest(df, bands, vp, start_capital=1000, vp_lookback=200, 
                    require_vp_confluence=True, use_poc_tp=True):
    """
    Fibonacci Bollinger Bands + Volume Profile Backtest.
    
    Args:
        df: OHLC DataFrame
        bands: Fibonacci Bands
        vp: Initial Volume Profile (wird rolling aktualisiert)
        start_capital: Startkapital
        vp_lookback: Anzahl Kerzen für VP Berechnung
        require_vp_confluence: Nur starke Signale handeln
        use_poc_tp: PoC als ersten Take-Profit nutzen
    """
    capital = start_capital
    position = None
    trades = []
    bands_idx = bands.index
    equity_curve = [capital]
    
    # VP Statistiken
    strong_signals = 0
    weak_signals = 0
    
    for i in range(max(vp_lookback, 1), len(bands)):
        price = df.loc[bands_idx[i], 'close']
        date = bands_idx[i]
        
        if pd.isna(bands['basis'].iloc[i]):
            continue
        
        # Rolling Volume Profile (letzte vp_lookback Kerzen)
        vp_start = max(0, i - vp_lookback)
        current_vp = calculate_volume_profile(df.iloc[vp_start:i], num_bars=50)
        
        if current_vp is None:
            continue
        
        # --- POSITION MANAGEMENT ---
        if position is not None:
            exit_price = None
            exit_reason = None
            
            if position['side'] == 'long':
                # Stop Loss
                if price < bands['lower_1'].iloc[i]:
                    exit_price = price
                    exit_reason = 'SL (lower_1)'
                # TP1: PoC
                elif use_poc_tp and price >= current_vp['poc'] and not position.get('tp1_hit'):
                    # Teilverkauf bei PoC (50%)
                    position['tp1_hit'] = True
                    partial_pnl = (price - position['entry_price']) / position['entry_price'] * (position['size'] * 0.5)
                    capital += partial_pnl
                    position['size'] *= 0.5
                    trades.append({
                        'type': 'PARTIAL_SELL', 'side': 'long', 'date': date, 
                        'price': price, 'pnl': partial_pnl, 'capital': capital,
                        'level': 'PoC (TP1)'
                    })
                # TP2: upper_6
                elif price >= bands['upper_6'].iloc[i]:
                    exit_price = price
                    exit_reason = 'TP (upper_6)'
            
            elif position['side'] == 'short':
                # Stop Loss
                if price > bands['upper_1'].iloc[i]:
                    exit_price = price
                    exit_reason = 'SL (upper_1)'
                # TP1: PoC
                elif use_poc_tp and price <= current_vp['poc'] and not position.get('tp1_hit'):
                    position['tp1_hit'] = True
                    partial_pnl = (position['entry_price'] - price) / position['entry_price'] * (position['size'] * 0.5)
                    capital += partial_pnl
                    position['size'] *= 0.5
                    trades.append({
                        'type': 'PARTIAL_BUY', 'side': 'short', 'date': date,
                        'price': price, 'pnl': partial_pnl, 'capital': capital,
                        'level': 'PoC (TP1)'
                    })
                # TP2: lower_6
                elif price <= bands['lower_6'].iloc[i]:
                    exit_price = price
                    exit_reason = 'TP (lower_6)'
            
            # Exit ausführen
            if exit_price:
                if position['side'] == 'long':
                    pnl = (exit_price - position['entry_price']) / position['entry_price'] * position['size']
                else:
                    pnl = (position['entry_price'] - exit_price) / position['entry_price'] * position['size']
                
                capital += pnl
                trades.append({
                    'type': 'EXIT', 'side': position['side'], 'date': date,
                    'price': exit_price, 'pnl': pnl, 'capital': capital,
                    'level': exit_reason, 'signal_strength': position.get('signal_strength', 0)
                })
                equity_curve.append(capital)
                position = None
        
        # --- ENTRY LOGIC ---
        if position is None:
            signal_type, strength, reason = get_signal_strength(price, bands, current_vp, i)
            
            # Nur handeln wenn Signal vorhanden
            if signal_type == 'NO_SIGNAL':
                continue
            
            # Bei require_vp_confluence nur STRONG Signale handeln
            if require_vp_confluence and 'STRONG' not in signal_type:
                weak_signals += 1
                continue
            
            strong_signals += 1
            
            if 'LONG' in signal_type:
                position = {
                    'side': 'long',
                    'entry_price': price,
                    'size': capital,
                    'signal_strength': strength,
                    'reason': reason,
                    'tp1_hit': False
                }
                trades.append({
                    'type': 'BUY', 'side': 'long', 'date': date, 'price': price,
                    'level': 'lower_6', 'signal_strength': strength, 'reason': reason
                })
            
            elif 'SHORT' in signal_type:
                position = {
                    'side': 'short',
                    'entry_price': price,
                    'size': capital,
                    'signal_strength': strength,
                    'reason': reason,
                    'tp1_hit': False
                }
                trades.append({
                    'type': 'SELL', 'side': 'short', 'date': date, 'price': price,
                    'level': 'upper_6', 'signal_strength': strength, 'reason': reason
                })
    
    # Offene Position am Ende schließen
    if position is not None and len(bands_idx) > 0:
        price = df.loc[bands_idx[-1], 'close']
        date = bands_idx[-1]
        
        if position['side'] == 'long':
            pnl = (price - position['entry_price']) / position['entry_price'] * position['size']
        else:
            pnl = (position['entry_price'] - price) / position['entry_price'] * position['size']
        
        capital += pnl
        trades.append({
            'type': 'EXIT (End)', 'side': position['side'], 'date': date,
            'price': price, 'pnl': pnl, 'capital': capital
        })
        equity_curve.append(capital)
    
    # Statistiken berechnen
    total_return = (capital - start_capital) / start_capital * 100
    exit_trades = [t for t in trades if 'EXIT' in t['type'] or 'PARTIAL' in t['type']]
    num_trades = len(exit_trades)
    win_trades = [t for t in exit_trades if t.get('pnl', 0) > 0]
    win_rate = len(win_trades) / num_trades * 100 if num_trades else 0
    
    # Maximaler Drawdown
    eq = np.array(equity_curve)
    running_max = np.maximum.accumulate(eq)
    drawdown = (eq - running_max) / running_max * 100
    max_drawdown = abs(np.min(drawdown)) if len(drawdown) > 0 else 0.0
    
    return {
        'capital': capital,
        'total_return': total_return,
        'num_trades': num_trades,
        'win_rate': win_rate,
        'max_drawdown': max_drawdown,
        'trades': trades,
        'equity_curve': equity_curve,
        'strong_signals': strong_signals,
        'weak_signals_filtered': weak_signals
    }


# =============================================================================
# LEGACY BACKTEST (ohne Volume Profile)
# =============================================================================
def fib_backtest(df, bands, start_capital=1000, entry_level='lower_6', exit_level='upper_6'):
    """
    Fibonacci Bollinger Bands Backtest mit Long & Short Trading.
    (Legacy-Funktion für Kompatibilität)
    """
    capital = start_capital
    position = 0  # 0: keine Position, 1: long, -1: short
    entry_price = 0
    entry_idx = 0
    trades = []
    bands_idx = bands.index
    equity_curve = [capital]
    
    for i in range(1, len(bands)):
        price = df.loc[bands_idx[i], 'close']
        basis = bands['basis'].iloc[i]
        date = bands_idx[i]
        
        if pd.isna(basis):
            continue
        
        # --- LONG TRADES ---
        if position == 0 and price <= bands['lower_6'].iloc[i]:
            position = 1
            entry_price = price
            entry_idx = i
            trades.append({'type': 'BUY', 'side': 'long', 'date': date, 'price': price, 'level': 'lower_6'})
        
        elif position == 1 and price >= bands['upper_6'].iloc[i]:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({'type': 'SELL', 'side': 'long', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital, 'level': 'upper_6'})
            equity_curve.append(capital)
            position = 0
        
        elif position == 1 and price < bands['lower_1'].iloc[i]:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({'type': 'SELL (SL)', 'side': 'long', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital, 'level': 'lower_1'})
            equity_curve.append(capital)
            position = 0
        
        # --- SHORT TRADES ---
        elif position == 0 and price >= bands['upper_6'].iloc[i]:
            position = -1
            entry_price = price
            entry_idx = i
            trades.append({'type': 'SELL', 'side': 'short', 'date': date, 'price': price, 'level': 'upper_6'})
        
        elif position == -1 and price <= bands['lower_6'].iloc[i]:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({'type': 'BUY', 'side': 'short', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital, 'level': 'lower_6'})
            equity_curve.append(capital)
            position = 0
        
        elif position == -1 and price > bands['upper_1'].iloc[i]:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({'type': 'BUY (SL)', 'side': 'short', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital, 'level': 'upper_1'})
            equity_curve.append(capital)
            position = 0
    
    # Offene Position am Ende schließen
    if position == 1 and len(bands_idx) > 0:
        price = df.loc[bands_idx[-1], 'close']
        date = bands_idx[-1]
        pnl = (price - entry_price) / entry_price * capital
        capital += pnl
        trades.append({'type': 'SELL (End)', 'side': 'long', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital})
        equity_curve.append(capital)
    elif position == -1 and len(bands_idx) > 0:
        price = df.loc[bands_idx[-1], 'close']
        date = bands_idx[-1]
        pnl = (entry_price - price) / entry_price * capital
        capital += pnl
        trades.append({'type': 'BUY (End)', 'side': 'short', 'date': date, 'price': price, 'pnl': pnl, 'capital': capital})
        equity_curve.append(capital)
    
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len([t for t in trades if t['type'].startswith(('SELL', 'BUY'))])
    win_trades = [t for t in trades if t.get('pnl', 0) > 0]
    win_rate = len(win_trades) / num_trades * 100 if num_trades else 0
    
    eq = np.array(equity_curve)
    running_max = np.maximum.accumulate(eq)
    drawdown = (eq - running_max) / running_max * 100
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
    
    return capital, total_return, num_trades, win_rate, trades, abs(max_drawdown)


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="KBot Backtest (Fib BB + Volume Profile)")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol(e), z.B. BTCUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe(s), z.B. 4h')
    parser.add_argument('--start_date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start_capital', type=float, default=1000, help='Startkapital in USD')
    parser.add_argument('--use_volume_profile', type=bool, default=True, help='Volume Profile nutzen')
    parser.add_argument('--require_confluence', type=bool, default=True, help='Nur bei VP-Konfluenz handeln')
    parser.add_argument('--fib_length', type=int, default=200, help='Fib BB VWMA Länge')
    parser.add_argument('--fib_mult', type=float, default=3.0, help='Fib BB Multiplikator')
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  KBot Backtest (Fibonacci BB + Volume Profile)")
    print("=" * 60)
    print(f"Symbol:           {args.symbol}")
    print(f"Timeframe:        {args.timeframe}")
    print(f"Zeitraum:         {args.start_date} bis {args.end_date}")
    print(f"Startkapital:     {args.start_capital:.2f} USD")
    print(f"Volume Profile:   {'Aktiv' if args.use_volume_profile else 'Inaktiv'}")
    print(f"VP-Konfluenz:     {'Erforderlich' if args.require_confluence else 'Optional'}")
    print(f"Fib Length:       {args.fib_length}")
    print(f"Fib Multiplier:   {args.fib_mult}")
    print("=" * 60 + "\n")

    try:
        df = load_ohlcv(args.symbol, args.start_date, args.end_date, args.timeframe)
    except Exception as e:
        print(f"Fehler beim Laden der Kursdaten: {e}")
        sys.exit(1)
    
    if df.empty or len(df) < 60:
        print("Nicht genügend Kursdaten für Backtest.")
        sys.exit(1)

    print(f"✓ {len(df)} Kerzen geladen\n")

    # Berechne Fibonacci Bollinger Bands
    bands = fibonacci_bollinger_bands(df, length=args.fib_length, mult=args.fib_mult)
    
    if args.use_volume_profile:
        # Berechne initiales Volume Profile
        vp = calculate_volume_profile(df, num_bars=50)
        
        if vp:
            print("Volume Profile Analyse:")
            print(f"  PoC (Point of Control): {vp['poc']:.2f}")
            print(f"  VAH (Value Area High):  {vp['vah']:.2f}")
            print(f"  VAL (Value Area Low):   {vp['val']:.2f}")
            print()
        
        # Backtest mit Volume Profile
        result = fib_vp_backtest(
            df, bands, vp, 
            start_capital=args.start_capital,
            require_vp_confluence=args.require_confluence,
            use_poc_tp=True
        )
        
        print("=" * 60)
        print("  ERGEBNISSE (Fib BB + Volume Profile)")
        print("=" * 60)
        print(f"  Endkapital:        {result['capital']:.2f} USD")
        print(f"  Gesamtrendite:     {result['total_return']:+.2f} %")
        print(f"  Trades:            {result['num_trades']}")
        print(f"  Gewinnquote:       {result['win_rate']:.1f} %")
        print(f"  Max. Drawdown:     {result['max_drawdown']:.2f} %")
        print("-" * 60)
        print(f"  Starke Signale:    {result['strong_signals']}")
        print(f"  Gefiltert (schwach): {result['weak_signals_filtered']}")
        print("=" * 60)
        
    else:
        # Legacy Backtest ohne Volume Profile
        capital, total_return, num_trades, win_rate, trades, max_dd = fib_backtest(
            df, bands, start_capital=args.start_capital
        )
        
        print("Ergebnisse (nur Fib BB):")
        print(f"  Endkapital:    {capital:.2f} USD")
        print(f"  Gesamtrendite: {total_return:.2f} %")
        print(f"  Trades:        {num_trades}")
        print(f"  Gewinnquote:   {win_rate:.1f} %")
        print(f"  Max. Drawdown: {max_dd:.2f} %")


if __name__ == "__main__":
    main()

