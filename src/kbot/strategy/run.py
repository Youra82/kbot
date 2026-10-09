"""
run.py — ALP Haupt-Loop (Dry-Run / Paper-Trading)

Pro Zyklus (poll_interval_seconds):
  1. Neue Ethereum-Bloecke scannen -> Bridge-Zufluesse je Ziel-Token speichern
  2. Paper-Positionen auf Ausstieg pruefen (SL / TP / Haltedauer)
  3. Nach jeder vollen Stunde: abgeschlossene Stunde mit signal.flow_events
     bewerten (identisch zu research/event_study.py) -> Paper-Long
"""
import csv
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd

from kbot.strategy.signal import hourly_flows, flow_events, baseline_at, BASELINE_HOURS
from kbot.utils.bridge_monitor import backfill
from kbot.utils.paper_trader import PaperTrader, summary
from kbot.utils.telegram import send_message

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
STATE_DIR = os.path.join(PROJECT_ROOT, 'artifacts', 'state')
FLOW_STORE = os.path.join(STATE_DIR, 'flows.csv')
SCANNER_STATE = os.path.join(STATE_DIR, 'scanner.json')
SIGNAL_LOG = os.path.join(PROJECT_ROOT, 'logs', 'signals.csv')
FLOW_FIELDS = ['ts', 'block', 'tx', 'src', 'dest', 'token', 'usd']
KEEP_DAYS = 40

logger = logging.getLogger('kbot')


def _utcnow():
    return datetime.now(timezone.utc)


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _append_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        if new:
            w.writeheader()
        w.writerows(rows)


def load_store() -> pd.DataFrame:
    if not os.path.exists(FLOW_STORE):
        return pd.DataFrame(columns=FLOW_FIELDS)
    df = pd.read_csv(FLOW_STORE)
    df['ts'] = pd.to_datetime(df['ts'], utc=True, format='ISO8601')
    return df


def trim_store(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df['ts'] >= _utcnow() - timedelta(days=KEEP_DAYS)]
    tmp = FLOW_STORE + '.tmp'
    out = df.copy()
    out['ts'] = out['ts'].map(lambda t: t.isoformat())
    out.to_csv(tmp, index=False)
    os.replace(tmp, FLOW_STORE)
    return df


def ensure_history(monitor, store: pd.DataFrame, settings: dict, log) -> pd.DataFrame:
    """Baseline braucht >= 14 Tage Historie. Fehlt sie, per Backfill nachladen (einmalig, ~20 min)."""
    need_days = settings.get('backfill_days', 31)
    have = store['ts'].min() if len(store) else None
    if have is not None and have <= _utcnow() - timedelta(days=need_days - 1):
        return store
    log.info(f"Flow-Historie unvollstaendig — Backfill {need_days} Tage (einmalig, dauert ~20 min)...")
    flows, latest = backfill(monitor.client, need_days, monitor.min_transfer, log)
    df = pd.DataFrame(flows)
    df['ts'] = pd.to_datetime(df['ts'], utc=True, format='ISO8601')
    store = pd.concat([df[FLOW_FIELDS], store]).drop_duplicates(['tx', 'src', 'usd', 'block'])
    store = trim_store(store)
    monitor.cursor = latest
    _save_json(SCANNER_STATE, {'cursor': latest})
    log.info(f"Backfill fertig: {len(store)} Fluesse, Cursor {latest}")
    return store


def evaluate_hour(store, hour, tokens, sig, paper, tg, log):
    k, A, H = sig['k'], sig['min_hour_flow_usd'], sig['hold_hours']
    start = hour - timedelta(hours=BASELINE_HOURS + 2 * H)
    for token in tokens:
        F = hourly_flows(store, token, start, hour)
        flow = float(F.iloc[-1])
        if flow <= 0:
            continue
        base = baseline_at(F, hour)
        ev = flow_events(F, k, A, H)
        hit = bool(ev) and ev[-1] == hour
        status = 'event' if hit else ('unter_schwelle' if flow < A or not (flow >= k * base) else 'sperre')
        if flow >= A * 0.5:
            _append_csv(SIGNAL_LOG, ['hour', 'token', 'flow_usd', 'baseline_usd', 'ratio', 'status'], [{
                'hour': hour.isoformat(), 'token': token, 'flow_usd': round(flow), 'baseline_usd': round(base or 0),
                'ratio': round(flow / base, 2) if base else '', 'status': status}])
        if not hit:
            continue
        if paper.has_position(token):
            log.info(f"Event {token} {hour:%H:%M}, aber Position offen — uebersprungen.")
            continue
        symbol = tokens[token]
        pos = paper.open(token, symbol, hour.isoformat(), flow, base)
        if pos:
            send_message(tg.get('bot_token'), tg.get('chat_id'),
                         f"🟡 <b>KBOT DRY-RUN — LONG {token}</b>\n"
                         f"Bridge-Zufluss {hour:%d.%m %H:00} UTC: <b>{flow / 1e6:.1f} Mio $</b>\n"
                         f"= {flow / base:.1f}x Stundenschnitt (30 T: {base / 1e6:.2f} Mio $)\n"
                         f"Einstieg {pos['entry']} | Ausstieg nach {H}h"
                         + (f" | SL {paper.sl}%" if paper.sl else "") + (f" | TP {paper.tp}%" if paper.tp else ""))


