"""
paper_short.py — Dry-Run-Shorts auf Bitget mit zwei Paper-Konten.

  limit : Einstieg Sell-Limit am Ask, Ausstieg Buy-Limit am Bid (Maker 0,02 % je Seite).
          Gefuellt nur, wenn Bitget-1m-Hoch/-Tief den Limitpreis im Fenster erreicht;
          sonst: Einstieg verpasst (kein Trade) bzw. Ausstieg per Market (Taker 0,06 %).
  market: Einstieg am Bid, Ausstieg am Ask (Taker 0,06 % je Seite) — Vergleich.
Liquidation: Hoechstkurs waehrend der Haltedauer >= Einstieg * (1 + 0,9/Hebel) -> Margin verloren.
"""
import csv
import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger('kbot')

MAKER, TAKER = 0.0002, 0.0006
FIELDS = ['account', 'token', 'symbol', 'signal_ts', 'usd', 'sender_type', 'entry_time', 'entry', 'exit_time', 'exit',
          'status', 'ret_pct', 'margin', 'pnl_usdt', 'equity_after', 'tx']


def _now():
    return datetime.now(timezone.utc)


class PaperShort:
    def __init__(self, ticker_fn, ohlcv_fn, state_path, trade_log, start_equity=100.0, leverage=5,
                 margin_frac=1 / 3, hold_minutes=60, fill_window_minutes=2):
        self.ticker = ticker_fn            # symbol -> {'bid','ask','last'}
        self.ohlcv = ohlcv_fn              # (symbol, since_ms) -> [[ts,o,h,l,c,v], ...] 1m
        self.state_path, self.trade_log = state_path, trade_log
        self.lev, self.frac = float(leverage), float(margin_frac)
        self.hold = timedelta(minutes=hold_minutes)
        self.window = timedelta(minutes=fill_window_minutes)
        st = self._load()
        self.equity = st.get('equity', {'limit': start_equity, 'market': start_equity})
        self.positions = st.get('positions', [])

    # --- Zustand ---
    def _load(self):
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp = self.state_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'equity': self.equity, 'positions': self.positions}, f, indent=2)
        os.replace(tmp, self.state_path)

    def open_tokens(self):
        return {p['token'] for p in self.positions}

    # --- Oeffnen ---
    def open(self, sig: dict, symbol: str):
        tk = self.ticker(symbol)
        if not tk or not tk.get('bid') or not tk.get('ask'):
            logger.error(f"Paper-Short {symbol}: kein Bid/Ask")
            return None
        now = _now()
        pos = {'token': sig['token'], 'symbol': symbol, 'signal_ts': sig['ts'], 'usd': round(sig['usd']),
               'sender_type': sig['sender_type'], 'tx': sig['tx'], 'opened': now.isoformat(),
               'due': (now + self.hold).isoformat(),
               'limit': {'price': float(tk['ask']), 'state': 'pending',
                         'margin': self.equity['limit'] * self.frac},
               'market': {'price': float(tk['bid']), 'state': 'open',
                          'margin': self.equity['market'] * self.frac}}
        self.positions.append(pos)
        self._save()
        logger.info(f"[PAPER] SHORT {symbol} | Limit @ {pos['limit']['price']} | Market @ {pos['market']['price']} "
                    f"| Einzahlung {sig['usd']:,.0f} $")
        return pos

    # --- Pruefen ---
    def _bars(self, symbol, start):
        bars = self.ohlcv(symbol, int(start.timestamp() * 1000)) or []
        return [b for b in bars if b[0] >= int(start.timestamp() * 1000) // 60000 * 60000]

    def check(self) -> list:
        closed, now = [], _now()
        for p in list(self.positions):
            opened = datetime.fromisoformat(p['opened'])
            due = datetime.fromisoformat(p['due'])
            L, M = p['limit'], p['market']
            # 1) Limit-Einstieg: gefuellt, wenn Hoch im Fenster den Ask-Limitpreis erreicht
            if L['state'] == 'pending' and now >= opened + self.window:
                bars = [b for b in self._bars(p['symbol'], opened) if b[0] < (opened + self.window).timestamp() * 1000]
                L['state'] = 'open' if bars and max(b[2] for b in bars) >= L['price'] else 'missed'
                logger.info(f"[PAPER] {p['symbol']} Limit-Einstieg {'GEFUELLT' if L['state'] == 'open' else 'VERPASST'}")
                if L['state'] == 'missed':
                    closed.append(self._record(p, 'limit', None, 'missed', None, 0.0))
                self._save()
            if now < due:
                continue
            # 2) Ablauf: Market sofort schliessen, Limit-Buy am Bid stellen
            tk = None
            if M['state'] == 'open' or L['state'] == 'open':
                tk = self.ticker(p['symbol'])
                if not tk or not tk.get('ask'):
                    continue
                high = max([b[2] for b in self._bars(p['symbol'], opened)] or [0.0])
            if M['state'] == 'open':
                closed.append(self._close(p, 'market', high, float(tk['ask']), 2 * TAKER))
            if L['state'] == 'open':
                if high >= L['price'] * (1 + 0.9 / self.lev):
                    closed.append(self._close(p, 'limit', high, None, 0))
                else:
                    L['state'], L['exit_limit'], L['exit_due'] = 'exiting', float(tk['bid']), (now + self.window).isoformat()
            # 3) Limit-Ausstieg: gefuellt, wenn Tief den Bid-Limitpreis erreicht, sonst Market am Ask
            if L['state'] == 'exiting' and now >= datetime.fromisoformat(L['exit_due']):
                start = datetime.fromisoformat(L['exit_due']) - self.window
                bars = [b for b in self._bars(p['symbol'], start) if b[0] < datetime.fromisoformat(L['exit_due']).timestamp() * 1000]
                if bars and min(b[3] for b in bars) <= L['exit_limit']:
                    closed.append(self._close(p, 'limit', 0, L['exit_limit'], 2 * MAKER))
                else:
                    tk = self.ticker(p['symbol'])
                    if not tk or not tk.get('ask'):
                        continue
                    closed.append(self._close(p, 'limit', 0, float(tk['ask']), MAKER + TAKER))
            if M['state'] in ('closed', 'liquidated') and L['state'] in ('closed', 'liquidated', 'missed'):
                self.positions.remove(p)
            self._save()
        return closed

    def _close(self, p, acc, high, exit_px, fee):
        a = p[acc]
        if high and high >= a['price'] * (1 + 0.9 / self.lev):
            a['state'] = 'liquidated'
            return self._record(p, acc, high, 'liquidated', -1.0, -a['margin'])
        ret = (a['price'] - exit_px) / a['price'] - fee
        a['state'] = 'closed'
        return self._record(p, acc, exit_px, 'closed', ret, a['margin'] * self.lev * ret)

    def _record(self, p, acc, exit_px, status, ret, pnl):
        self.equity[acc] = self.equity[acc] + pnl
        a = p[acc]
        row = {'account': acc, 'token': p['token'], 'symbol': p['symbol'], 'signal_ts': p['signal_ts'], 'usd': p['usd'],
               'sender_type': p['sender_type'], 'entry_time': p['opened'], 'entry': a['price'],
               'exit_time': _now().isoformat(), 'exit': exit_px, 'status': status,
               'ret_pct': None if ret is None else round(ret * 100, 4), 'margin': round(a['margin'], 4),
               'pnl_usdt': round(pnl, 4), 'equity_after': round(self.equity[acc], 4), 'tx': p['tx']}
        os.makedirs(os.path.dirname(self.trade_log), exist_ok=True)
        new = not os.path.exists(self.trade_log)
        with open(self.trade_log, 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)
        logger.info(f"[PAPER] {acc.upper()} {p['symbol']} {status} | {row['ret_pct']}% | Konto {self.equity[acc]:.2f} USDT")
        return row


def summary(trade_log) -> dict:
    if not os.path.exists(trade_log):
        return {}
    with open(trade_log) as f:
        rows = list(csv.DictReader(f))
    out = {}
    for acc in ('limit', 'market'):
        r = [x for x in rows if x['account'] == acc]
        done = [x for x in r if x['status'] in ('closed', 'liquidated')]
        out[acc] = {'trades': len(done), 'missed': sum(x['status'] == 'missed' for x in r),
                    'win': sum(float(x['pnl_usdt']) > 0 for x in done),
                    'equity': float(r[-1]['equity_after']) if r else None}
    return out
