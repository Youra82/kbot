#!/usr/bin/env python3
"""Select robust configs (from report) and build ensemble.json

Reads report_filtered_configs.json and writes artifacts/ensemble_selected.json
"""
import argparse
import json
import os
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT_DIR = os.path.join(PROJECT_ROOT, 'artifacts')
REPORT_FILE = os.path.join(OUT_DIR, 'report_filtered_configs.json')
OUTPUT = os.path.join(OUT_DIR, 'ensemble_selected.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', default=REPORT_FILE)
    ap.add_argument('--output', default=OUTPUT)
    ap.add_argument('--auto_push', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.report):
        print('Report not found:', args.report)
        return 1

    r = json.loads(Path(args.report).read_text())
    filtered = r.get('filtered', [])
    ensemble = []
    for c in filtered:
        ensemble.append({'file': c['config'], 'symbol': c['symbol'], 'timeframe': c['timeframe'], 'agg': c['agg']})

    Path(args.output).write_text(json.dumps({'ensemble': ensemble}, indent=2))
    print('Wrote ensemble to', args.output)

    if args.auto_push and ensemble:
        try:
            import subprocess
            subprocess.check_call(['git','add', args.output])
            subprocess.check_call(['git','commit','-m', 'Add selected ensemble'])
            subprocess.check_call(['git','push','origin','HEAD'])
            print('Committed and pushed ensemble')
        except Exception as e:
            print('Git push failed:', e)

if __name__=='__main__':
    main()
