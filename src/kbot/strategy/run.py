#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Kanal-Trading-Bot (Basisstruktur)



import sys
import argparse
import pandas as pd
import numpy as np
import datetime
import ccxt
import os

# Ensure local `src` is on sys.path so `import kbot.*` works when run.py
# is executed as a subprocess from the project root.
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

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
        import os
        import json
        import logging
        import time
        from kbot.utils.ann_model import load_model_and_scaler
        from kbot.utils.trade_manager import full_trade_cycle
        from kbot.utils.exchange import Exchange

        print("\nKBot Live Mode")
        print("---------------")
        print(f"Symbol:     {args.symbol}")
        print(f"Timeframe:  {args.timeframe}")

        # Projekt-Root bestimmen (ein Verzeichnis oberhalb von `src`)
        # `SRC_ROOT` ist oben als .../project/src gesetzt, also ist PROJECT_ROOT dessen Parent
        PROJECT_ROOT = os.path.abspath(os.path.join(SRC_ROOT, '..'))

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

        try:
            exchange = Exchange(account_config)
        except Exception as e:
            print(f"Fehler beim Initialisieren der Exchange: {e}")
            return

        tf_map_seconds = {'1m':60, '5m':300, '15m':900, '30m':1800, '1h':3600, '2h':7200, '4h':14400, '6h':21600, '12h':43200, '1d':86400}
        sleep_seconds = tf_map_seconds.get(args.timeframe, 3600)

        print(f"Starte Live-Loop für {args.symbol} ({args.timeframe}). Intervall ≈ {sleep_seconds}s")
        try:
            while True:
                try:
                    full_trade_cycle(exchange, model, scaler, params, telegram_config, logger)
                except Exception as e:
                    logger.error(f"Fehler im Handelszyklus: {e}", exc_info=True)
                time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            print('\nLive-Run durch Benutzer gestoppt.')
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

