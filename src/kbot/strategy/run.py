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


# --- Kanal-Erkennung: genau ein Kanal zwischen letzter HH->HH und LL->LL ---
def detect_channels(df, window=50, min_channel_width=0.005, slope_threshold=0.05, pivot_lookback=5):
    """
    Baut pro Kerze genau einen Kanal, indem die letzten zwei Pivot-Hochs (HH)
    verbunden werden und die letzten zwei Pivot-Tiefs (LL) verbunden werden.
    Dadurch entsteht ein sauberer, einziger Kanal (keine überlappenden Linien).

    Args:
        df: OHLC DataFrame
        window: maximale Alter der genutzten Pivots (Kerzen)
        min_channel_width: minimale Breite als Anteil am Preis
        slope_threshold: nur für Signatur-Kompatibilität
        pivot_lookback: Kerzen links/rechts zur Pivot-Bestätigung
    """
    highs = df['high'].values
    lows = df['low'].values
    channels = []

    # Pivot-Erkennung (Swing High/Low)
    pivot_high_mask = np.zeros(len(df), dtype=bool)
    pivot_low_mask = np.zeros(len(df), dtype=bool)
    for i in range(pivot_lookback, len(df) - pivot_lookback):
        left = i - pivot_lookback
        right = i + pivot_lookback + 1
        if highs[i] >= highs[left:right].max():
            pivot_high_mask[i] = True
        if lows[i] <= lows[left:right].min():
            pivot_low_mask[i] = True

    pivot_high_idx = np.where(pivot_high_mask)[0]
    pivot_low_idx = np.where(pivot_low_mask)[0]

    def line_val(start_idx, start_val, slope, target_idx):
        return start_val + slope * (target_idx - start_idx)

    for i in range(window, len(df)):
        # Letzte zwei HH und LL vor aktueller Kerze
        ph_pos = np.searchsorted(pivot_high_idx, i, side='right')
        pl_pos = np.searchsorted(pivot_low_idx, i, side='right')

        if ph_pos < 2 or pl_pos < 2:
            channels.append({'high': np.nan, 'low': np.nan, 'type': 'none', 'index': df.index[i], 'width': 0.0, 'fit_quality': 0.0})
            continue

        h1_idx, h2_idx = pivot_high_idx[ph_pos - 2], pivot_high_idx[ph_pos - 1]
        l1_idx, l2_idx = pivot_low_idx[pl_pos - 2], pivot_low_idx[pl_pos - 1]

        # Nur frische Pivots (innerhalb Fenster)
        if (i - h2_idx) > window or (i - l2_idx) > window:
            channels.append({'high': np.nan, 'low': np.nan, 'type': 'none', 'index': df.index[i], 'width': 0.0, 'fit_quality': 0.0})
            continue

        slope_high = (highs[h2_idx] - highs[h1_idx]) / max((h2_idx - h1_idx), 1e-9)
        slope_low = (lows[l2_idx] - lows[l1_idx]) / max((l2_idx - l1_idx), 1e-9)

        high_line = line_val(h2_idx, highs[h2_idx], slope_high, i)
        low_line = line_val(l2_idx, lows[l2_idx], slope_low, i)
        mid_val = (high_line + low_line) / 2
        channel_width = (high_line - low_line) / mid_val if mid_val > 0 else 0.0

        # Qualitätsmaß: hier simpel, da Linie durch die Pivots exakt geht
        fit_quality = 1.0 if channel_width > 0 else 0.0

        ctype = 'none'
        if high_line > low_line and channel_width >= min_channel_width:
            ctype = 'parallel'  # einheitlicher Kanal-Typ für Plot/Backtest

        channels.append({
            'high': high_line,
            'low': low_line,
            'type': ctype,
            'index': df.index[i],
            'width': channel_width,
            'fit_quality': float(fit_quality)
        })

    ch_df = pd.DataFrame(channels)
    ch_df.index = ch_df['index']
    return ch_df[['high', 'low', 'type', 'width', 'fit_quality']]

# --- Kanal-Trading-Backtest (OPTIMIERT) ---

def channel_backtest(df, channels, start_capital=1000, entry_threshold=0.015, exit_threshold=0.025):
    """
    Optimierter Kanal-basierter Backtest mit verbessertem Risikomanagement.
    
    Args:
        df: OHLC DataFrame
        channels: Kanal-Daten von detect_channels()
        start_capital: Startkapital
        entry_threshold: Einstiegs-Schwellenwert (% vom Kanal-Tiefpunkt)
        exit_threshold: Ausstiegs-Schwellenwert (% vom Kanal-Hochpunkt)
    """
    capital = start_capital
    position = 0
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
        
        # EINSTIEG: Preis nähert sich dem unteren Kanalrand
        if position == 0 and price <= low * (1 + entry_threshold):
            position = 1
            entry_price = price
            entry_idx = i
            trades.append({
                'type': 'BUY',
                'date': date,
                'price': price,
                'kanaltyp': ctype
            })
        
        # AUSSTIEG 1: Preis erreicht oberen Kanalrand
        elif position == 1 and price >= high * (1 - exit_threshold):
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # AUSSTIEG 2: Zu lange in Position (> 10 Kerzen) ohne Gewinn
        elif position == 1 and (i - entry_idx) > 10 and price < entry_price * 1.002:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL (T/O)',
                'date': date,
                'price': price,
                'pnl': pnl,
                'capital': capital,
                'kanaltyp': ctype
            })
            equity_curve.append(capital)
            position = 0
            entry_idx = 0
        
        # STOP LOSS: Wenn Preis zu stark fällt (-3%)
        elif position == 1 and price < entry_price * 0.97:
            pnl = (price - entry_price) / entry_price * capital
            capital += pnl
            trades.append({
                'type': 'SELL (SL)',
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
            'date': date,
            'price': price,
            'pnl': pnl,
            'capital': capital,
            'kanaltyp': ctype
        })
        equity_curve.append(capital)
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

