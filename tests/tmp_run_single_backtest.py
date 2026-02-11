import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

try:
    from kbot.analysis.backtester import load_data, run_backtest
except Exception:
    import traceback
    traceback.print_exc()
    raise SystemExit(1)

symbol = 'ETH/USDT:USDT'
timeframe = '2h'
start_date = '2023-01-01'
end_date = '2026-02-11'

candidates = [
    {'lookback_n':3,'reversal_threshold_pct':0.05,'atr_period':7,'atr_mult':1.0,'risk_reward_ratio':1.5},
    {'lookback_n':4,'reversal_threshold_pct':0.08,'atr_period':10,'atr_mult':1.0,'risk_reward_ratio':1.5},
    {'lookback_n':5,'reversal_threshold_pct':0.15,'atr_period':14,'atr_mult':1.2,'risk_reward_ratio':2.0},
    {'lookback_n':3,'reversal_threshold_pct':0.02,'atr_period':5,'atr_mult':0.8,'risk_reward_ratio':1.2},
]

print(f"Lade Daten für {symbol} {timeframe} ({start_date} - {end_date})...")
data = load_data(symbol, timeframe, start_date, end_date)
if data.empty:
    print("Keine historischen Daten verfügbar. Abbruch.")
    raise SystemExit(1)

for idx, s in enumerate(candidates, start=1):
    params = {
        'strategy': {
            'lookback_n': s['lookback_n'],
            'reversal_threshold_pct': s['reversal_threshold_pct'],
            'atr_period': s['atr_period'],
            'atr_mult': s['atr_mult'],
            'use_volume_confirmation': False,
            'risk_reward_ratio': s.get('risk_reward_ratio',1.5),
        },
        'risk': {'risk_per_trade_pct': 1.0, 'leverage': 10},
        'behavior': {'use_longs': True, 'use_shorts': True}
    }
    print(f"\nTest {idx}: {params['strategy']}")
    result = run_backtest(data, params, start_capital=1000, verbose=False)
    print(f"  trades: {result.get('trades_count',0)}, pnl: {result.get('total_pnl_pct',0):.2f}%, win_rate: {result.get('win_rate',0):.1f}%, dd: {result.get('max_drawdown_pct',0):.1f}%")
    if result.get('trades_count',0) > 0:
        print("  -> Trades gefunden. Wir können jetzt den Optimizer mit gelockerten Constraints laufen lassen.")
        break
else:
    print('\nKeine der getesteten Parameter-Kombinationen hat Trades erzeugt. Ich empfehle, weitere Timeframes oder Symbole zu testen, oder Signal-Logik zu prüfen.')
