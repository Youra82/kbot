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
    if not symbol.endswith(':USDT'):
        symbol = symbol.upper() + '/USDT:USDT'
    since = int(pd.Timestamp(start).timestamp() * 1000)
    end_ts = int(pd.Timestamp(end).timestamp() * 1000)
    tf_map = {'1d':'1d','4h':'4h','1h':'1h','6h':'6h','30m':'30m','15m':'15m','5m':'5m'}
    tf = tf_map.get(timeframe, '1d')
    all_ohlcv = []
    limit = 500
    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv += ohlcv
        last = ohlcv[-1][0]
        # Bitget gibt Kerzen ab since, also +1ms um Überschneidung zu vermeiden
        since = last + 1
        if len(ohlcv) < limit:
            break
    if not all_ohlcv:
        raise Exception(f"Keine Daten von Bitget für {symbol} im Zeitraum {start} bis {end}")
    df = pd.DataFrame(all_ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    return df[['open','high','low','close','volume']]


# --- Erweiterte Kanal-Erkennung: parallel, wedge, triangle ---
def detect_channels(df, window=50):
    idx = np.arange(len(df))
    channel_types = []
    highs = df['high'].values
    lows = df['low'].values
    channels = []
    for i in range(window, len(df)):
        x = idx[i-window:i]
        y_high = highs[i-window:i]
        y_low = lows[i-window:i]
        coef_high = np.polyfit(x, y_high, 1)
        coef_low = np.polyfit(x, y_low, 1)
        # Parallelkanal: ähnliche Steigung
        if abs(coef_high[0] - coef_low[0]) < 0.1 * max(abs(coef_high[0]), 1e-8):
            ctype = 'parallel'
        # Keil: beide Linien gleiche Richtung, Abstand wird kleiner
        elif np.sign(coef_high[0]) == np.sign(coef_low[0]) and abs(coef_high[0]) > 0.05 and abs(coef_low[0]) > 0.05:
            ctype = 'wedge'
        # Dreieck: Linien laufen aufeinander zu (entgegengesetzte Steigung)
        elif coef_high[0] < 0 and coef_low[0] > 0:
            ctype = 'triangle'
        else:
            ctype = 'none'
        high_val = np.polyval(coef_high, x[-1])
        low_val = np.polyval(coef_low, x[-1])
        channels.append({'high': high_val, 'low': low_val, 'type': ctype, 'index': df.index[i]})
    # DataFrame mit Kanaltypen
    ch_df = pd.DataFrame(channels)
    ch_df.index = ch_df['index']
    return ch_df[['high','low','type']]

# --- Kanal-Trading-Backtest ---

def channel_backtest(df, channels, start_capital=1000):
    capital = start_capital
    position = 0
    entry_price = 0
    trades = []
    channel_types = []
    ch_idx = channels.index
    equity_curve = [capital]
    for i in range(1, len(channels)):
        price = df.loc[ch_idx[i], 'close']
        high = channels['high'].iloc[i]
        low = channels['low'].iloc[i]
        ctype = channels['type'].iloc[i]
        date = ch_idx[i]
        channel_types.append(ctype)
        # Einstieg Long am unteren Kanalrand (nur bei erkanntem Kanaltyp)
        if position == 0 and ctype != 'none' and (abs(price - low) < 1e-8 or price <= low * 1.001):
            position = 1
            entry_price = price
            trades.append({'type':'BUY','date':date,'price':price,'kanaltyp':ctype})
        # Ausstieg Long am oberen Kanalrand
        elif position == 1 and (price >= high * 0.999):
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({'type':'SELL','date':date,'price':price,'pnl':pnl,'capital':capital,'kanaltyp':ctype})
            equity_curve.append(capital)
            position = 0
    # Offene Position am Ende schließen
    if position == 1:
        price = df.loc[ch_idx[-1], 'close']
        date = ch_idx[-1]
        ctype = channels['type'].iloc[-1]
        pnl = (price - entry_price) / entry_price * capital
        capital += pnl
        trades.append({'type':'SELL','date':date,'price':price,'pnl':pnl,'capital':capital,'kanaltyp':ctype})
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

