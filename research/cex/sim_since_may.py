"""100 USDT ab 2026-05-01, Signale exakt wie Primaer (>=500k, Short 60 min). Margin je Trade = Kapital/3 (bis 3 gleichzeitig)."""
import os, numpy as np, pandas as pd
from test import load, run, TOKENS, D
data = {t: load(t) for t in TOKENS if os.path.exists(os.path.join(D, 'deposits', f'{t}.json'))}
ev = run(data, 5e5, 60)
ev = ev[ev.t >= pd.Timestamp('2026-05-01', tz='UTC')].sort_values('t').reset_index(drop=True)
mae = []
for _, e in ev.iterrows():
    px = data[e.tok][0]; w = px[e.t:e.t + pd.Timedelta(minutes=60)]
    mae.append(w.max() / w.iloc[0] - 1)          # schlimmster Anstieg gegen den Short (Minutenschluss)
ev['mae'] = mae
ev['nur_wal'] = ev.cex == '-'
print(f"Signale seit 01.05.: {len(ev)} ({ev.nur_wal.sum()} von Wal-Adressen), Zeitraum bis {ev.t.max():%d.%m.}")
print(f"Schlimmster Anstieg waehrend eines Trades: {ev.mae.max()*100:.1f} % | >10 %: {(ev.mae > .10).sum()} Trades\n")

def sim(g, lev, cost, frac=1/3, min_notional=5.0):
    eq, peak, dd, n, liq, skipped = 100.0, 100.0, 0.0, 0, 0, 0
    month = {}
    for _, e in g.iterrows():
        margin = eq * frac; notional = margin * lev
        if notional < min_notional:
            skipped += 1; continue
        if e.mae >= 1 / lev * 0.9:                 # Liquidation (mit Puffer)
            pnl = -margin; liq += 1
        else:
            pnl = notional * (e.short - cost)
        eq += pnl; n += 1
        peak = max(peak, eq); dd = min(dd, eq / peak - 1)
        month[e.t.strftime('%Y-%m')] = eq
        if eq <= 1: break
    return eq, dd * 100, n, liq, month

rows = []
for name, g in [('alle Signale', ev), ('nur Wal-Absender', ev[ev.nur_wal])]:
    for cost_name, cost in [('Market 0,12 %', 0.0012), ('Limit 0,04 %', 0.0004)]:
        for lev in [1, 3, 5, 10]:
            eq, dd, n, liq, month = sim(g, lev, cost)
            rows.append((name, cost_name, lev, eq, dd, n, liq, month))
            print(f"{name:17s} | {cost_name:13s} | {lev:2d}x | 100 -> {eq:7.1f} USDT ({eq-100:+6.1f} %) | Max-DD {dd:6.1f} % | Trades {n} | Liq {liq}")
print("\nMonatsverlauf (Kapital am Monatsende):")
for name, cost_name, lev, eq, dd, n, liq, month in rows:
    if lev in (3,) :
        print(f"  {name:17s} {cost_name:13s} {lev}x: " + "  ".join(f"{m[5:]}: {v:.1f}" for m, v in month.items()))
