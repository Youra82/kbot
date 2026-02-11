#!/usr/bin/env python3
"""Automated short optimizer + walk-forward runner

Usage:
  python scripts/auto_optimize_and_wf.py

This script runs the optimizer for a set of short symbol/timeframe combos
(with small trial counts), looks for saved config files, runs walk-forward on
any saved configs and aggregates results into artifacts/auto_opt_results.json
"""
import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
OUT_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
WF_DIR = os.path.join(OUT_DIR, 'walk_forward_runs')

COMBOS = [
    ('BTC', '2h'),
    ('ETH', '4h'),
    ('ADA', '4h')
]

PY = os.path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
OPT = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'analysis', 'optimizer.py')
WF = os.path.join(PROJECT_ROOT, 'scripts', 'walk_forward.py')

RESULTS = []

os.makedirs(WF_DIR, exist_ok=True)

for sym, tf in COMBOS:
    sym_arg = sym
    print(f"\n=== Running optimizer for {sym} {tf} ===")
    cmd = [PY, OPT, '--strategy', 'peak_trough', '--symbols', sym_arg, '--timeframes', tf,
           '--start_date', '2023-01-01', '--end_date', '2026-02-11', '--trials', '20', '--jobs', '1',
           '--param', 'lookback_n:3:8:1', '--param', 'reversal_threshold_pct:0.02:1.0:0.02',
           '--param', 'atr_period:5:21:2', '--param', 'atr_mult:0.8:2.0:0.1', '--min_trades', '5', '--min_pnl', '-100', '--max_drawdown', '90', '--mode', 'best_profit']
    print(' '.join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print('Optimizer failed for', sym, tf, 'skipping')
        continue

    # check for saved config
    safe_name = f"{sym.replace('/', '').replace(':','')}_{tf}"
    cfg_path = os.path.join(CONFIG_DIR, f"config_{safe_name}.json")

    if os.path.exists(cfg_path):
        print('Found config:', cfg_path)
        # run walk-forward
        wf_cmd = [PY, WF, '--config', cfg_path, '--train_frac', '0.7', '--n_splits', '3']
        try:
            subprocess.run(wf_cmd, check=True)
        except subprocess.CalledProcessError:
            print('Walk-forward failed for', cfg_path)
            continue
        # find latest wf summary for this config
        files = sorted(Path(WF_DIR).glob(f"wf_config_{safe_name}_*.json"))
        if files:
            latest = str(files[-1])
            summary = json.loads(Path(latest).read_text())
            RESULTS.append({'symbol': sym, 'timeframe': tf, 'config': cfg_path, 'walk_forward': summary})
        else:
            print('No walk-forward summary found for', cfg_path)
    else:
        print('No config saved for', sym, tf)

# write aggregate results
now = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
out_path = os.path.join(OUT_DIR, f"auto_opt_results_{now}.json")
with open(out_path, 'w') as f:
    json.dump(RESULTS, f, indent=2, default=str)
print('Wrote aggregate results to', out_path)
