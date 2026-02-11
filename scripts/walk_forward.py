#!/usr/bin/env python3
"""POC Walk-Forward: Simple in-sample / out-of-sample check for a saved config

Usage:
  scripts/walk_forward.py --config src/kbot/strategy/configs/config_ETHUSDTUSDT_2h.json --train_frac 0.8
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data, run_backtest


def run_walk_forward(cfg_path, train_frac=0.8, start_date=None, end_date=None):
    cfg = json.loads(Path(cfg_path).read_text())
    sym = cfg['market']['symbol']
    tf = cfg['market']['timeframe']

    # default dates from config optimization metadata
    if not start_date or not end_date:
        dr = cfg.get('optimization', {}).get('data_range', '')
        if ' to ' in dr:
            start_date, end_date = dr.split(' to ')
        else:
            raise SystemExit('Bitte start/end angeben oder validen data_range in config')

    print(f"Walk-Forward für {sym} {tf} ({start_date} - {end_date})")
    data = load_data(sym, tf, start_date, end_date)
    if data.empty:
        print('Keine Daten verfügbar. Abbruch.')
        return 1

    split_idx = int(len(data) * float(train_frac))
    train_df = data.iloc[:split_idx]
    oos_df = data.iloc[split_idx:]

    params = {'strategy': cfg['strategy'], 'risk': cfg.get('risk',{}), 'behavior': cfg.get('behavior',{})}

    print('\n-- In-Sample --')
    res_train = run_backtest(train_df.copy(), params, start_capital=1000, verbose=False)
    print(f"IS: PnL={res_train.get('total_pnl_pct',0):.2f}%, Trades={res_train.get('trades_count',0)}, Win={res_train.get('win_rate',0):.1f}%")

    print('\n-- Out-of-Sample --')
    res_oos = run_backtest(oos_df.copy(), params, start_capital=1000, verbose=False)
    print(f"OOS: PnL={res_oos.get('total_pnl_pct',0):.2f}%, Trades={res_oos.get('trades_count',0)}, Win={res_oos.get('win_rate',0):.1f}%")

    # Save walk-forward summary
    import datetime
    now = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'walk_forward_runs')
    os.makedirs(out_dir, exist_ok=True)
    summary = {
        'config': str(cfg_path),
        'symbol': sym,
        'timeframe': tf,
        'train_frac': train_frac,
        'start_date': start_date,
        'end_date': end_date,
        'is': res_train,
        'oos': res_oos
    }
    out_path = os.path.join(out_dir, f"wf_{Path(cfg_path).stem}_{now}.json")
    with open(out_path, 'w') as f:
        json.dump(summary, f, default=str, indent=2)
    print(f"Saved walk-forward summary: {out_path}")

    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--train_frac', type=float, default=0.8)
    ap.add_argument('--start_date', type=str, default=None)
    ap.add_argument('--end_date', type=str, default=None)
    args = ap.parse_args()

    return run_walk_forward(args.config, args.train_frac, args.start_date, args.end_date)


if __name__ == '__main__':
    main()