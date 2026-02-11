import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data
from kbot.strategy.peak_trough import is_peak, is_trough

symbol = 'ETH/USDT:USDT'
timeframe = '2h'
start_date = '2023-01-01'
end_date = '2026-02-11'

data = load_data(symbol, timeframe, start_date, end_date)
if data.empty:
    print('Keine Daten')
    raise SystemExit(1)

# Build ohlcv list
ohlcv = []
for idx,row in data.tail(500).iterrows():
    ohlcv.append((int(idx.timestamp()), float(row['open']), float(row['high']), float(row['low']), float(row['close']), float(row.get('volume',0))))

for n in [3,4,5,6]:
    peaks = [i for i in range(len(ohlcv)) if is_peak(ohlcv, i, n)]
    troughs = [i for i in range(len(ohlcv)) if is_trough(ohlcv, i, n)]
    print(f'n={n}: peaks={len(peaks)}, troughs={len(troughs)}')
    if peaks:
        print('  last peaks (idx,close):', [(p, ohlcv[p][4]) for p in peaks[-5:]])
    if troughs:
        print('  last troughs (idx,close):', [(t, ohlcv[t][4]) for t in troughs[-5:]])
