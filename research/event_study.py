"""Event-Study gemaess PREREG.md: Bridge-Inflow (Ethereum -> Chain X) -> Forward-Return Token X."""
import json, os, itertools
import numpy as np
import pandas as pd

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
COST = 0.0012

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from kbot.utils.bridge_registry import token_of  # gleiche Zuordnung wie Live-Bot
from kbot.strategy.signal import hourly_flows, flow_events  # gleiches Signal wie Live-Bot


def load_flows():
    rows = [json.loads(l) for l in open(os.path.join(D, 'transfers.jsonl'))]
    dest = json.load(open(os.path.join(D, 'dest.json')))
    out = []
    unk = {}
    for r in rows:
        if r.get('empty') or r['value'] < 100_000:
            continue
        d = dest.get(r['tx'])
        tok = token_of(r['src'], d)
        if tok is None:
            unk[d] = unk.get(d, 0) + r['value']
            continue
        out.append((pd.Timestamp(r['ts']), tok, r['value']))
    df = pd.DataFrame(out, columns=['ts', 'token', 'usd'])
    df['h'] = df['ts'].dt.floor('h')
    return df, unk


def load_px(tok):
    p = os.path.join(D, 'prices', f'{tok}.csv')
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    return df['o']


def fwd(px, t, H):
    t0 = t + pd.Timedelta(hours=1)
    t1 = t0 + pd.Timedelta(hours=H)
    if t0 not in px.index or t1 not in px.index:
        return np.nan
    return px[t1] / px[t0] - 1


def tstat(x):
    x = np.asarray(x); x = x[~np.isnan(x)]
    if len(x) < 3:
        return np.nan
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def run(flows, k, A, H, split):
    btc = load_px('BTC')
    res = []
    for tok, g in flows.groupby('token'):
        px = load_px(tok)
        if px is None:
            continue
        # erst ab Beginn der Bridge-Daten, sonst kuenstliche Null-Baseline
        F = hourly_flows(flows, tok, max(px.index[0], flows.ts.min()), px.index[-1])
        for t in flow_events(F, k, A, H):
            r = fwd(px, t, H); b = fwd(btc, t, H)
            res.append({'tok': tok, 't': t, 'raw': r - COST, 'ex': r - b - COST, 'oos': t >= split})
    return pd.DataFrame(res)


def summarize(ev):
    out = {}
    for name, g in [('IS', ev[~ev.oos]), ('OOS', ev[ev.oos])]:
        out[name] = dict(n=len(g), ex=g.ex.mean() * 100, t_ex=tstat(g.ex), raw=g.raw.mean() * 100,
                         t_raw=tstat(g.raw), wr=(g.ex > 0).mean() * 100 if len(g) else np.nan)
    return out


if __name__ == '__main__':
    flows, unk = load_flows()
    print(f"Zufluesse >=100k zugeordnet: {len(flows)} | {flows.usd.sum()/1e9:.1f} Mrd $ | "
          f"{flows.ts.min():%Y-%m-%d} .. {flows.ts.max():%Y-%m-%d}")
    print("Nicht zugeordnet (Top):", sorted(((v / 1e6, k) for k, v in unk.items()), reverse=True)[:8])
    print(flows.groupby('token').usd.agg(['count', 'sum']).sort_values('sum', ascending=False)
          .assign(sum=lambda x: (x['sum'] / 1e6).round(0)).to_string())
    t_min = flows.ts.min()
    split = t_min + (flows.ts.max() - t_min) * (8 / 12)
    print(f"IS/OOS-Grenze: {split:%Y-%m-%d}")

    # Baseline: unbedingte Excess-Rendite derselben Tokens (Sanity-Check gegen Drift)
    print("\n=== PRIMAER k=3, A=1M, H=24 ===")
    ev = run(flows, 3, 1e6, 24, split)
    s = summarize(ev)
    for kk, v in s.items():
        print(f"{kk:4s} n={v['n']:4d}  ex={v['ex']:+.3f}% t={v['t_ex']:+.2f}  raw={v['raw']:+.3f}% t={v['t_raw']:+.2f}  WR={v['wr']:.0f}%")
    print(ev.groupby(['tok', 'oos']).ex.agg(['count', 'mean']).unstack().round(4).to_string())
    ev.to_csv(os.path.join(D, 'events_primary.csv'), index=False)

    print("\n=== SENSITIVITAET (27 Varianten) ===")
    rows = []
    for k, A, H in itertools.product([2, 3, 5], [3e5, 1e6, 3e6], [4, 24, 72]):
        s = summarize(run(flows, k, A, H, split))
        rows.append(dict(k=k, A=A / 1e6, H=H, n_is=s['IS']['n'], ex_is=s['IS']['ex'], t_is=s['IS']['t_ex'],
                         n_oos=s['OOS']['n'], ex_oos=s['OOS']['ex'], t_oos=s['OOS']['t_ex'], raw_oos=s['OOS']['raw']))
    tab = pd.DataFrame(rows)
    print(tab.round(3).to_string(index=False))
    passed = tab[(tab.t_is >= 2) & (tab.t_oos >= 1.5) & (tab.raw_oos > 0) & (tab.n_oos >= 30)]
    print(f"\nVarianten mit Bestehen IS t>=2 & OOS t>=1.5: {len(passed)}/27")
    print(f"Varianten mit IS t>=2: {(tab.t_is >= 2).sum()} | mit IS t<=-2: {(tab.t_is <= -2).sum()}")
    tab.to_csv(os.path.join(D, 'sensitivity.csv'), index=False)
