#!/usr/bin/env python3
"""Pick and quick-simulate ensemble from optimizer configs (POC)

Usage:
  scripts/pick_and_simulate.py --min_trades 20 --min_pnl 20 --min_pf 1.2 --ensemble_size 5 --output ensemble.json [--auto_push]

This POC selects configs by metadata in src/kbot/strategy/configs/*.json and
writes an ensemble file with chosen configs and a simple aggregated estimate.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

def find_candidates(cfg_dir):
    res=[]
    for f in sorted(Path(cfg_dir).glob('*.json')):
        try:
            j=json.loads(f.read_text())
            opt=j.get('optimization',{})
            trades=opt.get('backtest_trades',0)
            pnl=opt.get('backtest_pnl_pct',0)
            pf=opt.get('backtest_profit_factor',0)
            res.append({'file':str(f),'trades':trades,'pnl':pnl,'pf':pf,'summary':opt})
        except Exception as e:
            print(f"Warning: failed to parse {f}: {e}", file=sys.stderr)
    return res


def pick_top(candidates,min_trades,min_pnl,min_pf,ensemble_size):
    filt=[c for c in candidates if c['trades']>=min_trades and c['pnl']>=min_pnl and c['pf']>=min_pf]
    filt.sort(key=lambda x: x['pnl'], reverse=True)
    return filt[:ensemble_size]


def quick_simulate(ensemble):
    # POC: aggregated metrics (mean pnl, weighted by trades)
    if not ensemble:
        return {}
    total_trades=sum(e['trades'] for e in ensemble)
    mean_pnl=sum(e['pnl'] for e in ensemble)/len(ensemble)
    weighted_pnl=sum(e['pnl']*e['trades'] for e in ensemble)/max(total_trades,1)
    return {'n':len(ensemble),'mean_pnl':mean_pnl,'weighted_pnl':weighted_pnl,'total_trades':total_trades}


def write_output(out_path, ensemble, metrics):
    payload={'ensemble':[{'file':e['file'],'trades':e['trades'],'pnl':e['pnl'],'pf':e['pf']} for e in ensemble],
             'metrics':metrics}
    Path(out_path).write_text(json.dumps(payload, indent=2))
    print(f"Wrote ensemble to {out_path}")


def git_commit_and_push(files, message):
    try:
        subprocess.check_call(['git','add']+files)
        subprocess.check_call(['git','commit','-m',message])
        subprocess.check_call(['git','push','origin','HEAD'])
        return True
    except subprocess.CalledProcessError as e:
        print('Git push failed:', e, file=sys.stderr)
        return False


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--min_trades', type=int, default=20)
    ap.add_argument('--min_pnl', type=float, default=20.0)
    ap.add_argument('--min_pf', type=float, default=1.2)
    ap.add_argument('--ensemble_size', type=int, default=5)
    ap.add_argument('--cfg_dir', default='src/kbot/strategy/configs')
    ap.add_argument('--output', default='artifacts/ensemble.json')
    ap.add_argument('--auto_push', action='store_true', help='If set, commit ensemble.json to git and push')
    args=ap.parse_args()

    cand=find_candidates(args.cfg_dir)
    chosen=pick_top(cand,args.min_trades,args.min_pnl,args.min_pf,args.ensemble_size)
    metrics=quick_simulate(chosen)
    write_output(args.output, chosen, metrics)

    print('Selected configs:')
    for e in chosen:
        print(f" - {Path(e['file']).name}: trades={e['trades']}, pnl={e['pnl']}, pf={e['pf']}")
    print('Metrics:',metrics)

    if args.auto_push:
        ok=git_commit_and_push([args.output], 'Add ensemble selection output')
        if ok:
            print('Ensemble pushed to origin')

if __name__=='__main__':
    main()
