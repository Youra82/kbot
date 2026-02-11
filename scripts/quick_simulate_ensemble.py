#!/usr/bin/env python3
"""Quick simulate ensemble: load ensemble_selected.json and run quick backtest per config
Writes artifacts/ensemble_simulation.json with aggregated metrics
"""
import json
import os
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
ENSEMBLE = os.path.join(OUT_DIR, 'ensemble_selected.json')
OUT = os.path.join(OUT_DIR, 'ensemble_simulation.json')

# import backtester helper
import sys
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))
from kbot.analysis.backtester import load_data, run_backtest


def run():
    if not os.path.exists(ENSEMBLE):
        print('Ensemble file not found:', ENSEMBLE)
        return 1
    e = json.loads(Path(ENSEMBLE).read_text())
    results = []
    for item in e.get('ensemble', []):
        cfg_file = item['file']
        cfg = json.loads(Path(cfg_file).read_text())
        sym = cfg['market']['symbol']
        tf = cfg['market']['timeframe']
        params = {'strategy': cfg['strategy'], 'risk': cfg.get('risk',{}), 'behavior': cfg.get('behavior',{})}
        print('Running quick backtest for', sym, tf)
        data = load_data(sym, tf, '2023-01-01', '2026-02-11')
        if data.empty:
            print('No data for', sym, tf)
            continue
        res = run_backtest(data, params, start_capital=1000, verbose=False)
        results.append({'file': cfg_file, 'symbol': sym, 'timeframe': tf, 'result': res})

    Path(OUT).write_text(json.dumps({'results': results}, indent=2, default=str))
    print('Wrote ensemble simulation to', OUT)
    return 0

if __name__=='__main__':
    run()
