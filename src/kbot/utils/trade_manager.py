"""
trade_manager.py — ALP Trade Execution

Oeffnet Long-Positionen auf Bitget mit Market Order + SL/TP Trigger Orders.
Simulationsmodus: Loggt nur in CSV, fuehrt keine echten Orders aus.
"""
import csv
import logging
import os
from datetime import datetime

logger = logging.getLogger('kbot')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
TRADE_LOG = os.path.join(PROJECT_ROOT, 'logs', 'trades.csv')


def _log_trade(row: dict):
    os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
    write_header = not os.path.exists(TRADE_LOG)
    with open(TRADE_LOG, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def open_long(exchange, symbol: str, invest_usdt: float, risk: dict,
              simulation_mode: bool, logger=None) -> bool:
    """
    Oeffnet eine Long-Position auf Bitget.
    Gibt True zurueck bei Erfolg (oder Simulation), False bei Fehler.
    """
    if logger is None:
        logger = logging.getLogger('kbot')

    sl_pct = risk.get('stop_loss_pct', 2.0) / 100
    tp_pct = risk.get('take_profit_pct', 5.0) / 100
    leverage = int(risk.get('leverage', 3))

    try:
        ticker = exchange.fetch_ticker(symbol)
        if not ticker:
            logger.error(f"Kein Ticker fuer {symbol}")
            return False

        price = ticker.get('last') or ticker.get('close')
        if not price:
            logger.error(f"Kein Preis fuer {symbol}")
            return False

        position_value = invest_usdt * leverage
        amount = position_value / price
        sl_price = price * (1 - sl_pct)
        tp_price = price * (1 + tp_pct)

        row = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'side': 'long',
            'price': round(price, 6),
            'amount': round(amount, 6),
            'invest_usdt': invest_usdt,
            'leverage': leverage,
            'sl_price': round(sl_price, 6),
            'tp_price': round(tp_price, 6),
            'simulation': simulation_mode,
        }

        if simulation_mode:
            logger.info(
                f"[SIMULATION] LONG {symbol} @ {price:.4f} | "
                f"Amount: {amount:.4f} | SL: {sl_price:.4f} | TP: {tp_price:.4f}"
            )
            _log_trade(row)
            return True

        # --- Live Trading ---
        exchange.set_margin_mode(symbol, 'isolated')
        exchange.set_leverage(symbol, leverage)

        order = exchange.create_market_order(symbol, 'buy', amount)
        if not order:
            logger.error(f"Market Order fehlgeschlagen fuer {symbol}")
            return False

        actual_price = order.get('average') or price
        actual_sl = actual_price * (1 - sl_pct)
        actual_tp = actual_price * (1 + tp_pct)

        exchange.place_trigger_market_order(
            symbol, 'sell', amount, actual_sl,
            params={'reduceOnly': True, 'triggerType': 'mark_price'}
        )
        exchange.place_trigger_market_order(
            symbol, 'sell', amount, actual_tp,
            params={'reduceOnly': True, 'triggerType': 'mark_price'}
        )

        row.update({
            'price': round(actual_price, 6),
            'sl_price': round(actual_sl, 6),
            'tp_price': round(actual_tp, 6),
        })
        _log_trade(row)

        logger.info(
            f"LIVE LONG {symbol} @ {actual_price:.4f} | "
            f"SL: {actual_sl:.4f} | TP: {actual_tp:.4f}"
        )
        return True

    except Exception as e:
        logger.error(f"Fehler bei open_long({symbol}): {e}", exc_info=True)
        return False
