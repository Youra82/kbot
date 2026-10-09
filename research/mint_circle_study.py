"""Nachtrag (Abweichung von PREREG_MINTS, strengere Messlatte): nur Circle-Primaeremission 0x55fe..44b8, brutto + netto."""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from kbot.utils.bridge_monitor import AlchemyClient, BLOCKS_PER_HOUR
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
CIRCLE = "0x55fe002aeff02f77364de339a1292923a15844b8"; USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
ZERO = "0x0000000000000000000000000000000000000000"

def burns(client):
    p = os.path.join(D, 'circle_burns.json')
    if os.path.exists(p): return json.load(open(p))
    latest = int(client.call("eth_blockNumber", []), 16); frm = latest - 365 * 24 * BLOCKS_PER_HOUR
    out, pk = [], None
    while True:
        q = {"fromBlock": hex(frm), "toBlock": hex(latest), "fromAddress": CIRCLE, "toAddress": ZERO, "contractAddresses": [USDC],
             "category": ["erc20"], "withMetadata": True, "maxCount": "0x3e8", "excludeZeroValue": True}
        if pk: q["pageKey"] = pk
        r = client.call("alchemy_getAssetTransfers", [q], retries=6)
        out += [{'ts': t['metadata']['blockTimestamp'], 'usd': float(t['value'] or 0)} for t in r['transfers']]
        pk = r.get('pageKey')
        if not pk: break
    json.dump(out, open(p, 'w')); return out

def tstat(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan

s = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'secret.json')))
m = pd.DataFrame(json.load(open(os.path.join(D, 'mints.json'))))
m = m[(m.src == 'usdc_mint') & (m.to.str.lower() == CIRCLE)]
b = pd.DataFrame(burns(AlchemyClient(s['alchemy_api_key'])))
for d in (m, b): d['ts'] = pd.to_datetime(d['ts'], utc=True)
print(f"Circle-Mints {len(m)} / {m.usd.sum()/1e9:.0f} Mrd | Burns {len(b)} / {b.usd.sum()/1e9:.0f} Mrd")
t0 = min(m.ts.min(), b.ts.min()).floor('h'); t1 = max(m.ts.max(), b.ts.max()).floor('h')
idx = pd.date_range(t0, t1, freq='h', tz='UTC')
G = m.groupby(m.ts.dt.floor('h')).usd.sum().reindex(idx, fill_value=0.0)
N = G - b.groupby(b.ts.dt.floor('h')).usd.sum().reindex(idx, fill_value=0.0)
split = t0 + (t1 - t0) * (8 / 12)
for tok in ['BTC', 'ETH']:
    px = pd.read_csv(os.path.join(D, 'prices', f'{tok}.csv'), index_col=0, parse_dates=True)['o']
    for nm, F in [('brutto', G), ('netto', N), ('netto24h', N.rolling(24).sum())]:
        for A in [5e7, 2e8, 5e8]:
            for H in [24, 72]:
                fwd = px.shift(-(H + 1)) / px.shift(-1) - 1
                ev, last = [], None
                for t in F[F >= A].index:
                    if last is None or t >= last + pd.Timedelta(hours=H): ev.append(t); last = t
                out = []
                for name, sel in [('IS', lambda i: i < split), ('OOS', lambda i: i >= split)]:
                    e = [t for t in ev if sel(t) and t in fwd.index and not np.isnan(fwd[t])]
                    base = fwd[(fwd.index >= t0) & sel(fwd.index)].mean(); diff = fwd[e] - base
                    out.append(f"{name} n={len(e):3d} Diff {diff.mean()*100:+5.2f}% t={tstat(diff):+.2f}")
                print(f"{tok} {nm:8s} A={A/1e6:4.0f}M H={H}h | " + " | ".join(out))
