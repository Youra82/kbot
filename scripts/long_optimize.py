#!/usr/bin/env python3
"""Run longer optimizer runs for selected configs

Reads ensemble_selected.json and for each config runs optimizer with higher trials
and stores summaries to artifacts/optimizer_runs.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PY = os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
OPT = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'analysis', 'optimizer.py')
OUT_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
ENSEMBLE = os.path.join(OUT_DIR, 'ensemble_selected.json')


def run_long_opt(cfg_file, trials=200):
    # Extract symbol & timeframe from config
    j = json.loads(Path(cfg_file).read_text())
    sym = j['market']['symbol'].split('/')[0]
    tf = j['market']['timeframe']
    cmd = [PY, OPT, '--strategy', 'peak_trough', '--symbols', sym, '--timeframes', tf,
           '--start_date', '2023-01-01', '--end_date', '2026-02-11', '--trials', str(trials), '--jobs', '1',
           '--param', 'lookback_n:3:8:1', '--param', 'reversal_threshold_pct:0.02:1.0:0.02',
           '--param', 'atr_period:5:21:2', '--param', 'atr_mult:0.8:2.0:0.1', '--min_trades', '5', '--min_pnl', '-100', '--max_drawdown', '90', '--mode', 'best_profit']
    print('Running:', ' '.join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ensemble', default=ENSEMBLE)
    ap.add_argument('--trials', type=int, default=200)
    args = ap.parse_args()

    if not os.path.exists(args.ensemble):
        print('Ensemble file not found:', args.ensemble)
        return 1

    e = json.loads(Path(args.ensemble).read_text())
    for item in e.get('ensemble', []):
        cfg = item['file']
        print('\n=== Long optimize for', cfg, '===')
        try:
            run_long_opt(cfg, trials=args.trials)
        except subprocess.CalledProcessError as ex:
            print('Long optimize failed for', cfg, ex)

if __name__ == '__main__':
    main()
