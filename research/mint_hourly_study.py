"""H-M2 gemaess PREREG_MINTS.md: USDC-Mints + USDT-Treasury-Auszahlungen (Ethereum, stuendlich) -> BTC/ETH."""
import json, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from kbot.utils.bridge_monitor import AlchemyClient, BLOCKS_PER_HOUR

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"; USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
ZERO = "0x0000000000000000000000000000000000000000"
TETHER_TREASURY = "0x5754284f345afc66a98fbb0a0afe71e0f007b949"
COST = 0.0012


def collect(client, days=365):
    p = os.path.join(D, 'mints.json')
    if os.path.exists(p):
        return json.load(open(p))
    latest = int(client.call("eth_blockNumber", []), 16)
    frm = latest - days * 24 * BLOCKS_PER_HOUR
    out = []
    for name, fa, tok in [('usdc_mint', ZERO, USDC), ('usdt_treasury', TETHER_TREASURY, USDT)]:
        pk = None
        while True:
            q = {"fromBlock": hex(frm), "toBlock": hex(latest), "fromAddress": fa, "contractAddresses": [tok],
                 "category": ["erc20"], "withMetadata": True, "maxCount": "0x3e8", "excludeZeroValue": True}
            if pk:
                q["pageKey"] = pk
            res = client.call("alchemy_getAssetTransfers", [q], retries=6)
            out += [{'src': name, 'ts': t['metadata']['blockTimestamp'], 'usd': float(t['value'] or 0), 'to': t['to']}
                    for t in res['transfers']]
            pk = res.get('pageKey')
            if not pk:
                break
        print(name, sum(1 for o in out if o['src'] == name), flush=True)
    json.dump(out, open(p, 'w'))
    return out


def tstat(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan


if __name__ == '__main__':
    s = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'secret.json')))
    rows = collect(AlchemyClient(s['alchemy_api_key']))
    df = pd.DataFrame(rows); df['ts'] = pd.to_datetime(df['ts'], utc=True)
    # Treasury -> Treasury/Burn-Ruecklaeufe ausschliessen
    df = df[~df['to'].str.lower().isin([ZERO, TETHER_TREASURY])]
    print(df.groupby('src').usd.agg(['count', 'sum']).assign(sum=lambda x: (x['sum'] / 1e9).round(1)))
    t0, t1 = df.ts.min().floor('h'), df.ts.max().floor('h')
    idx = pd.date_range(t0, t1, freq='h', tz='UTC')
    F = df.groupby(df.ts.dt.floor('h')).usd.sum().reindex(idx, fill_value=0.0)
    split = t0 + (t1 - t0) * (8 / 12)
    for tok in ['BTC', 'ETH']:
        px = pd.read_csv(os.path.join(D, 'prices', f'{tok}.csv'), index_col=0, parse_dates=True)['o']
        for A in [2e7, 5e7, 2e8]:
            for H in [24, 72]:
                fwd = (px.shift(-(H + 1)) / px.shift(-1) - 1)
                cand = F[F >= A].index
                ev, last = [], None
                for t in cand:
                    if last is None or t >= last + pd.Timedelta(hours=H):
                        ev.append(t); last = t
                out = []
                for name, sel in [('IS', lambda i: i < split), ('OOS', lambda i: i >= split)]:
                    e = [t for t in ev if sel(t) and t in fwd.index and not np.isnan(fwd[t])]
                    b = fwd[(fwd.index >= t0) & sel(fwd.index)].mean()
                    diff = fwd[e] - b
                    out.append(f"{name} n={len(e):3d} Diff {diff.mean()*100:+5.2f}% t={tstat(diff):+.2f}")
                tag = ' <- PRIMAER' if (A == 5e7 and H == 24) else ''
                print(f"{tok} A={A/1e6:4.0f}M H={H}h | " + " | ".join(out) + tag)