def daily_report(store, tokens, tg):
    since = _utcnow() - timedelta(days=1)
    d = store[(store['ts'] >= since) & store['token'].isin(list(tokens))]
    top = d.groupby('token')['usd'].sum().sort_values(ascending=False).head(8)
    s = summary()
    lines = [f"📊 <b>KBOT Tagesbericht</b> (Dry-Run)", "Bridge-Zufluesse 24h:"]
    lines += [f"  {t}: {v / 1e6:.1f} Mio $" for t, v in top.items()]
    if s['n']:
        lines.append(f"\nPaper-Trades: {s['n']} | Excess vs BTC Ø {s['excess_mean']:+.2f}% | "
                     f"WR {s['win_rate']:.0f}% | PnL {s['pnl_sum']:+.2f} USDT")
    else:
        lines.append("\nNoch keine abgeschlossenen Paper-Trades.")
    send_message(tg.get('bot_token'), tg.get('chat_id'), "\n".join(lines))


def run_alp_loop(monitor, exchange, settings, telegram_config, log):
    sig = settings['signal']
    poll = settings.get('poll_interval_seconds', 30)
    tokens = {t: f"{t}/USDT:USDT" for t in sig['tokens']}
    if exchange.markets:
        missing = [t for t, s in tokens.items() if s not in exchange.markets]
        for t in missing:
            log.warning(f"{tokens[t]} nicht auf Bitget — wird nicht gehandelt.")
            tokens.pop(t)

    def price(symbol):
        tk = exchange.fetch_ticker(symbol)
        return float(tk['last']) if tk and tk.get('last') else None

    paper = PaperTrader(price, settings.get('risk', {}), settings.get('invest_per_trade_usdt', 20), sig['hold_hours'])
    monitor.cursor = _load_json(SCANNER_STATE, {}).get('cursor')
    store = ensure_history(monitor, load_store(), settings, log)

    st = _load_json(os.path.join(STATE_DIR, 'loop.json'), {})
    last_eval = pd.Timestamp(st['last_eval']) if st.get('last_eval') else pd.Timestamp(_utcnow()).floor('h') - pd.Timedelta(hours=1)
    last_report = st.get('last_report', '')
    log.info(f"ALP Dry-Run gestartet | Tokens: {', '.join(tokens)} | k={sig['k']} A={sig['min_hour_flow_usd']:,.0f}$ "
             f"H={sig['hold_hours']}h | Cursor {monitor.cursor}")
    send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'),
                 f"▶️ KBOT Dry-Run gestartet\nTokens: {', '.join(tokens)}\n"
                 f"Signal: Stundenzufluss ≥ {sig['k']}x 30-T-Schnitt und ≥ {sig['min_hour_flow_usd'] / 1e6:.1f} Mio $")

    errors = 0
    while True:
        try:
            new = monitor.poll()
            _save_json(SCANNER_STATE, {'cursor': monitor.cursor})
            if new:
                _append_csv(FLOW_STORE, FLOW_FIELDS, new)
                df = pd.DataFrame(new)
                df['ts'] = pd.to_datetime(df['ts'], utc=True, format='ISO8601')
                store = pd.concat([store, df[FLOW_FIELDS]], ignore_index=True)
                for f in new:
                    if f['token'] in tokens and f['usd'] >= 1e6:
                        log.info(f"Fluss {f['usd']:,.0f} $ -> {f['token']} ({f['src']})")

            for row in paper.check_exits():
                send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'),
                             f"{'✅' if row['excess_pct'] > 0 else '❌'} <b>KBOT DRY-RUN CLOSE {row['token']}</b> ({row['reason']})\n"
                             f"Rendite {row['ret_pct']:+.2f}% | BTC {row['btc_ret_pct']:+.2f}% | "
                             f"Excess {row['excess_pct']:+.2f}%\nPaper-PnL {row['pnl_usdt']:+.2f} USDT")

            cur_hour = pd.Timestamp(_utcnow()).floor('h')
            # Stunde erst auswerten, wenn der Scanner sie vollstaendig gesehen hat (~1 min Puffer)
            if cur_hour - pd.Timedelta(hours=1) > last_eval and _utcnow() >= cur_hour + timedelta(minutes=1):
                hour = cur_hour - pd.Timedelta(hours=1)
                evaluate_hour(store, hour, tokens, sig, paper, telegram_config, log)
                last_eval = hour
                if hour.hour == 0:
                    store = trim_store(store)
            today = _utcnow().strftime('%Y-%m-%d')
            if _utcnow().hour >= settings.get('daily_report_hour_utc', 7) and last_report != today:
                daily_report(store, tokens, telegram_config)
                last_report = today
            _save_json(os.path.join(STATE_DIR, 'loop.json'), {'last_eval': last_eval.isoformat(), 'last_report': last_report})
            errors = 0
        except KeyboardInterrupt:
            log.info("ALP Loop durch Benutzer beendet.")
            break
        except Exception as e:
            errors += 1
            log.error(f"Fehler im ALP Loop ({errors}x in Folge): {e}", exc_info=errors == 1)
            if errors == 10:
                send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'),
                             f"⚠️ KBOT: 10 Fehler in Folge — {str(e)[:200]}")
        time.sleep(poll)
