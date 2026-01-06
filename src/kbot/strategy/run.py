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
    if args.live:
        import os
        import json
        import logging
        from kbot.utils.ann_model import load_model_and_scaler
        from kbot.utils.trade_manager import full_trade_cycle
        from kbot.utils.exchange import Exchange

        print("\nKBot Live Mode")
        print("---------------")
        print(f"Symbol:     {args.symbol}")
        print(f"Timeframe:  {args.timeframe}")

        # Projekt-Root bestimmen
        SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        PROJECT_ROOT = SCRIPT_DIR

        # Erzeuge sicheren Dateinamen wie im Optimizer
        def create_safe_filename(symbol, timeframe):
            return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"

        safe_name = create_safe_filename(args.symbol, args.timeframe)
        config_path = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs', f'config_{safe_name}.json')
        model_path = os.path.join(PROJECT_ROOT, 'artifacts', 'models', f'ann_predictor_{safe_name}.h5')
        scaler_path = os.path.join(PROJECT_ROOT, 'artifacts', 'models', f'ann_scaler_{safe_name}.joblib')

        if not os.path.exists(config_path):
            print(f"Fehler: Strategy-Config nicht gefunden: {config_path}")
            return

        with open(config_path, 'r') as f:
            params = json.load(f)

        # Lade Modell & Scaler
        model, scaler = load_model_and_scaler(model_path, scaler_path)
        if model is None or scaler is None:
            print(f"Fehler: Modell/Scaler nicht gefunden oder konnte nicht geladen werden: {model_path}, {scaler_path}")
            return

        # Lade Secrets für Exchange + Telegram
        secret_file = os.path.join(PROJECT_ROOT, 'secret.json')
        try:
            with open(secret_file, 'r') as f:
                secrets = json.load(f)
            account_config = secrets.get('kbot', [])[0]
            telegram_config = secrets.get('telegram', {})
        except Exception as e:
            print(f"Warnung: secret.json konnte nicht geladen werden: {e}")
            account_config = {}
            telegram_config = {}

        # Logger
        logger = logging.getLogger('kbot_live')
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

        # Exchange initialisieren
        try:
            exchange = Exchange(account_config)
        except Exception as e:
            print(f"Fehler beim Initialisieren der Exchange: {e}")
            return

        # Sleep mapping für Timeframes (Fallbacks)
        tf_map_seconds = {'1m':60, '5m':300, '15m':900, '30m':1800, '1h':3600, '2h':7200, '4h':14400, '6h':21600, '12h':43200, '1d':86400}
        sleep_seconds = tf_map_seconds.get(args.timeframe, 3600)

        print(f"Starte Live-Loop für {args.symbol} ({args.timeframe}). Intervall ≈ {sleep_seconds}s")
        try:
            while True:
                try:
                    full_trade_cycle(exchange, model, scaler, params, telegram_config, logger)
                except Exception as e:
                    logger.error(f"Fehler im Handelszyklus: {e}", exc_info=True)
                # Warte bis zur nächsten Kerze
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print('\nLive-Run durch Benutzer gestoppt.')
        return
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
    parser.add_argument('--start_date', type=str, required=False, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=False, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start_capital', type=float, default=1000, help='Startkapital in USD')
    parser.add_argument('--live', action='store_true', help='Run in live mode (no backtest)')
    args = parser.parse_args()

    if args.live:
        print("\nKBot Live Mode")
        print("---------------")
        print(f"Symbol:     {args.symbol}")
        print(f"Timeframe:  {args.timeframe}")
        print("Starte Live-Modus (Diagnostik / dry-run). Evaluieren, ob ein Trade möglich wäre (keine Orders werden gesendet).")

        # Versuche, ausreichend historische Daten zu laden (1 Jahr als Default)
        today = datetime.datetime.utcnow().date()
        end_date = today.strftime('%Y-%m-%d')
        start_date = (today - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

        try:
            df = load_ohlcv(args.symbol, start_date, end_date, args.timeframe)
        except Exception as e:
            print(f"Fehler beim Laden der Kursdaten für Diagnostik: {e}")
            return

        if df.empty or len(df) < 60:
            print("Nicht genügend Kursdaten für Diagnostik/backtest.")
            return

        # Berechne Bänder und bewerte aktuelle Situation
        bands = fibonacci_bollinger_bands(df, length=200, mult=3.0)
        latest_price = df['close'].iloc[-1]
        latest_time = df.index[-1]

        print(f"Letzter Kerzenzeitpunkt: {latest_time}  Preis: {latest_price:.6f}")

        reasons = []
        action = 'NO ENTRY'

        if pd.isna(bands['basis'].iloc[-1]):
            reasons.append('Basis/Indikatoren nicht berechnet (NaN)')
        else:
            lower6 = bands['lower_6'].iloc[-1]
            upper6 = bands['upper_6'].iloc[-1]
            if pd.notna(lower6) and latest_price <= lower6:
                action = 'BUY (would enter LONG)'
                reasons.append(f'Preis {latest_price:.6f} <= lower_6 {lower6:.6f} -> Long-Entry')
            elif pd.notna(upper6) and latest_price >= upper6:
                action = 'SELL (would enter SHORT)'
                reasons.append(f'Preis {latest_price:.6f} >= upper_6 {upper6:.6f} -> Short-Entry')
            else:
                # zusätzliche Hinweise, warum kein Entry
                dist_lower = (latest_price - lower6) if pd.notna(lower6) else None
                dist_upper = (upper6 - latest_price) if pd.notna(upper6) else None
                if dist_lower is not None and dist_upper is not None:
                    reasons.append(f'Preis liegt zwischen entry-Leveln: dist to lower_6 = {dist_lower:.6f}, dist to upper_6 = {dist_upper:.6f}')
                else:
                    reasons.append('Preis nicht an Entry-Levels oder fehlende Level-Daten')

        print('\nDiagnostik-Ergebnis:')
        print(f'  Aktion: {action}')
        print('  Gründe:')
        for r in reasons:
            print(f'   - {r}')
        # Zusätzliche Debug-Informationen
        print('\nLetzte 10 Kerzen (Timestamp, Close):')
        for t, close in df['close'].tail(10).items():
            print(f'  {t}  {close:.6f}')

        # Band-Werte der letzten Kerze
        last_bands = bands.iloc[-1]
        print('\nBandwerte (letzte Kerze):')
        try:
            print(f"  basis: {last_bands['basis']:.6f}  dev: {last_bands['dev']:.6f}")
            for i in range(1,7):
                print(f"  upper_{i}: {last_bands[f'upper_{i}']:.6f}  lower_{i}: {last_bands[f'lower_{i}']:.6f}")
        except Exception:
            print('  (Bandwerte nicht vollständig vorhanden)')

        # Prozentuale Abstände zu Entry-Levels
        try:
            lower6 = last_bands['lower_6']
            upper6 = last_bands['upper_6']
            if pd.notna(lower6):
                pct_to_lower = (latest_price - lower6) / lower6 * 100
                print(f"\nAbstand zum lower_6: {pct_to_lower:.3f}% (negativ = unterhalb)")
            if pd.notna(upper6):
                pct_to_upper = (upper6 - latest_price) / upper6 * 100
                print(f"Abstand zum upper_6: {pct_to_upper:.3f}% (negativ = oberhalb)")
        except Exception:
            pass

        print('\nHinweis: Dies ist ein Dry-Run. Es werden keine Orders gesendet.')
        return

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

