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
        return
    # Kanäle erkennen
    channels = detect_channels(df)
    for channel in channels:
        # Telegram-Nachricht mit exakten Koordinaten
        start_idx, end_idx = channel['start'], channel['end']
        high_line = channel['high_line']
        low_line = channel['low_line']
        msg = (
            f"Neuer Kanal erkannt: {channel['type'].capitalize()}\n"
            f"Start: Index {start_idx}, End: Index {end_idx}\n"
            f"Obere Begrenzung: y = {high_line[0]:.4f}*x + {high_line[1]:.2f}\n"
            f"Untere Begrenzung: y = {low_line[0]:.4f}*x + {low_line[1]:.2f}"
        )
        send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'), msg)
        logger.info(msg)
        # Automatische Trading-Logik: Entry am aktuellen Preis, Ziel ist das jeweils andere Kanalende
        current_idx = len(df) - 1
        current_price = df['close'].iloc[-1]
        # Berechne obere und untere Begrenzung am aktuellen Index
        high_now = high_line[0] * current_idx + high_line[1]
        low_now = low_line[0] * current_idx + low_line[1]
        # Wenn Preis nahe der unteren Begrenzung: Long bis obere Begrenzung
        if abs(current_price - low_now) < 0.01 * current_price:
            target = high_line[0] * current_idx + high_line[1]
            trade_type = 'long'
            # SL: etwas unterhalb der unteren Begrenzung, TP: obere Begrenzung
            sl = low_now - 0.003 * current_price
            tp = target
            amount = params.get('trade_amount', 0.1)  # Default: 0.1 Kontrakte
            try:
                order = exchange.create_order(
                    symbol=symbol,
                    side='buy',
                    type='market',
                    amount=amount,
                    params={
                        'stopLossPrice': round(sl, 4),
                        'takeProfitPrice': round(tp, 4)
                    }
                )
                trade_msg = (
                    f"LONG ausgeführt: Entry {current_price:.4f}, TP {tp:.4f}, SL {sl:.4f}\nOrder: {order}"
                )
            except Exception as e:
                trade_msg = f"LONG-Order fehlgeschlagen: {e}"
            send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'), trade_msg)
            logger.info(trade_msg)
        # Wenn Preis nahe der oberen Begrenzung: Short bis untere Begrenzung
        elif abs(current_price - high_now) < 0.01 * current_price:
            target = low_line[0] * current_idx + low_line[1]
            trade_type = 'short'
            # SL: etwas oberhalb der oberen Begrenzung, TP: untere Begrenzung
            sl = high_now + 0.003 * current_price
            tp = target
            amount = params.get('trade_amount', 0.1)
            try:
                order = exchange.create_order(
                    symbol=symbol,
                    side='sell',
                    type='market',
                    amount=amount,
                    params={
                        'stopLossPrice': round(sl, 4),
                        'takeProfitPrice': round(tp, 4)
                    }
                )
                trade_msg = (
                    f"SHORT ausgeführt: Entry {current_price:.4f}, TP {tp:.4f}, SL {sl:.4f}\nOrder: {order}"
                )
            except Exception as e:
                trade_msg = f"SHORT-Order fehlgeschlagen: {e}"
            send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'), trade_msg)
            logger.info(trade_msg)
        # Sonst: Kein Trade
        else:
            logger.info("Kein Trade: Preis nicht am Kanalrand.")
    logger.info(f">>> KBot-Lauf für {symbol} ({timeframe}) abgeschlossen <<<\n")

def main():
    parser = argparse.ArgumentParser(description="KBot Kanal-Trading-Skript")
    parser.add_argument('--symbol', required=True, type=str)
    parser.add_argument('--timeframe', required=True, type=str)
    args = parser.parse_args()
    symbol, timeframe = args.symbol, args.timeframe
    logger = setup_logging(symbol, timeframe)
    try:
        params = load_config(symbol, timeframe)
        with open(os.path.join(PROJECT_ROOT, 'secret.json'), "r") as f:
            secrets = json.load(f)
        accounts_to_run = secrets.get('kbot', [])
        telegram_config = secrets.get('telegram', {})
    except Exception as e:
        logger.critical(f"Kritischer Initialisierungs-Fehler: {e}", exc_info=True)
        sys.exit(1)
    for account in accounts_to_run:
        try:
            run_for_account(account, telegram_config, params, logger)
        except Exception as e:
            logger.error(f"Schwerwiegender Fehler bei Account {account.get('name', 'Unbenannt')}: {e}", exc_info=True)
if __name__ == "__main__":
    main()
