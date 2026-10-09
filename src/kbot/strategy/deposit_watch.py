"""
deposit_watch.py — Dry-Run-Waechter: Wal-Einzahlung auf Binance -> Paper-Short auf Bitget.

Pro Zyklus (poll_interval_seconds):
  1. Neue Ethereum-Bloecke: Sweeps lernen, Einzahlungen an bekannte Binance-Adressen finden
  2. USD-Wert (Bitget-Kurs) -> DepositRule (identisch zu research/cex/test.py)
  3. Einstieg zum Schluss der Minute floor(Blockzeit)+1 (wie Backtest), Paper-Short 60 min
  4. Ausstiege pruefen, Telegram, Tagesbericht
"""
import csv
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd

from kbot.strategy.deposit_signal import DepositRule, entry_minute
from kbot.utils.deposit_monitor import AddressBook, DepositScanner
from kbot.utils.paper_short import PaperShort, summary
from kbot.utils.telegram import send_message

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
STATE = os.path.join(PROJECT_ROOT, 'artifacts', 'state')
BOOK_FILE = os.path.join(STATE, 'deposit_addresses.json')
LOOP_FILE = os.path.join(STATE, 'deposit_loop.json')
POS_FILE = os.path.join(STATE, 'paper_shorts.json')
TRADE_LOG = os.path.join(PROJECT_ROOT, 'logs', 'paper_shorts.csv')
DEPOSIT_LOG = os.path.join(PROJECT_ROOT, 'logs', 'deposits.csv')
DEP_FIELDS = ['ts', 'token', 'amount', 'usd', 'sender_type', 'sender', 'dep_addr', 'known_since', 'status', 'tx']

logger = logging.getLogger('kbot')


def _now():
    return datetime.now(timezone.utc)


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _log_deposit(row):
    os.makedirs(os.path.dirname(DEPOSIT_LOG), exist_ok=True)
    new = not os.path.exists(DEPOSIT_LOG)
    with open(DEPOSIT_LOG, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=DEP_FIELDS, extrasaction='ignore')
        if new:
            w.writeheader()
        w.writerow(row)


def _tg(tg, text):
    send_message(tg.get('bot_token'), tg.get('chat_id'), text)


def _balance_line(paper):
    """Realisierte Kontostaende beider Paper-Konten + offene Shorts (offene Trades noch nicht eingerechnet)."""
    return (f"💰 Konto Limit {paper.equity['limit']:.2f} USDT | Market {paper.equity['market']:.2f} USDT | "
            f"offene Shorts: {len(paper.positions)}")


def _close_message(rows):
    r0 = rows[0]
    if all(r['status'] == 'missed' for r in rows):
        return f"⏸ KBOT DRY-RUN — {r0['token']}: Limit-Einstieg nicht gefuellt (Market-Vergleich laeuft weiter)"
    lines = [f"<b>KBOT DRY-RUN — {r0['token']} Short beendet</b>"]
    for r in rows:
        if r['status'] == 'missed':
            lines.append(f"Limit: Einstieg nicht gefuellt (kein Trade)")
        else:
            icon = '✅' if r['pnl_usdt'] > 0 else '❌'
            lines.append(f"{icon} {r['account'].capitalize()}: {r['ret_pct']:+.2f}% ({r['status']}) | "
                         f"{r['pnl_usdt']:+.2f} USDT -> Konto {r['equity_after']:.2f}")
    return "\n".join(lines)


def daily_report(tg, n_book, paper=None):
    s = summary(TRADE_LOG)
    lines = ["📊 <b>KBOT Tagesbericht</b> (Dry-Run, Wal-Einzahlungen)", f"Bekannte Binance-Adressen: {n_book:,}"]
    for acc, label in (('limit', 'Limit (5x, Maker)'), ('market', 'Market (5x, Taker)')):
        v = s.get(acc)
        if v and v['equity'] is not None:
            lines.append(f"{label}: {v['equity']:.2f} USDT | Trades {v['trades']} | Gewinner {v['win']} | "
                         f"verpasst {v['missed']}")
    if len(lines) == 2:
        lines.append("Noch keine abgeschlossenen Trades.")
    if paper is not None:
        lines.append(_balance_line(paper))
    _tg(tg, "\n".join(lines))


