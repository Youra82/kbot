import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data
from kbot.strategy.peak_trough import generate_signal

symbol = 'ETH/USDT:USDT'
timeframe = '2h'
start_date = '2023-01-01'
end_date = '2026-02-11'

data = load_data(symbol, timeframe, start_date, end_date)
if data.empty:
    print('Keine Daten')
    raise SystemExit(1)

ohlcv = []
for idx,row in data.tail(500).iterrows():
    ohlcv.append((int(idx.timestamp()), float(row['open']), float(row['high']), float(row['low']), float(row['close']), float(row.get('volume',0))))

config = {'lookback_n':3, 'reversal_threshold_pct':0.2, 'atr_period':7, 'atr_mult':1.0, 'risk_reward_ratio':1.5}
res = generate_signal(ohlcv, config)
print('generate_signal result:', res)
