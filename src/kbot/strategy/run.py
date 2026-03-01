"""
run.py — ALP Haupt-Strategie-Loop

Polling-Schleife:
  1. Ethereum Bridge-Flows scannen (Alchemy)
  2. Sentiment-Check (CryptoPanic)
  3. Cooldown pruefen
  4. Trade ausfuehren (Bitget)
  5. Telegram-Benachrichtigung
"""
import csv
import logging
import os
import time
from datetime import datetime

from kbot.utils.trade_manager import open_long
from kbot.utils.telegram import send_message

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SIGNAL_LOG = os.path.join(PROJECT_ROOT, 'logs', 'signals.csv')


def _log_signal(row: dict):
    os.makedirs(os.path.dirname(SIGNAL_LOG), exist_ok=True)
    write_header = not os.path.exists(SIGNAL_LOG)
    with open(SIGNAL_LOG, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(row)

logger = logging.getLogger('kbot')


def run_alp_loop(monitor, guard, exchange, settings, telegram_config, logger):
    poll_interval = settings.get('poll_interval_seconds', 30)
    cooldown_minutes = settings.get('cooldown_minutes', 60)
    invest_usdt = settings.get('invest_per_trade_usdt', 100)
    simulation_mode = settings.get('simulation_mode', True)
    risk = settings.get('risk', {
        'stop_loss_pct': 2.0,
        'take_profit_pct': 5.0,
        'leverage': 3,
        'max_daily_trades': 5
    })
    max_daily = risk.get('max_daily_trades', 5)

    bot_token = telegram_config.get('bot_token', '')
    chat_id = telegram_config.get('chat_id', '')

    cooldowns = {}  # symbol -> datetime of last trade
    daily = {'date': datetime.now().date(), 'count': 0}

    logger.info(
        f"ALP Loop gestartet | Poll: {poll_interval}s | "
        f"Cooldown: {cooldown_minutes}min | "
        f"Modus: {'SIMULATION' if simulation_mode else 'LIVE'}"
    )

    while True:
        try:
            today = datetime.now().date()
            if daily['date'] != today:
                daily = {'date': today, 'count': 0}

            if daily['count'] >= max_daily:
                logger.info(f"Tageslimit erreicht ({max_daily} Trades) — warte bis morgen.")
                time.sleep(poll_interval)
                continue

            signals = monitor.scan_bridge_flows()

            for signal in signals:
                symbol = signal['symbol']
                bridge_name = signal['bridge_name']
                inflow_usd = signal['inflow_usd']
                stablecoin = signal['stablecoin']

                # Signal dokumentieren
                signal_row = {
                    'timestamp': datetime.now().isoformat(),
                    'bridge': bridge_name,
                    'symbol': symbol,
                    'inflow_usd': round(inflow_usd, 0),
                    'stablecoin': stablecoin,
                    'tx_hash': signal.get('tx_hash', ''),
                    'status': '',
                }

                # Cooldown pruefen
                last = cooldowns.get(symbol)
                if last:
                    elapsed = (datetime.now() - last).total_seconds()
                    if elapsed < cooldown_minutes * 60:
                        remaining = cooldown_minutes - elapsed / 60
                        logger.info(f"Cooldown fuer {symbol}: noch {remaining:.0f} min.")
                        signal_row['status'] = 'cooldown'
                        _log_signal(signal_row)
                        continue

                # Sentiment-Check
                if not guard.is_safe_to_trade(bridge_name, symbol):
                    msg = (
                        f"🛑 <b>ALP BLOCKIERT</b>\n"
                        f"{inflow_usd:,.0f} {stablecoin} → {bridge_name}\n"
                        f"Sentiment-Check negativ — Trade abgebrochen."
                    )
                    send_message(bot_token, chat_id, msg)
                    signal_row['status'] = 'sentiment_blocked'
                    _log_signal(signal_row)
                    continue

                # Trade ausfuehren
                logger.info(
                    f"Signal: {inflow_usd:,.0f} {stablecoin} → {bridge_name} | "
                    f"Trade: LONG {symbol}"
                )
                result = open_long(exchange, symbol, invest_usdt, risk, simulation_mode, logger)

                if result:
                    cooldowns[symbol] = datetime.now()
                    daily['count'] += 1
                    signal_row['status'] = 'traded'
                    msg = (
                        f"{'🟡 SIMULATION' if simulation_mode else '✅ LIVE'} <b>ALP Trade</b>\n"
                        f"<b>LONG {symbol}</b>\n"
                        f"Signal: {inflow_usd:,.0f} {stablecoin} → {bridge_name}\n"
                        f"Invest: {invest_usdt} USDT | Hebel: {risk.get('leverage', 3)}x\n"
                        f"SL: {risk.get('stop_loss_pct', 2.0)}% | "
                        f"TP: {risk.get('take_profit_pct', 5.0)}%\n"
                        f"Trades heute: {daily['count']}/{max_daily}"
                    )
                    send_message(bot_token, chat_id, msg)
                else:
                    signal_row['status'] = 'trade_failed'

                _log_signal(signal_row)

        except KeyboardInterrupt:
            logger.info("ALP Loop durch Benutzer beendet.")
            break
        except Exception as e:
            logger.error(f"Fehler im ALP Loop: {e}", exc_info=True)

        time.sleep(poll_interval)
