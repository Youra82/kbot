#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Kanal-Trading-Bot (Basisstruktur)
import sys
import argparse

# --- Argument-Parser für Shell-Aufruf ---
def main():
    parser = argparse.ArgumentParser(description="KBot Backtest (Dummy-Ausgabe)")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol(e), z.B. BTCUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe(s), z.B. 4h')
    parser.add_argument('--start_date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    args = parser.parse_args()

    print("\nKBot Backtest Dummy-Ausgabe")
    print("---------------------------")
    print(f"Symbol(e):   {args.symbol}")
    print(f"Timeframe(s): {args.timeframe}")
    print(f"Zeitraum:    {args.start_date} bis {args.end_date}")
    print("\n[Hier folgt später die Backtest-Logik und Ergebnis-Ausgabe]")

if __name__ == "__main__":
    main()

# ...existing code...
        for start in range(0, len(df)-window, min_points//2):
            end = start + window
            x = idx[start:end]
            y_high = highs[start:end]
            y_low = lows[start:end]
            # Lineare Regression für obere und untere Begrenzung
            coef_high = np.polyfit(x, y_high, 1)
            coef_low = np.polyfit(x, y_low, 1)
            # Prüfe Parallelität (ähnliche Steigung)
            if abs(coef_high[0] - coef_low[0]) < 0.1 * abs(coef_high[0]):
                channels.append({
                    'type': 'parallel',
                    'start': int(x[0]), 'end': int(x[-1]),
                    'high_line': coef_high.tolist(),
                    'low_line': coef_low.tolist()
                })
    # Dreiecke (konvergierende Linien)
    for window in range(min_points, len(df), min_points//2):
        for start in range(0, len(df)-window, min_points//2):
            end = start + window
            x = idx[start:end]
            y_high = highs[start:end]
            y_low = lows[start:end]
            coef_high = np.polyfit(x, y_high, 1)
            coef_low = np.polyfit(x, y_low, 1)
            # Prüfe Konvergenz (Steigungen entgegengesetzt)
            if coef_high[0] < 0 and coef_low[0] > 0:
                channels.append({
                    'type': 'triangle',
                    'start': int(x[0]), 'end': int(x[-1]),
                    'high_line': coef_high.tolist(),
                    'low_line': coef_low.tolist()
                })
    # Keile (beide Linien gleiche Richtung, aber Abstand wird kleiner)
    for window in range(min_points, len(df), min_points//2):
        for start in range(0, len(df)-window, min_points//2):
            end = start + window
            x = idx[start:end]
            y_high = highs[start:end]
            y_low = lows[start:end]
            coef_high = np.polyfit(x, y_high, 1)
            coef_low = np.polyfit(x, y_low, 1)
            # Beide Steigungen gleiches Vorzeichen, Abstand verringert sich
            if np.sign(coef_high[0]) == np.sign(coef_low[0]) and abs(coef_high[0]) > 0.05 and abs(coef_low[0]) > 0.05:
                if abs((y_high[-1] - y_low[-1]) - (y_high[0] - y_low[0])) < 0.2 * abs(y_high[0] - y_low[0]):
                    channels.append({
                        'type': 'wedge',
                        'start': int(x[0]), 'end': int(x[-1]),
                        'high_line': coef_high.tolist(),
                        'low_line': coef_low.tolist()
                    })
    return channels

@guardian_decorator
def run_for_account(account, telegram_config, params, logger):
    account_name = account.get('name', 'Standard-Account')
    symbol = params['market']['symbol']
    timeframe = params['market']['timeframe']
    logger.info(f"--- Starte KBot für {symbol} ({timeframe}) auf Account '{account_name}' ---")
    exchange = Exchange(account)
    # OHLCV-Daten laden
    df = exchange.fetch_historical_ohlcv(symbol, timeframe, limit=500)
    if df is None or len(df) < 30:

        logger.error("Nicht genügend Daten für Kanal-Erkennung.")
