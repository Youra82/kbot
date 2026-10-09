"""Auswertung gemaess PRAEREGISTRIERUNG.md (sha256 504b4591...)."""
import json, os, itertools
import numpy as np, pandas as pd
from collect import D, TOKENS, HOT, load_px

COST = 0.0012
EV_START = pd.Timestamp('2025-11-09', tz='UTC')
SPLIT = pd.Timestamp('2026-06-09', tz='UTC')
from kbot.utils.deposit_registry import sender_type
from kbot.strategy.deposit_signal import DepositRule, entry_minute  # gleiche Regel wie Live


def load(tok):
    px = load_px(tok)
    px = px.reindex(pd.date_range(px.index[0], px.index[-1], freq='min', tz='UTC')).ffill()
    sw = pd.DataFrame(json.load(open(os.path.join(D, 'sweeps', f'{tok}.json'))))
    sw['ts'] = pd.to_datetime(sw.ts, utc=True)
    dp = pd.DataFrame(json.load(open(os.path.join(D, 'deposits', f'{tok}.json'))))
    if len(dp):
        dp['ts'] = pd.to_datetime(dp.ts, utc=True)
        first = sw.groupby('from').ts.min()
        dp['known_since'] = dp.dep_addr.map(first)
        dp['usd'] = dp.value * px.reindex(dp.ts.dt.floor('min')).values
        dp['cex'] = dp.sender.map(sender_type)
    sw['usd'] = sw.value * px.reindex(sw.ts.dt.floor('min')).values
    return px, sw, dp


def run(tok_data, A, H, which='dep', filt=None):
    rows = []
    for tok, (px, sw, dp) in tok_data.items():
        ev = (dp if which == 'dep' else sw.rename(columns={'from': 'dep_addr'}))
        if not len(ev):
            continue
        ev = ev[(ev.usd >= A) & (ev.ts >= EV_START)].sort_values('ts')
        if filt is not None and which == 'dep':
            ev = ev[filt(ev)]
        short = -(px.shift(-H) / px - 1)
        base = {p: short[(short.index >= EV_START) & ((short.index >= SPLIT) if p else (short.index < SPLIT))].mean()
                for p in (False, True)}
        rule = DepositRule(A, H)
        last = None
        for _, e in ev.iterrows():
            if which == 'dep':
                if not rule.accept(tok, e.ts, e.usd, e.known_since):
                    continue
                t0 = entry_minute(e.ts)
            else:
                t0 = entry_minute(e.ts)
                if last is not None and t0 < last + pd.Timedelta(minutes=H):
                    continue
                last = t0
            if t0 not in short.index or np.isnan(short[t0]):
                continue
            oos = t0 >= SPLIT
            rows.append({'tok': tok, 't': t0, 'usd': e.usd, 'short': short[t0], 'diff': short[t0] - base[oos],
                         'oos': oos, 'cex': e.get('cex', '-')})
    return pd.DataFrame(rows)


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan


def line(name, ev):
    out = []
    for p, g in [('IS', ev[~ev.oos]), ('OOS', ev[ev.oos])] if len(ev) else []:
        out.append(f"{p} n={len(g):4d} Diff {g['diff'].mean()*100:+.3f}% t={tstat(g['diff']):+.2f} "
                   f"Short netto {(g.short - COST).mean()*100:+.3f}% WR {(g.short > COST).mean()*100:.0f}%")
    print(f"{name:30s} " + " | ".join(out))


if __name__ == '__main__':
    data = {t: load(t) for t in TOKENS if os.path.exists(os.path.join(D, 'deposits', f'{t}.json'))}
    known = [v[2][v[2].ts > v[2].known_since] for v in data.values() if len(v[2])]
    print(f"Tokens {len(data)} | Einzahlungen (bekannte Adressen) {sum(len(k) for k in known)} | >=500k: "
          f"{sum(int((k.usd >= 5e5).sum()) for k in known)}")
    print("\n=== PRIMAER: Einzahlung >= 500k $, Short 60 min ===")
    ev = run(data, 5e5, 60); line("PRIMAER", ev)
    if len(ev):
        print(ev.groupby('tok')['diff'].agg(['count', 'mean']).round(4).T.to_string())
    print("\n=== Sensitivitaet ===")
    for A, H in itertools.product([2.5e5, 5e5, 2e6], [15, 60, 240]):
        line(f"A={A/1e6:.2f}M H={H}", run(data, A, H))
    print("\n=== Sekundaer: Sweep-Zeitpunkt (alle Adressen) ===")
    for A, H in itertools.product([5e5, 2e6], [15, 60, 240]):
        line(f"Sweep A={A/1e6:.1f}M H={H}", run(data, A, H, which='sweep'))
    print("\n=== Beschreibend: Absender Boersen-Wallet vs. sonstige (A=500k, H=60) ===")
    line("Absender Boerse", run(data, 5e5, 60, filt=lambda e: e.cex != '-'))
    line("Absender sonstige", run(data, 5e5, 60, filt=lambda e: e.cex == '-'))
