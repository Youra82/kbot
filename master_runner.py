#!/usr/bin/env python3
"""
master_runner.py — KBot Agentic Liquidity Pulse (ALP)

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
from kbot.utils.sentiment import SentimentGuard
from kbot.utils.exchange import Exchange
from kbot.strategy.run import run_alp_loop


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
    cryptopanic_key = secrets.get('cryptopanic_api_key', '')
    telegram_config = secrets.get('telegram', {})
    account_config = secrets.get('kbot', [{}])[0]

    mode = "SIMULATION" if settings.get('simulation_mode', True) else "LIVE"
    bridges = settings.get('bridges', {})

    print("=" * 55)
    print("  KBot — Agentic Liquidity Pulse (ALP)")
    print(f"  Modus    : {mode}")
    print(f"  Bridges  : {', '.join(b['name'] for b in bridges.values())}")
    print(f"  Poll     : {settings.get('poll_interval_seconds', 30)}s")
    print(f"  Cooldown : {settings.get('cooldown_minutes', 60)} min")
    print("=" * 55)

    if not alchemy_key:
        logger.error("Kein Alchemy API-Key in secret.json! Bot kann nicht starten.")
        sys.exit(1)

    monitor = BridgeMonitor(alchemy_key, settings)
    guard = SentimentGuard(cryptopanic_key, settings.get('sentiment', {}))
    exchange = Exchange(account_config)

    run_alp_loop(monitor, guard, exchange, settings, telegram_config, logger)


if __name__ == '__main__':
    main()
