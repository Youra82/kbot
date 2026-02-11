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


def run_walk_forward(cfg_path, train_frac=0.8, start_date=None, end_date=None, n_splits=3):
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

    print(f"Walk-Forward für {sym} {tf} ({start_date} - {end_date}) | n_splits={n_splits}")
    data = load_data(sym, tf, start_date, end_date)
    if data.empty:
        print('Keine Daten verfügbar. Abbruch.')
        return 1

    total_len = len(data)
    train_len = int(total_len * float(train_frac))
    oos_total_len = total_len - train_len
    if oos_total_len < n_splits:
        n_splits = max(1, oos_total_len)

    oos_len = max(1, int(oos_total_len / n_splits))

    params = {'strategy': cfg['strategy'], 'risk': cfg.get('risk',{}), 'behavior': cfg.get('behavior',{})}

    splits_results = []

    for i in range(n_splits):
        train_end = train_len + i * oos_len
        oos_start = train_end
        oos_end = min(oos_start + oos_len, total_len)

        train_df = data.iloc[:train_end]
        oos_df = data.iloc[oos_start:oos_end]

        if len(train_df) < 5 or len(oos_df) < 1:
            print(f"Split {i+1}: zu wenig Daten (train={len(train_df)}, oos={len(oos_df)}), überspringe.")
            continue

        print(f"\n-- Split {i+1}/{n_splits} | Train {len(train_df)} rows, OOS {len(oos_df)} rows --")
        res_train = run_backtest(train_df.copy(), params, start_capital=1000, verbose=False)
        res_oos = run_backtest(oos_df.copy(), params, start_capital=1000, verbose=False)

        print(f"IS: PnL={res_train.get('total_pnl_pct',0):.2f}%, Trades={res_train.get('trades_count',0)}, Win={res_train.get('win_rate',0):.1f}%")
        print(f"OOS: PnL={res_oos.get('total_pnl_pct',0):.2f}%, Trades={res_oos.get('trades_count',0)}, Win={res_oos.get('win_rate',0):.1f}%")

        splits_results.append({'split': i+1, 'train_rows': len(train_df), 'oos_rows': len(oos_df), 'is': res_train, 'oos': res_oos})

    # Aggregate metrics
    if not splits_results:
        print('Keine gültigen Splits berechnet.')
        return 1

    agg = {
        'n_splits': len(splits_results),
        'mean_is_pnl': sum(s['is'].get('total_pnl_pct',0) for s in splits_results)/len(splits_results),
        'mean_oos_pnl': sum(s['oos'].get('total_pnl_pct',0) for s in splits_results)/len(splits_results),
        'mean_oos_win': sum(s['oos'].get('win_rate',0) for s in splits_results)/len(splits_results),
        'total_oos_trades': sum(s['oos'].get('trades_count',0) for s in splits_results)
    }

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
        'n_splits': len(splits_results),
        'agg': agg,
        'splits': splits_results
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
    ap.add_argument('--n_splits', type=int, default=3, help='Number of rolling OOS splits')
    args = ap.parse_args()

    return run_walk_forward(args.config, args.train_frac, args.start_date, args.end_date, args.n_splits)


if __name__ == '__main__':
    main()