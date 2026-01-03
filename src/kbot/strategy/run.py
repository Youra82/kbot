#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Kanal-Trading-Bot (Basisstruktur)



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
        # Entfernt: if len(ohlcv) < limit: break
        # Bitget gibt manchmal weniger als limit zurück, auch wenn mehr Daten da sind!
    if not all_ohlcv:
        raise Exception(f"Keine Daten von Bitget für {symbol} im Zeitraum {start} bis {end}")
    df = pd.DataFrame(all_ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    return df[['open','high','low','close','volume']]


# --- Adaptive Trend Finder: Logarithmische Regression mit ATR-basierter Kanal-Breite ---
def detect_channels(df, window=50, min_channel_width=0.005, slope_threshold=0.05, dev_multiplier=2.0):
    """
    Adaptive Trend Finder mit volatilitäts-basierten (ATR) Kanälen:
    - Logarithmische Regression über verschiedene Perioden (20-200)
    - Wählt die Periode mit der höchsten Pearson-Korrelation
    - Kanal-Breite basiert auf ATR (dynamisch je nach Volatilität)
    
    Args:
        df: OHLC DataFrame
        window: Maximum Periode (Standard: 200)
        min_channel_width: ungenutzt (ersetzt durch ATR)
        slope_threshold: ungenutzt (Kompatibilität)
        dev_multiplier: ATR Multiplikator für Kanal-Breite (Standard: 2.0)
    """
    closes = df['close'].values
    n = len(df)
    
    # Berechne ATR (Average True Range) für volatilitäts-basierte Kanäle
    def calculate_atr(df, period=14):
        """Berechne ATR (Average True Range)"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        tr = np.zeros(n)
        for i in range(n):
            if i == 0:
                tr[i] = high[i] - low[i]
            else:
                tr[i] = max(
                    high[i] - low[i],
                    abs(high[i] - close[i-1]),
                    abs(low[i] - close[i-1])
                )
        
        atr = np.zeros(n)
        atr[period-1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        
        return atr
    
    atr_values = calculate_atr(df, period=14)
    
    # Perioden für Short-Term Channel (wie im TradingView Indikator)
    periods = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
    
    def calc_log_regression(source, length, end_idx):
        """
        TradingView Adaptive Trend Finder Regression:
        x=1 bis x=length, wobei logSource[i-1] für i=1..length
        → i=1: logSource[0] (älteste Kerze)
        → i=length: logSource[length-1] (neueste Kerze)
        Also: x=1 für älteste, x=length für neueste
        """
        if end_idx < length - 1:
            return None, None, None, None
        
        window_data = source[end_idx - length + 1:end_idx + 1]
        log_source = np.log(window_data)
        
        sum_x = 0.0
        sum_xx = 0.0
        sum_yx = 0.0
        sum_y = 0.0
        
        # Loop wie im PineScript: for i = 1 to length, lSrc = logSource[i - 1]
        for i in range(1, length + 1):
            lsrc = log_source[i - 1]  # i=1 → index 0 (älteste), i=length → index length-1 (neueste)
            sum_x += i
            sum_xx += i * i
            sum_yx += i * lsrc
            sum_y += lsrc
        
        slope = (length * sum_yx - sum_x * sum_y) / (length * sum_xx - sum_x * sum_x)
        average = sum_y / length
        intercept = average - slope * sum_x / length + slope
        
        # Standardabweichung Loop
        period_1 = length - 1
        sum_dev = 0.0
        sum_dxx = 0.0
        sum_dyy = 0.0
        sum_dyx = 0.0
        regres = intercept + slope * period_1 * 0.5
        sum_slp = intercept
        
        for i in range(length):
            lsrc = log_source[i]
            dxt = lsrc - average
            dyt = sum_slp - regres
            lsrc_residual = lsrc - sum_slp
            sum_slp += slope
            sum_dxx += dxt * dxt
            sum_dyy += dyt * dyt
            sum_dyx += dxt * dyt
            sum_dev += lsrc_residual * lsrc_residual
        
        std_dev = np.sqrt(sum_dev / period_1) if period_1 > 0 else 0.0
        divisor = sum_dxx * sum_dyy
        pearson_r = sum_dyx / np.sqrt(divisor) if divisor > 0 else 0.0
        
        return slope, intercept, std_dev, abs(pearson_r)
    
    channels = []
    
    # Für jede Kerze: finde beste Periode und berechne Kanal mit ATR-Breite
    for i in range(n):
        if i < periods[0]:  # Nicht genug Daten
            channels.append({
                'high': np.nan,
                'low': np.nan,
                'type': 'none',
                'index': df.index[i],
                'width': 0.0,
                'fit_quality': 0.0
            })
            continue
        
        best_pearson = -1
        best_slope = None
        best_intercept = None
        best_std_dev = None
        best_period = None
        
        # Finde Periode mit höchster Korrelation
        for period in periods:
            if i >= period:
                slope, intercept, std_dev, pearson_r = calc_log_regression(closes, period, i)
                if pearson_r is not None and pearson_r > best_pearson:
                    best_pearson = pearson_r
                    best_slope = slope
                    best_intercept = intercept
                    best_std_dev = std_dev
                    best_period = period
        
        if best_slope is None:
            channels.append({
                'high': np.nan,
                'low': np.nan,
                'type': 'none',
                'index': df.index[i],
                'width': 0.0,
                'fit_quality': 0.0
            })
            continue
        
        # Mittelpunkt aus Regression
        current_log_price = best_intercept + best_slope * (best_period - 1)
        mid_price = np.exp(current_log_price)
        
        # ATR-BASIERTE KANAL-BREITE (statt symmetrisch logarithmisch)
        current_atr = atr_values[i]
        high_line = mid_price + dev_multiplier * current_atr
        low_line = mid_price - dev_multiplier * current_atr
        
        channel_width = (high_line - low_line) / mid_price if mid_price > 0 else 0.0
        
        channels.append({
            'high': high_line,
            'low': low_line,
            'type': 'parallel',
            'index': df.index[i],
            'width': channel_width,
            'fit_quality': float(best_pearson)
        })
    
    ch_df = pd.DataFrame(channels)
    ch_df.index = ch_df['index']
    return ch_df[['high', 'low', 'type', 'width', 'fit_quality']]

# --- Kanal-Trading-Backtest (OPTIMIERT) ---

def channel_backtest(df, channels, start_capital=1000, entry_threshold=0.015, exit_threshold=0.025):
    """
    Optimierter Kanal-basierter Backtest mit Long & Short Trading.
    
    Args:
        df: OHLC DataFrame
        channels: Kanal-Daten von detect_channels()
        start_capital: Startkapital
        entry_threshold: Einstiegs-Schwellenwert (% vom Kanal-Rand)
        exit_threshold: Ausstiegs-Schwellenwert (% vom Kanal-Rand)
    """
    capital = start_capital
    position = 0  # 0: keine Position, 1: long, -1: short
    entry_price = 0
    entry_idx = 0
    trades = []
    ch_idx = channels.index
    equity_curve = [capital]
    
    for i in range(1, len(channels)):
        price = df.loc[ch_idx[i], 'close']
        high = channels['high'].iloc[i]
        low = channels['low'].iloc[i]
        ctype = channels['type'].iloc[i]
        fit_quality = channels['fit_quality'].iloc[i]
        date = ch_idx[i]
        
        # Nur bei Kanälen mit guter Fit-Qualität handeln
        if ctype == 'none' or fit_quality < 0.4:
            continue
        
        # --- LONG TRADES ---
        # EINSTIEG LONG: Preis nähert sich dem unteren Kanalrand
        if position == 0 and price <= low * (1 + entry_threshold):
            position = 1
            entry_price = price
            entry_idx = i
            trades.append({
                'type': 'BUY',
                'side': 'long',
                'date': date,
                'price': price,
                'kanaltyp': ctype
            })
        
        # AUSSTIEG LONG 1: Preis erreicht oberen Kanalrand
        elif position == 1 and price >= high * (1 - exit_threshold):
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL',
                'side': 'long',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # AUSSTIEG LONG 2: Zu lange in Position (> 10 Kerzen) ohne Gewinn
        elif position == 1 and (i - entry_idx) > 10 and price < entry_price * 1.002:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL (T/O)',
                'side': 'long',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # STOP LOSS LONG: Wenn Preis zu stark fällt (-3%)
        elif position == 1 and price < entry_price * 0.97:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL (SL)',
                'side': 'long',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # --- SHORT TRADES ---
        # EINSTIEG SHORT: Preis nähert sich dem oberen Kanalrand
        elif position == 0 and price >= high * (1 - entry_threshold):
            position = -1
            entry_price = price
            entry_idx = i
            trades.append({
                'type': 'SELL',
                'side': 'short',
                'date': date,
                'price': price,
                'kanaltyp': ctype
            })
        
        # AUSSTIEG SHORT 1: Preis erreicht unteren Kanalrand
        elif position == -1 and price <= low * (1 + exit_threshold):
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'BUY',
                'side': 'short',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # AUSSTIEG SHORT 2: Zu lange in Position (> 10 Kerzen) ohne Gewinn
        elif position == -1 and (i - entry_idx) > 10 and price > entry_price * 0.998:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'BUY (T/O)',
                'side': 'short',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # STOP LOSS SHORT: Wenn Preis zu stark steigt (+3%)
        elif position == -1 and price > entry_price * 1.03:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'BUY (SL)',
                'side': 'short',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
    
    # Offene Position am Ende schließen
    if position == 1 and len(ch_idx) > 0:
        price = df.loc[ch_idx[-1], 'close']
        date = ch_idx[-1]
        ctype = channels['type'].iloc[-1]
        pnl = (price - entry_price) / entry_price * capital
        capital += pnl
        trades.append({
            'type': 'SELL (End)',
            'side': 'long',
            'date': date,
            'price': price,
            'pnl': pnl,
            'capital': capital,
            'kanaltyp': ctype
        })
        equity_curve.append(capital)
    elif position == -1 and len(ch_idx) > 0:
        price = df.loc[ch_idx[-1], 'close']
        date = ch_idx[-1]
        ctype = channels['type'].iloc[-1]
        pnl = (entry_price - price) / entry_price * capital
        capital += pnl
        trades.append({
            'type': 'BUY (End)',
            'side': 'short',
            'date': date,
            'price': price,
            'pnl': pnl,
            'capital': capital,
            'kanaltyp': ctype
        })
        equity_curve.append(capital)
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len([t for t in trades if t['type']=='SELL'])
    win_trades = [t for t in trades if t.get('pnl',0)>0]
    win_rate = len(win_trades) / num_trades * 100 if num_trades else 0
    # Maximaler Drawdown berechnen
    eq = np.array(equity_curve)
    if len(eq) > 1:
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak
        max_dd = dd.min() * 100  # in Prozent
    else:
        max_dd = 0.0
    return capital, total_return, num_trades, win_rate, trades, max_dd


def main():
    parser = argparse.ArgumentParser(description="KBot Backtest (Kanalstrategie)")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol(e), z.B. BTCUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe(s), z.B. 4h')
    parser.add_argument('--start_date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start_capital', type=float, default=1000, help='Startkapital in USD')
    args = parser.parse_args()

    print("\nKBot Backtest (Kanalstrategie)")
    print("------------------------------")
    print(f"Symbol:     {args.symbol}")
    print(f"Timeframe:  {args.timeframe}")
    print(f"Zeitraum:   {args.start_date} bis {args.end_date}")
    print(f"Startkapital: {args.start_capital:.2f} USD\n")

    try:
        df = load_ohlcv(args.symbol, args.start_date, args.end_date, args.timeframe)
    except Exception as e:
        print(f"Fehler beim Laden der Kursdaten: {e}")
        sys.exit(1)
    if df.empty or len(df) < 60:
        print("Nicht genügend Kursdaten für Backtest.")
        sys.exit(1)

    channels = detect_channels(df, window=50)
    capital, total_return, num_trades, win_rate, trades, max_dd = channel_backtest(df, channels, start_capital=args.start_capital)

    print("Ergebnisse:")
    print(f"  Endkapital:   {capital:.2f} USD")
    print(f"  Gesamtrendite: {total_return:.2f} %")
    print(f"  Trades:        {num_trades}")
    print(f"  Gewinnquote:   {win_rate:.1f} %")
    print(f"  Max. Drawdown: {max_dd:.2f} %\n")

    if trades:
        # Zähle wie oft jeder Kanaltyp verwendet wurde
        from collections import Counter
        kanaltypen = [t.get('kanaltyp','unbekannt') for t in trades if t.get('kanaltyp')]
        if kanaltypen:
            print("Verwendete Kanaltypen:")
            for ktyp, count in Counter(kanaltypen).items():
                print(f"  {ktyp}: {count}x")
        else:
            print("Keine Kanaltypen in Trades gefunden.")
    else:
        print("Keine Trades im Zeitraum.")

if __name__ == "__main__":
    main()

