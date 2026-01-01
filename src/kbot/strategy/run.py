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


# --- Erweiterte Kanal-Erkennung: parallel, wedge, triangle (OPTIMIERT) ---
def detect_channels(df, window=50, min_channel_width=0.005, slope_threshold=0.05):
    """
    Erkennt Handelskanäle mit verbesserten Validierungen.
    
    Args:
        df: OHLC DataFrame
        window: Fenster-Größe für Kanal-Analyse (Standard: 50 Kerzen)
        min_channel_width: Minimale Kanal-Breite als % vom Preis (Standard: 0.5%)
        slope_threshold: Minimale Steigung für bedeutungsvolle Trends (Standard: 0.05)
    """
    idx = np.arange(len(df))
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    channels = []
    
    for i in range(window, len(df)):
        x = idx[i-window:i]
        y_high = highs[i-window:i]
        y_low = lows[i-window:i]
        y_close = closes[i-window:i]
        
        coef_high = np.polyfit(x, y_high, 1)
        coef_low = np.polyfit(x, y_low, 1)
        
        # Berechne Kanal-Breite und Stabilität
        high_val = np.polyval(coef_high, x[-1])
        low_val = np.polyval(coef_low, x[-1])
        mid_val = (high_val + low_val) / 2
        channel_width = (high_val - low_val) / mid_val if mid_val > 0 else 0
        
        # Berechne R² für Fit-Qualität
        y_high_pred = np.polyval(coef_high, x)
        y_low_pred = np.polyval(coef_low, x)
        ss_res_high = np.sum((y_high - y_high_pred) ** 2)
        ss_tot_high = np.sum((y_high - np.mean(y_high)) ** 2)
        r2_high = 1 - (ss_res_high / ss_tot_high) if ss_tot_high > 0 else 0
        
        ss_res_low = np.sum((y_low - y_low_pred) ** 2)
        ss_tot_low = np.sum((y_low - np.mean(y_low)) ** 2)
        r2_low = 1 - (ss_res_low / ss_tot_low) if ss_tot_low > 0 else 0
        
        fit_quality = min(r2_high, r2_low)
        
        # Klassifizierung mit strengeren Bedingungen
        ctype = 'none'
        
        # Nur Kanäle mit ausreichender Breite und Fit-Qualität
        if channel_width >= min_channel_width and fit_quality >= 0.5:
            slope_diff = abs(coef_high[0] - coef_low[0])
            slope_high = abs(coef_high[0])
            slope_low = abs(coef_low[0])
            
            # Parallele Kanäle: Ähnliche Steigung UND stabil
            if slope_diff < 0.08 * max(slope_high, slope_low, 1e-8):
                ctype = 'parallel'
            # Keile: Gleiche Richtung UND deutliche Steigung
            elif (np.sign(coef_high[0]) == np.sign(coef_low[0]) and 
                  slope_high > slope_threshold and slope_low > slope_threshold):
                ctype = 'wedge'
            # Dreiecke: Konvergierende Linien
            elif coef_high[0] < -slope_threshold and coef_low[0] > slope_threshold:
                ctype = 'triangle'
        
        channels.append({
            'high': high_val, 
            'low': low_val, 
            'type': ctype, 
            'index': df.index[i],
            'width': channel_width,
            'fit_quality': fit_quality
        })
    
    # DataFrame mit Kanaltypen
    ch_df = pd.DataFrame(channels)
    ch_df.index = ch_df['index']
    return ch_df[['high','low','type','width','fit_quality']]

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

