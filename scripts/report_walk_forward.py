#!/usr/bin/env python3
"""Report and Filter Walk-Forward + Auto-Optimize Results

Loads artifacts/auto_opt_results_*.json and walk_forward_runs/*.json and
produces a summarized report, including filtering for robust configs.
"""
import argparse
import json
import os
from pathlib import Path
from statistics import mean

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
WF_DIR = os.path.join(OUT_DIR, 'walk_forward_runs')
AUTO_FILE_GLOB = os.path.join(OUT_DIR, 'auto_opt_results_*.json')


def find_all_config_files():
    cfg_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    files = sorted(Path(cfg_dir).glob('config_*.json'))
    return [str(f) for f in files if 'template' not in f.name]


def load_wf_summaries_for_config(cfg_path):
    safe = Path(cfg_path).stem.replace('config_', 'wf_config_')
    files = sorted(Path(WF_DIR).glob(f"{safe}_*.json"))
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text()))
        except Exception as e:
            print('Warning parse WF', f, e)
    return out


def ensure_wf_summary(cfg_path, train_frac=0.7, n_splits=3):
    # If no WF summary exists, run walk_forward for that config
    wf_files = load_wf_summaries_for_config(cfg_path)
    if wf_files:
        return wf_files[-1]
    # run walk_forward script
    wf_script = os.path.join(PROJECT_ROOT, 'scripts', 'walk_forward.py')
    cmd = f"python {wf_script} --config {cfg_path} --train_frac {train_frac} --n_splits {n_splits}"
    print('Running walk-forward for', cfg_path)
    os.system(cmd)
    wf_files = load_wf_summaries_for_config(cfg_path)
    return wf_files[-1] if wf_files else None


def summarize_from_configs(config_files, min_oos_trades=20, min_mean_oos_pnl=0.0):
    candidates = []
    for cfg in config_files:
        wf = ensure_wf_summary(cfg)
        if not wf:
            print('No WF summary for', cfg)
            continue
        agg = wf.get('agg', {})
        mean_oos = agg.get('mean_oos_pnl', 0.0)
        total_oos_trades = agg.get('total_oos_trades', 0)
        if total_oos_trades >= min_oos_trades and mean_oos >= min_mean_oos_pnl:
            # get symbol/timeframe
            j = json.loads(Path(cfg).read_text())
            sym = j['market']['symbol'].split('/')[0]
            tf = j['market']['timeframe']
            candidates.append({'symbol': sym, 'timeframe': tf, 'config': cfg, 'agg': agg})
    return candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min_oos_trades', type=int, default=20)
    ap.add_argument('--min_mean_oos_pnl', type=float, default=0.0)
    ap.add_argument('--output', default=os.path.join(OUT_DIR, 'report_filtered_configs.json'))
    args = ap.parse_args()

    cfgs = find_all_config_files()
    print(f'Found {len(cfgs)} config files')

    candidates = summarize_from_configs(cfgs, args.min_oos_trades, args.min_mean_oos_pnl)
    print(f'Filtered {len(candidates)} candidate configs (min_trades={args.min_oos_trades}, min_mean_oos_pnl={args.min_mean_oos_pnl})')

    with open(args.output, 'w') as f:
        json.dump({'filtered': candidates}, f, indent=2)

    print('Wrote filtered report to', args.output)


if __name__ == '__main__':
    main()
