"""H-M1 gemaess PREREG_MINTS.md: taegliche Stablecoin-Neuemission (DefiLlama) -> BTC-Forward-Return."""
import json, os, time
import numpy as np, pandas as pd, requests

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
COST = 0.0012


def btc_daily():
    p = os.path.join(D, 'prices', 'BTC_1d.csv')
    if os.path.exists(p):
        return pd.read_csv(p, index_col=0, parse_dates=True)['c']
    rows, cur = [], int(pd.Timestamp('2017-09-01', tz='UTC').timestamp() * 1000)
    while True:
        b = requests.get('https://api.binance.com/api/v3/klines',
                         params={'symbol': 'BTCUSDT', 'interval': '1d', 'startTime': cur, 'limit': 1000}, timeout=30).json()
        if not b:
            break
        rows += b; cur = b[-1][0] + 86400_000
        if len(b) < 1000:
            break
        time.sleep(0.2)
    s = pd.Series([float(r[4]) for r in rows], index=pd.to_datetime([r[0] for r in rows], unit='ms', utc=True))
    s = s[~s.index.duplicated()]
    s.to_frame('c').to_csv(p)
    return s


def tstat(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 2 else np.nan


if __name__ == '__main__':
    raw = json.load(open(os.path.join(D, 'llama_stables_all.json')))
    sup = pd.Series({pd.Timestamp(int(r['date']), unit='s', tz='UTC'): r['totalCirculatingUSD'].get('peggedUSD', np.nan)
                     for r in raw}).sort_index()
    sup = sup[sup.index >= '2019-06-01']
    btc = btc_daily()
    # Close des Datums-Tages d (Kerze d schliesst d+1 00:00) = 24h nach Stempel -> kein Lookahead
    dS = sup.diff()
    sd = dS.shift(1).rolling(90, min_periods=60).std()
    split = pd.Timestamp('2024-01-01', tz='UTC')
    print(f"Supply-Daten {sup.index[0]:%Y-%m-%d} .. {sup.index[-1]:%Y-%m-%d}, BTC {btc.index[0]:%Y-%m-%d} ..")
    for k in [1.5, 2, 3]:
        for H in [3, 7, 14]:
            fwd = btc.shift(-H) / btc - 1          # Close d -> Close d+H
            cand = dS[(dS >= k * sd) & (dS > 0)].index
            ev, last = [], None
            for t in cand:
                if last is None or t >= last + pd.Timedelta(days=H):
                    ev.append(t); last = t
            ev = [t for t in ev if t in fwd.index and not np.isnan(fwd[t])]
            out = []
            for name, sel in [('IS', lambda t: t < split), ('OOS', lambda t: t >= split)]:
                e = [t for t in ev if sel(t)]
                base_idx = [t for t in fwd.dropna().index if sel(t) and t >= sd.dropna().index[0]]
                base = fwd[base_idx].mean()
                diff = fwd[e] - base
                out.append(f"{name} n={len(e):3d} Event {fwd[e].mean()*100:+6.2f}% Basis {base*100:+5.2f}% "
                           f"Diff {diff.mean()*100:+6.2f}% t={tstat(diff):+.2f}")
            tag = ' <- PRIMAER' if (k == 2 and H == 7) else ''
            print(f"k={k} H={H:2d}d | " + " | ".join(out) + tag)
