import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data

symbol = 'ETH/USDT:USDT'
timeframe = '2h'
start_date = '2023-01-01'
end_date = '2026-02-11'

data = load_data(symbol, timeframe, start_date, end_date)
if data.empty:
    print('Keine Daten')
    raise SystemExit(1)

closes = list(data['close'].tail(20))
print('letzte 20 closes:')
for i in range(1,len(closes)):
    prev = closes[i-1]
    cur = closes[i]
    diff_pct = (cur - prev)/ (prev + 1e-9) * 100
    print(f"{i}: prev={prev:.2f}, cur={cur:.2f}, diff_pct={diff_pct:.4f}%")
