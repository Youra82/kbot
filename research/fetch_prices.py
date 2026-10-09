"""1h-Kerzen (Binance USDT-M Futures, oeffentlich) fuer die Tokens der Ziel-Chains."""
import os, time, requests
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'prices')
SYMS = ['BTC', 'ETH', 'ARB', 'OP', 'SOL', 'AVAX', 'POL', 'APT', 'HYPE', 'BNB', 'MNT', 'BERA', 'SUI', 'SEI', 'S', 'XPL', 'LINEA', 'WLD', 'UNI']
DAYS = 400


def fetch(sym):
    url = 'https://fapi.binance.com/fapi/v1/klines'
    end = int(time.time() * 1000)
    start = end - DAYS * 86400_000
    rows, cur = [], start
    while cur < end:
        r = requests.get(url, params={'symbol': f'{sym}USDT', 'interval': '1h', 'startTime': cur, 'limit': 1500}, timeout=30)
        if r.status_code != 200:
            print(sym, r.status_code, r.text[:100]); return None
        b = r.json()
        if not b:
            break
        rows += b
        nxt = b[-1][0] + 3600_000
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(0.15)
    df = pd.DataFrame(rows, columns=list('tohlcv') + ['ct', 'qv', 'n', 'tb', 'tq', 'x'])[list('tohlcv')]
    df = df.drop_duplicates('t').astype(float)
    df['t'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    return df.set_index('t')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for s in SYMS:
        df = fetch(s)
        if df is None or df.empty:
            continue
        # Luecken pruefen (stille Paginierungsfehler)
        gaps = (df.index.to_series().diff() > pd.Timedelta('1h')).sum()
        df.to_csv(os.path.join(OUT, f'{s}.csv'))
        print(f'{s}: {len(df)} Kerzen {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d %H:%M}, Luecken: {gaps}', flush=True)
