#!/usr/bin/env python3
"""
master_runner.py — KBot (Dry-Run)

Entry point: laedt Konfiguration, verbindet alle Komponenten,
startet den kontinuierlichen ALP-Loop.
"""
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.utils.bridge_monitor import BridgeMonitor
from kbot.utils.exchange import Exchange
from kbot.strategy.run import run_alp_loop
from kbot.strategy.deposit_watch import run_deposit_watch
from kbot.utils.bridge_monitor import AlchemyClient


def setup_logging() -> logging.Logger:
    log_dir = os.path.join(PROJECT_ROOT, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'kbot.log')

    logger = logging.getLogger('kbot')
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        logger.addHandler(ch)

    return logger


def main():
    logger = setup_logging()

    settings_path = os.path.join(PROJECT_ROOT, 'settings.json')
    secret_path = os.path.join(PROJECT_ROOT, 'secret.json')

    with open(settings_path, 'r') as f:
        settings = json.load(f)
    with open(secret_path, 'r') as f:
        secrets = json.load(f)

    alchemy_key = secrets.get('alchemy_api_key', '')
    telegram_config = secrets.get('telegram', {})
    account_config = (secrets.get('kbot') or [{}])[0]

    if not settings.get('simulation_mode', True):
        logger.error("Live-Modus ist deaktiviert: erst Dry-Run-Vorwaertstest (siehe README). "
                     "simulation_mode=true setzen.")
        sys.exit(1)

    if not alchemy_key:
        logger.error("Kein Alchemy API-Key in secret.json! Bot kann nicht starten.")
        sys.exit(1)

    exchange = Exchange(account_config)   # nur oeffentliche Kurse im Dry-Run
    mode = settings.get('mode', 'deposits')
    print("=" * 60)
    if mode == 'deposits':
        cfg = settings['deposit_watch']
        print("  KBot — Wal-Einzahlungen auf Binance -> Short (DRY-RUN)")
        print(f"  Coins    : {len(cfg['tokens'])} ERC-20-Alts")
        print(f"  Signal   : Einzahlung >= {cfg['min_usd']:,.0f} $ an bekannte Binance-Adresse")
        print(f"  Paper    : {cfg['start_equity_usdt']} USDT | {cfg['leverage']}x | Margin {cfg['margin_fraction']:.0%} | "
              f"Short {cfg['hold_minutes']} min")
        print("=" * 60)
        run_deposit_watch(AlchemyClient(alchemy_key), exchange, settings, telegram_config, logger)
    elif mode == 'bridge':
        bw = settings['bridge_watch']
        print("  KBot — Bridge-Inflow (ARCHIV, Backtest widerlegt) — DRY-RUN")
        print("=" * 60)
        run_alp_loop(BridgeMonitor(alchemy_key, bw), exchange, bw, telegram_config, logger)
    else:
        logger.error(f"Unbekannter mode '{mode}' in settings.json (erlaubt: deposits, bridge).")
        sys.exit(1)


if __name__ == '__main__':
    main()
