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


# --- Fibonacci Bollinger Bands ---
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

# --- Fibonacci Bollinger Bands Backtest ---

def fib_backtest(df, bands, start_capital=1000, entry_level='lower_6', exit_level='upper_6'):
    """
    Fibonacci Bollinger Bands Backtest mit Long & Short Trading.
    
    Args:
        df: OHLC DataFrame
        bands: Fibonacci Bands von fibonacci_bollinger_bands()
        start_capital: Startkapital
        entry_level: Level für Entry (z.B. 'lower_6' für Long, 'upper_6' für Short)
        exit_level: Level für Exit
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
        # EINSTIEG LONG: Preis berührt lower_6 (unterste Fib-Linie)
        if position == 0 and price <= bands['lower_6'].iloc[i]:
            position = 1
            entry_price = price
            entry_idx = i
            trades.append({
                'type': 'BUY',
                'side': 'long',
                'date': date,
                'price': price,
                'level': 'lower_6'
            })
        
        # AUSSTIEG LONG: Preis erreicht upper_6
        elif position == 1 and price >= bands['upper_6'].iloc[i]:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL',
                'side': 'long',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'level': 'upper_6'
            })
            equity_curve.append(capital)
            position = 0
        
        # STOP LOSS LONG: Price fällt unter lower_1
        elif position == 1 and price < bands['lower_1'].iloc[i]:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL (SL)',
                'side': 'long',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'level': 'lower_1'
            })
            equity_curve.append(capital)
            position = 0
        
        # --- SHORT TRADES ---
        # EINSTIEG SHORT: Preis berührt upper_6 (oberste Fib-Linie)
        elif position == 0 and price >= bands['upper_6'].iloc[i]:
            position = -1
            entry_price = price
            entry_idx = i
            trades.append({
                'type': 'SELL',
                'side': 'short',
                'date': date,
                'price': price,
                'level': 'upper_6'
            })
        
        # AUSSTIEG SHORT: Preis erreicht lower_6
        elif position == -1 and price <= bands['lower_6'].iloc[i]:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'BUY',
                'side': 'short',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'level': 'lower_6'
            })
            equity_curve.append(capital)
            position = 0
        
        # STOP LOSS SHORT: Price steigt über upper_1
        elif position == -1 and price > bands['upper_1'].iloc[i]:
            pnl = (entry_price - price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'BUY (SL)',
                'side': 'short',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'level': 'upper_1'
            })
            equity_curve.append(capital)
            position = 0
    
    # Offene Position am Ende schließen
    if position == 1 and len(bands_idx) > 0:
        price = df.loc[bands_idx[-1], 'close']
        date = bands_idx[-1]
        pnl = (price - entry_price) / entry_price * capital
        capital += pnl
        trades.append({
            'type': 'SELL (End)',
            'side': 'long',
            'date': date,
            'price': price,
            'pnl': pnl,
            'capital': capital
        })
        equity_curve.append(capital)
    elif position == -1 and len(bands_idx) > 0:
        price = df.loc[bands_idx[-1], 'close']
        date = bands_idx[-1]
        pnl = (entry_price - price) / entry_price * capital
        capital += pnl
        trades.append({
            'type': 'BUY (End)',
            'side': 'short',
            'date': date,
            'price': price,
            'pnl': pnl,
            'capital': capital
        })
        equity_curve.append(capital)
    
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len([t for t in trades if t['type'].startswith(('SELL', 'BUY'))])
    win_trades = [t for t in trades if t.get('pnl',0)>0]
    win_rate = len(win_trades) / num_trades * 100 if num_trades else 0
    
    # Maximaler Drawdown berechnen
    eq = np.array(equity_curve)
    running_max = np.maximum.accumulate(eq)
    drawdown = (eq - running_max) / running_max * 100
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
    
    return capital, total_return, num_trades, win_rate, trades, abs(max_drawdown)



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

    bands = fibonacci_bollinger_bands(df, length=200, mult=3.0)
    capital, total_return, num_trades, win_rate, trades, max_dd = fib_backtest(df, bands, start_capital=args.start_capital)

    print("Ergebnisse:")
    print(f"  Endkapital:   {capital:.2f} USD")
    print(f"  Gesamtrendite: {total_return:.2f} %")
    print(f"  Trades:        {num_trades}")
    print(f"  Gewinnquote:   {win_rate:.1f} %")
    print(f"  Max. Drawdown: {max_dd:.2f} %\n")

    if trades:
        print(f"Gesamttrades: {len(trades)}")
    else:
        print("Keine Trades im Zeitraum.")

if __name__ == "__main__":
    main()