def run_deposit_watch(client, exchange, settings, tg, log):
    cfg = settings['deposit_watch']
    poll = cfg.get('poll_interval_seconds', 15)

    def ticker(symbol):
        t = exchange.fetch_ticker(symbol)
        return {'bid': t.get('bid'), 'ask': t.get('ask'), 'last': t.get('last')} if t else None

    def ohlcv(symbol, since_ms):
        try:
            return exchange.exchange.fetch_ohlcv(symbol, '1m', since=since_ms, limit=200)
        except Exception as e:
            log.error(f"OHLCV {symbol}: {e}")
            return []

    book = AddressBook(BOOK_FILE)
    st = _load(LOOP_FILE, {})
    scanner = DepositScanner(client, book, cursor=st.get('cursor'), max_catchup=cfg.get('max_catchup_blocks', 600))
    if len(book) == 0:
        days = cfg.get('backfill_days', 60)
        _tg(tg, f"⏳ KBOT: baue Binance-Adressbuch auf ({days} Tage Sweeps, einmalig ~20–40 min)...")
        scanner.cursor = book.backfill(client, days, log)

    rule = DepositRule(cfg.get('min_usd', 500_000), cfg.get('hold_minutes', 60))
    rule.last_entry = {k: pd.Timestamp(v) for k, v in st.get('last_entry', {}).items()}
    paper = PaperShort(ticker, ohlcv, POS_FILE, TRADE_LOG, start_equity=cfg.get('start_equity_usdt', 100.0),
                       leverage=cfg.get('leverage', 5), margin_frac=cfg.get('margin_fraction', 1 / 3),
                       hold_minutes=cfg.get('hold_minutes', 60), fill_window_minutes=cfg.get('limit_fill_minutes', 2))
    pending = st.get('pending', [])
    last_report = st.get('last_report', '')
    symbols = {t: f"{t}/USDT:USDT" for t in cfg['tokens']}

    log.info(f"Wal-Einzahlungs-Waechter gestartet | {len(symbols)} Tokens | Adressbuch {len(book):,} | "
             f"Schwelle {rule.min_usd:,.0f} $ | Short {cfg.get('hold_minutes', 60)} min | Hebel {paper.lev:g}x")
    _tg(tg, f"▶️ <b>KBOT Dry-Run gestartet</b> — Wal-Einzahlungen auf Binance\n"
            f"Signal: Einzahlung ≥ {rule.min_usd / 1e6:.1f} Mio $ an bekannte Binance-Adresse → Short "
            f"{cfg.get('hold_minutes', 60)} min auf Bitget\nPaper: {paper.equity['limit']:.2f} USDT, "
            f"{paper.lev:g}x, Margin {paper.frac:.0%} je Trade | {len(symbols)} Coins")

    errors = 0
    while True:
        try:
            for d in scanner.poll():
                if d['token'] not in symbols:
                    continue
                tk = ticker(symbols[d['token']])
                px = tk.get('last') if tk else None
                d['usd'] = d['amount'] * px if px else None
                ok = rule.accept(d['token'], d['ts'], d['usd'], d['known_since'])
                if d['usd'] and d['usd'] >= 100_000:
                    _log_deposit({**d, 'usd': round(d['usd']), 'status': 'signal' if ok else 'unter_schwelle_oder_sperre'})
                if ok:
                    enter_at = entry_minute(d['ts']) + pd.Timedelta(minutes=1)     # Schluss der Einstiegsminute
                    pending.append({**d, 'enter_at': enter_at.isoformat()})
                    log.info(f"SIGNAL {d['token']}: {d['amount']:,.0f} ({d['usd']:,.0f} $) -> Binance, "
                             f"Absender {d['sender_type']}, Einstieg {enter_at:%H:%M:%S} UTC")
            for p in list(pending):
                if _now() >= datetime.fromisoformat(p['enter_at']):
                    pending.remove(p)
                    pos = paper.open(p, symbols[p['token']])
                    if pos:
                        who = 'Wal' if p['sender_type'] == '-' else p['sender_type']
                        _tg(tg, f"🔴 <b>KBOT DRY-RUN — SHORT {p['token']}</b>\n"
                                f"Einzahlung auf Binance: {p['amount']:,.0f} {p['token']} = <b>{p['usd'] / 1e6:.2f} Mio $</b> "
                                f"(Absender: {who})\nLimit @ {pos['limit']['price']} | Market @ {pos['market']['price']}\n"
                                f"Ausstieg in {cfg.get('hold_minutes', 60)} min\n{_balance_line(paper)}")
            groups = {}
            for row in paper.check():
                groups.setdefault((row['token'], row['signal_ts']), []).append(row)
            for (tok, sts), rows in groups.items():
                if any(r['account'] == 'market' for r in rows) or all(r['status'] == 'missed' for r in rows):
                    _tg(tg, _close_message(rows) + "\n" + _balance_line(paper))
            today = _now().strftime('%Y-%m-%d')
            if _now().hour >= cfg.get('daily_report_hour_utc', 7) and last_report != today:
                daily_report(tg, len(book), paper)
                last_report = today
            _save(LOOP_FILE, {'cursor': scanner.cursor, 'pending': pending, 'last_report': last_report,
                              'last_entry': {k: v.isoformat() for k, v in rule.last_entry.items()}})
            errors = 0
        except KeyboardInterrupt:
            log.info("Waechter durch Benutzer beendet.")
            break
        except Exception as e:
            errors += 1
            log.error(f"Fehler im Waechter ({errors}x in Folge): {e}", exc_info=errors == 1)
            if errors == 10:
                _tg(tg, f"⚠️ KBOT: 10 Fehler in Folge — {str(e)[:200]}")
        time.sleep(poll)
