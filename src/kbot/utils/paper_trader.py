"""
paper_trader.py — Dry-Run-Positionen mit echtem Ausstieg (SL / TP / Zeit) und PnL.

Der alte Simulationsmodus loggte nur Einstiege — Signalqualitaet war nie messbar.
Jede Position wird hier bis zum Ausstieg verfolgt; Excess-Return gegen BTC
wird mitgeschrieben (identisch zur Event-Study in research/).
"""
import csv
import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger('kbot')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
STATE_FILE = os.path.join(PROJECT_ROOT, 'artifacts', 'state', 'paper_positions.json')
TRADE_LOG = os.path.join(PROJECT_ROOT, 'logs', 'paper_trades.csv')
FEE_ROUNDTRIP = 0.0012

FIELDS = ['token', 'symbol', 'signal_hour', 'entry_time', 'entry', 'btc_entry', 'exit_time', 'exit', 'btc_exit',
          'reason', 'ret_pct', 'btc_ret_pct', 'excess_pct', 'pnl_usdt', 'invest_usdt', 'leverage', 'flow_usd',
          'baseline_usd']


def _now():
    return datetime.now(timezone.utc)


class PaperTrader:
    def __init__(self, price_fn, risk: dict, invest_usdt: float, hold_hours: int):
        self.price = price_fn                   # symbol -> float
        self.sl = risk.get('stop_loss_pct')     # None = kein SL (Event-Study ist Zeit-Exit)
        self.tp = risk.get('take_profit_pct')
        self.lev = float(risk.get('leverage', 1))
        self.invest = float(invest_usdt)
        self.hold = timedelta(hours=hold_hours)
        self.positions = self._load()

    def _load(self):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        tmp = STATE_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.positions, f, indent=2)
        os.replace(tmp, STATE_FILE)

    def has_position(self, token: str) -> bool:
        return token in self.positions

    def open(self, token: str, symbol: str, signal_hour: str, flow_usd: float, baseline_usd: float):
        entry = self.price(symbol)
        btc = self.price('BTC/USDT:USDT')
        if not entry or not btc:
            logger.error(f"Paper-Open {symbol}: kein Preis")
            return None
        pos = {'token': token, 'symbol': symbol, 'signal_hour': signal_hour, 'entry_time': _now().isoformat(),
               'entry': entry, 'btc_entry': btc, 'flow_usd': round(flow_usd), 'baseline_usd': round(baseline_usd),
               'due': (_now() + self.hold).isoformat()}
        self.positions[token] = pos
        self._save()
        logger.info(f"[PAPER] LONG {symbol} @ {entry} | Flow {flow_usd:,.0f} $ vs Baseline {baseline_usd:,.0f} $")
        return pos

    def check_exits(self) -> list:
        closed = []
        for token, p in list(self.positions.items()):
            px = self.price(p['symbol'])
            if not px:
                continue
            ret = px / p['entry'] - 1
            reason = None
            if self.sl is not None and ret <= -self.sl / 100:
                reason = 'SL'
            elif self.tp is not None and ret >= self.tp / 100:
                reason = 'TP'
            elif _now() >= datetime.fromisoformat(p['due']):
                reason = 'TIME'
            if reason:
                closed.append(self._close(token, px, reason))
        return closed

    def _close(self, token, px, reason):
        p = self.positions.pop(token)
        btc = self.price('BTC/USDT:USDT') or p['btc_entry']
        ret = px / p['entry'] - 1
        bret = btc / p['btc_entry'] - 1
        row = {**{k: p.get(k) for k in FIELDS if k in p}, 'exit_time': _now().isoformat(), 'exit': px,
               'btc_exit': btc, 'reason': reason, 'ret_pct': round((ret - FEE_ROUNDTRIP) * 100, 3),
               'btc_ret_pct': round(bret * 100, 3), 'excess_pct': round((ret - bret - FEE_ROUNDTRIP) * 100, 3),
               'pnl_usdt': round(self.invest * self.lev * (ret - FEE_ROUNDTRIP), 3),
               'invest_usdt': self.invest, 'leverage': self.lev}
        os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
        new = not os.path.exists(TRADE_LOG)
        with open(TRADE_LOG, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
        self._save()
        logger.info(f"[PAPER] CLOSE {p['symbol']} {reason} | {row['ret_pct']:+.2f}% | Excess {row['excess_pct']:+.2f}%")
        return row


def summary() -> dict:
    """Kennzahlen aller geschlossenen Paper-Trades."""
    if not os.path.exists(TRADE_LOG):
        return {'n': 0}
    with open(TRADE_LOG) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return {'n': 0}
    ex = [float(r['excess_pct']) for r in rows]
    pnl = [float(r['pnl_usdt']) for r in rows]
    return {'n': len(rows), 'excess_mean': sum(ex) / len(ex), 'win_rate': sum(e > 0 for e in ex) / len(ex) * 100,
            'pnl_sum': sum(pnl)}
