#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Kanal-Trading-Bot (Basisstruktur)

import sys
import argparse
import pandas as pd
import numpy as np
import datetime
try:
    import pandas_datareader.data as web
except ImportError:
    web = None

# --- Hilfsfunktion: Kursdaten laden (Yahoo Finance) ---
def load_ohlcv(symbol, start, end, timeframe):
    if web is None:
        raise ImportError("pandas_datareader muss installiert sein (pip install pandas_datareader)")
    # Mapping für Yahoo Finance
    symbol_map = {
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD',
        'XRP': 'XRP-USD',
        'ADA': 'ADA-USD',
        'DOGE': 'DOGE-USD',
        'SOL': 'SOL-USD',
    }
    yf_symbol = symbol_map.get(symbol.upper(), symbol.upper())
    df = web.DataReader(yf_symbol, 'yahoo', start, end)
    df = df.rename(columns={'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'})
    df = df[['open','high','low','close','volume']]
    df.index = pd.to_datetime(df.index)
    if timeframe != '1d':
        # Resample auf gewünschtes Intervall (z.B. 1h, 4h)
        rule = {'1h':'1H','4h':'4H','6h':'6H','12h':'12H'}.get(timeframe, None)
        if rule:
            df = df.resample(rule).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    return df

# --- Einfache SMA-Crossover-Strategie ---
def sma_crossover_backtest(df, fast=20, slow=50, start_capital=1000):
    df = df.copy()
    df['sma_fast'] = df['close'].rolling(fast).mean()
    df['sma_slow'] = df['close'].rolling(slow).mean()
    df['signal'] = 0
    df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1
    df.loc[df['sma_fast'] < df['sma_slow'], 'signal'] = -1
    df['position'] = df['signal'].shift(1).fillna(0)
    trades = []
    capital = start_capital
    position = 0
    entry_price = 0
    for i, row in df.iterrows():
        if row['position'] == 1 and position == 0:
            # Long-Einstieg
            position = 1
            entry_price = row['close']
            trades.append({'type':'BUY','date':i,'price':entry_price})
        elif row['position'] == -1 and position == 1:
            # Long-Exit
            exit_price = row['close']
            pnl = (exit_price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({'type':'SELL','date':i,'price':exit_price,'pnl':pnl,'capital':capital})
            position = 0
    # Offene Position am Ende schließen
    if position == 1:
        exit_price = df['close'].iloc[-1]
        pnl = (exit_price - entry_price) / entry_price * capital
        capital += pnl
        trades.append({'type':'SELL','date':df.index[-1],'price':exit_price,'pnl':pnl,'capital':capital})
    # Performance-Kennzahlen
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len([t for t in trades if t['type']=='SELL'])
    win_trades = [t for t in trades if t.get('pnl',0)>0]
    win_rate = len(win_trades) / num_trades * 100 if num_trades else 0
    return capital, total_return, num_trades, win_rate, trades

def main():
    parser = argparse.ArgumentParser(description="KBot Backtest (SMA-Crossover)")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol(e), z.B. BTCUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe(s), z.B. 4h')
    parser.add_argument('--start_date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start_capital', type=float, default=1000, help='Startkapital in USD')
    args = parser.parse_args()

    print("\nKBot Backtest (SMA-Crossover)")
    print("-----------------------------")
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

    capital, total_return, num_trades, win_rate, trades = sma_crossover_backtest(df, fast=20, slow=50, start_capital=args.start_capital)

    print("Ergebnisse:")
    print(f"  Endkapital:   {capital:.2f} USD")
    print(f"  Gesamtrendite: {total_return:.2f} %")
    print(f"  Trades:        {num_trades}")
    print(f"  Gewinnquote:   {win_rate:.1f} %\n")

    if trades:
        print("Trade-Liste:")
        print(f"{'Typ':<6} {'Datum':<19} {'Preis':>10} {'P&L':>10} {'Kapital':>10}")
        for t in trades:
            typ = t['type']
            datum = t['date'].strftime('%Y-%m-%d %H:%M') if hasattr(t['date'],'strftime') else str(t['date'])
            preis = f"{t['price']:.2f}"
            pnl = f"{t.get('pnl',''):>10.2f}" if 'pnl' in t else ' '*10
            cap = f"{t.get('capital',''):>10.2f}" if 'capital' in t else ' '*10
            print(f"{typ:<6} {datum:<19} {preis:>10} {pnl} {cap}")
    else:
        print("Keine Trades im Zeitraum.")

if __name__ == "__main__":
    main()

