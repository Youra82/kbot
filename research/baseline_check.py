"""Vergleich: Event-Excess vs. unbedingter Excess derselben Tokens/Perioden (Drift-Kontrolle)."""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from event_study import load_flows, run, load_px, COST, tstat

flows, _ = load_flows()
t0 = flows.ts.min(); split = t0 + (flows.ts.max() - t0) * (8 / 12)
btc = load_px('BTC')
for k, A, H in [(3, 1e6, 24), (3, 1e6, 4), (3, 1e6, 72), (5, 3e6, 24)]:
    ev = run(flows, k, A, H, split)
    out = []
    for oos in (False, True):
        e = ev[ev.oos == oos]
        # unbedingter Excess jedes Tokens in derselben Periode, gewichtet nach Event-Anzahl
        base = []
        for tok, n in e.tok.value_counts().items():
            px = load_px(tok)
            r = px.shift(-H - 1) / px.shift(-1) - 1
            b = btc.shift(-H - 1) / btc.shift(-1) - 1
            x = (r - b.reindex(r.index)).dropna()
            x = x[(x.index >= t0) & ((x.index >= split) if oos else (x.index < split))]
            base.append((x.mean() - COST, n))
        bm = sum(m * n for m, n in base) / sum(n for _, n in base)
        diff = e.ex - bm
        out.append(f"{'OOS' if oos else 'IS '} n={len(e):4d} Event {e.ex.mean()*100:+.3f}%  Zufall {bm*100:+.3f}%  "
                   f"Differenz {diff.mean()*100:+.3f}% t={tstat(diff):+.2f}")
    print(f"k={k} A={A/1e6:.0f}M H={H}h"); [print("   " + o) for o in out]
