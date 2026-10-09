import os, sys
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from kbot.strategy.deposit_signal import DepositRule, entry_minute
from kbot.utils.deposit_monitor import AddressBook, DepositScanner
from kbot.utils.deposit_registry import BINANCE_HOT, TOKENS
from kbot.utils.bridge_registry import TRANSFER_TOPIC
from kbot.utils import paper_short as ps

T0 = pd.Timestamp('2026-10-01 12:00:30', tz='UTC')


def test_entry_minute_matches_backtest():
    assert entry_minute(T0) == pd.Timestamp('2026-10-01 12:01', tz='UTC')


def test_rule_threshold_known_and_lockout():
    r = DepositRule(500_000, 60)
    known = T0 - pd.Timedelta(days=1)
    assert not r.accept('LINK', T0, 400_000, known)                 # unter Schwelle
    assert not r.accept('LINK', T0, 600_000, None)                  # Adresse unbekannt
    assert not r.accept('LINK', T0, 600_000, T0 + pd.Timedelta(1, 'min'))  # erst spaeter bekannt
    assert r.accept('LINK', T0, 600_000, known)
    assert not r.accept('LINK', T0 + pd.Timedelta(minutes=30), 9e6, known)  # Sperre 60 min
    assert r.accept('UNI', T0 + pd.Timedelta(minutes=30), 9e6, known)       # anderer Token frei
    assert r.accept('LINK', T0 + pd.Timedelta(minutes=61), 9e6, known)


def _log(token, frm, to, amount_wei, block, idx=0):
    pad = lambda a: '0x' + '0' * 24 + a[2:]
    return {'address': TOKENS[token], 'topics': [TRANSFER_TOPIC, pad(frm), pad(to)], 'data': hex(amount_wei),
            'blockNumber': hex(block), 'logIndex': hex(idx), 'transactionHash': f'0x{block:x}{idx}'}


def test_scanner_learns_sweeps_then_detects_deposits(tmp_path):
    book = AddressBook(str(tmp_path / 'book.json'))
    sc = DepositScanner(client=None, book=book)
    sc.decimals = {TOKENS['LINK']: 18}
    dep, whale = '0x' + 'a' * 40, '0x' + 'b' * 40
    ts = lambda b: f'2026-10-01T12:{b % 60:02d}:00+00:00'
    # Einzahlung VOR erstem Sweep -> unbekannt -> nicht erkannt; dann Sweep lernt Adresse
    out = sc.classify([_log('LINK', whale, dep, 10 ** 18 * 5, 1), _log('LINK', dep, BINANCE_HOT, 10 ** 18 * 5, 2)], ts)
    assert out == [] and book.known_since(dep) == ts(2)
    out = sc.classify([_log('LINK', whale, dep, 10 ** 18 * 70_000, 3)], ts)
    assert len(out) == 1 and out[0]['amount'] == 70_000 and out[0]['known_since'] == ts(2)
    assert out[0]['sender_type'] == '-'


class FakeEx:
    def __init__(self, bid, ask, bars):
        self.bid, self.ask, self.bars = bid, ask, bars

    def ticker(self, s):
        return {'bid': self.bid, 'ask': self.ask, 'last': (self.bid + self.ask) / 2}

    def ohlcv(self, s, since):
        return [b for b in self.bars if b[0] >= since // 60000 * 60000]


def _paper(tmp_path, ex):
    return ps.PaperShort(ex.ticker, ex.ohlcv, str(tmp_path / 'p.json'), str(tmp_path / 't.csv'),
                         start_equity=100, leverage=5, margin_frac=1 / 3, hold_minutes=60, fill_window_minutes=2)


def _bars(start, highs, lows):
    s = int(start.timestamp() * 1000) // 60000 * 60000
    return [[s + i * 60000, 0, h, l, 0, 0] for i, (h, l) in enumerate(zip(highs, lows))]


SIG = {'token': 'LINK', 'ts': T0.isoformat(), 'usd': 1e6, 'sender_type': '-', 'tx': '0x1'}


def test_limit_filled_and_profit(tmp_path, monkeypatch):
    now = datetime(2026, 10, 1, 12, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(ps, '_now', lambda: now)
    ex = FakeEx(9.99, 10.0, _bars(now, [10.01] * 3 + [9.5] * 70, [9.9] * 3 + [9.4] * 70))
    p = _paper(tmp_path, ex); p.open(SIG, 'LINK/USDT:USDT')
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=3)); p.check()
    assert p.positions[0]['limit']['state'] == 'open'
    ex.bid, ex.ask = 9.5, 9.51
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=61)); rows = p.check()
    assert {r['account'] for r in rows} == {'market'}                        # Limit-Ausstieg wartet
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=64)); rows = p.check()
    lim = rows[0]
    assert lim['account'] == 'limit' and lim['status'] == 'closed'
    assert lim['ret_pct'] == pytest.approx(((10.0 - 9.5) / 10.0 - 0.0004) * 100, abs=1e-3)
    assert p.equity['limit'] > 100 and p.positions == []


def test_limit_missed_market_still_trades(tmp_path, monkeypatch):
    now = datetime(2026, 10, 1, 12, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(ps, '_now', lambda: now)
    ex = FakeEx(9.99, 10.0, _bars(now, [9.98] * 70, [9.8] * 70))           # erreicht Ask nie
    p = _paper(tmp_path, ex); p.open(SIG, 'LINK/USDT:USDT')
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=3)); rows = p.check()
    assert rows[0]['status'] == 'missed' and p.equity['limit'] == 100
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=61)); rows = p.check()
    assert rows[0]['account'] == 'market' and p.positions == []


def test_liquidation(tmp_path, monkeypatch):
    now = datetime(2026, 10, 1, 12, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(ps, '_now', lambda: now)
    ex = FakeEx(9.99, 10.0, _bars(now, [10.01, 10.0, 12.0] + [10.0] * 70, [9.9] * 73))   # +20 % gegen Short
    p = _paper(tmp_path, ex); p.open(SIG, 'LINK/USDT:USDT')
    monkeypatch.setattr(ps, '_now', lambda: now + timedelta(minutes=61)); rows = p.check()
    assert all(r['status'] == 'liquidated' for r in rows)
    assert p.equity['market'] == pytest.approx(100 - 100 / 3)


def test_balance_line_shows_both_accounts(tmp_path):
    from kbot.strategy.deposit_watch import _balance_line
    ex = FakeEx(9.99, 10.0, [])
    p = _paper(tmp_path, ex)
    p.equity = {'limit': 104.37, 'market': 101.92}
    assert _balance_line(p) == "💰 Konto Limit 104.37 USDT | Market 101.92 USDT | offene Shorts: 0"
