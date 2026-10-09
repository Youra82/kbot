"""Daten fuer PRAEREGISTRIERUNG.md: Binance-1m-Kurse, Sweeps an Binance 14, Einzahlungen hinter grossen Sweeps."""
import io, json, os, sys, time, zipfile
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'src'))
from kbot.utils.bridge_monitor import AlchemyClient, BLOCKS_PER_HOUR

D = os.path.join(HERE, 'data'); os.makedirs(D, exist_ok=True)
from kbot.utils.deposit_registry import BINANCE_HOT as HOT, TOKENS  # gleiche Quelle wie Live-Waechter
PERP = {'PEPE': '1000PEPE', 'SHIB': '1000SHIB'}
PX_SCALE = {'PEPE': 1000, 'SHIB': 1000}   # 1000PEPE-Kontrakt: Preis je 1000 Token


def load_px(tok):
    """Preis je EINZELNEM Token (on-chain-Einheit)."""
    return pd.read_parquet(os.path.join(D, 'px', f'{tok}.parquet'))['c'] / PX_SCALE.get(tok, 1)
START, END = pd.Timestamp('2025-10-09', tz='UTC'), pd.Timestamp('2026-10-09', tz='UTC')
SWEEP_MIN_USD = 200_000


def prices(tok):
    p = os.path.join(D, 'px', f'{tok}.parquet')
    if os.path.exists(p):
        return
    sym = PERP.get(tok, tok) + 'USDT'
    urls = [f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{m:%Y-%m}.zip"
            for m in pd.date_range('2025-10-01', '2026-09-01', freq='MS')]
    urls += [f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/1m/{sym}-1m-{d:%Y-%m-%d}.zip"
             for d in pd.date_range('2026-10-01', '2026-10-08', freq='D')]
    fr = []
    for u in urls:
        for i in range(4):
            try:
                r = requests.get(u, timeout=60); break
            except Exception:
                time.sleep(3 * (i + 1))
        if r.status_code != 200:
            print(f'  {tok}: fehlt {u.rsplit("/", 1)[1]}', flush=True); continue
        z = zipfile.ZipFile(io.BytesIO(r.content)); x = pd.read_csv(z.open(z.namelist()[0]), header=None)
        if not str(x.iloc[0, 0]).isdigit():
            x = x.iloc[1:]
        fr.append(x.iloc[:, [0, 4]])
    df = pd.concat(fr); df.columns = ['t', 'c']
    df = df.astype(float); df['t'] = pd.to_datetime(df.t.astype('int64'), unit='ms', utc=True)
    df = df.drop_duplicates('t').set_index('t').sort_index()
    os.makedirs(os.path.dirname(p), exist_ok=True); df.to_parquet(p)
    print(f'Kurse {tok}: {len(df)} Minuten {df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d}', flush=True)


def transfers(c, q, max_pages=100000):
    out, pk, n = [], None, 0
    while True:
        qq = dict(q)
        if pk:
            qq['pageKey'] = pk
        r = c.call("alchemy_getAssetTransfers", [qq], retries=8)
        out += r['transfers']; pk = r.get('pageKey'); n += 1
        if not pk or n >= max_pages:
            return out


def sweeps(c, tok, frm, to):
    p = os.path.join(D, 'sweeps', f'{tok}.json')
    if os.path.exists(p):
        return
    t = transfers(c, {"fromBlock": hex(frm), "toBlock": hex(to), "toAddress": HOT, "contractAddresses": [TOKENS[tok]],
                      "category": ["erc20"], "withMetadata": True, "maxCount": "0x3e8", "excludeZeroValue": True})
    rows = [{'from': x['from'], 'ts': x['metadata']['blockTimestamp'], 'block': int(x['blockNum'], 16),
             'value': float(x['value'] or 0), 'tx': x['hash'], 'asset': x.get('asset')} for x in t]
    os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(rows, open(p, 'w'))
    assets = {r['asset'] for r in rows}
    print(f'Sweeps {tok}: {len(rows)} (Symbol laut Chain: {assets})', flush=True)


def deposits(c, tok):
    """Einzahlungen hinter jedem Sweep >= SWEEP_MIN_USD (zwischen vorigem Sweep derselben Adresse und diesem)."""
    p = os.path.join(D, 'deposits', f'{tok}.json')
    if os.path.exists(p):
        return
    sw = pd.DataFrame(json.load(open(os.path.join(D, 'sweeps', f'{tok}.json'))))
    px = load_px(tok)
    sw['ts'] = pd.to_datetime(sw.ts, utc=True)
    sw = sw.sort_values('block')
    sw['prev_block'] = sw.groupby('from').block.shift(1)
    sw['usd'] = sw.value * px.reindex(sw.ts.dt.floor('min'), method='ffill').values
    big = sw[sw.usd >= SWEEP_MIN_USD]
    rows, seen = [], set()

    def one(r):
        frm = int(r.prev_block) + 1 if not np.isnan(r.prev_block) else r.block - 3 * 24 * BLOCKS_PER_HOUR
        return transfers(c, {"fromBlock": hex(frm), "toBlock": hex(int(r.block)), "toAddress": r['from'],
                             "contractAddresses": [TOKENS[tok]], "category": ["erc20"], "withMetadata": True,
                             "maxCount": "0x3e8", "excludeZeroValue": True}, max_pages=3)
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(one, [r for _, r in big.iterrows()]))
    for (_, r), t in zip(big.iterrows(), res):
        for x in t:
            if x['hash'] in seen:
                continue
            seen.add(x['hash'])
            rows.append({'dep_addr': r['from'], 'sender': x['from'], 'ts': x['metadata']['blockTimestamp'],
                         'block': int(x['blockNum'], 16), 'value': float(x['value'] or 0), 'tx': x['hash']})
    os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(rows, open(p, 'w'))
    print(f'Einzahlungen {tok}: {len(big)} grosse Sweeps -> {len(rows)} Einzahlungen', flush=True)


if __name__ == '__main__':
    s = json.load(open(os.path.join(HERE, '..', '..', 'secret.json')))
    c = AlchemyClient(s['alchemy_api_key'])
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(prices, list(TOKENS) + ['BTC']))
    latest = int(c.call("eth_blockNumber", []), 16)
    frm = latest - int((pd.Timestamp.now(tz='UTC') - START).total_seconds() / 12)
    for tok in TOKENS:
        try:
            sweeps(c, tok, frm, latest)
            deposits(c, tok)
        except Exception as e:
            print(f'FEHLER {tok}: {str(e)[:200]}', flush=True)
    print('FERTIG', flush=True)
