"""NACHTRAG (nicht praeregistriert, nur Pruefung des bestandenen Primaers A=500k H=60)."""
import numpy as np, pandas as pd
from test import load, run, tstat, COST, SPLIT, TOKENS, D
import os
data = {t: load(t) for t in TOKENS if os.path.exists(os.path.join(D, 'deposits', f'{t}.json'))}
ev = run(data, 5e5, 60)
btc = pd.read_parquet(os.path.join(D, 'px', 'BTC.parquet'))['c']
btc = btc.reindex(pd.date_range(btc.index[0], btc.index[-1], freq='min', tz='UTC')).ffill()
bshort = -(btc.shift(-60) / btc - 1)
ev['btc_short'] = bshort.reindex(ev.t).values
ev['ex'] = ev.short - ev.btc_short          # Short Alt, Long BTC (marktneutral)
pre = []
for _, e in ev.iterrows():
    px = data[e.tok][0]
    a, b = e.t - pd.Timedelta(minutes=61), e.t - pd.Timedelta(minutes=1)
    pre.append(px.get(b, np.nan) / px.get(a, np.nan) - 1)
ev['pre60'] = pre
for p, g in [('IS', ev[~ev.oos]), ('OOS', ev[ev.oos])]:
    h = g.groupby(g.t.dt.floor('h'))['diff'].mean()
    print(f"{p}: n={len(g)} | Median Diff {g['diff'].median()*100:+.3f}% | Cluster/Stunde t={tstat(h):+.2f} (n={len(h)}) | "
          f"marktneutral (vs BTC) {g.ex.mean()*100:+.3f}% t={tstat(g.ex):+.2f} | Kurs 60 min VOR Einstieg {g.pre60.mean()*100:+.3f}%")
    loo = {t: g[g.tok != t]['diff'].mean() * 100 for t in g.tok.unique()}
    w = min(loo, key=loo.get)
    print(f"     ohne staerksten Coin ({w}): Diff {loo[w]:+.3f}% | Coins mit Diff>0: {(g.groupby('tok')['diff'].mean() > 0).sum()}/{g.tok.nunique()}")
    q = g.assign(q=pd.qcut(g.usd, 3, labels=['klein', 'mittel', 'gross'])).groupby('q', observed=True)['diff'].agg(['count', 'mean'])
    print("     nach Groesse:", ", ".join(f"{i} {v*100:+.2f}% ({n})" for i, (n, v) in q.iterrows()))
ev.to_csv(os.path.join(D, 'events_primary.csv'), index=False)
