# src/kbot/analysis/optimizer.py
# =============================================================================
# KBot: Parameter-Optimierung für Peak/Trough Strategie
# =============================================================================

import os
import sys
import json
import optuna
import argparse
from datetime import datetime
import threading
import time

# Optional imports for progress bars
try:
    from optuna.integration import TqdmProgressBarCallback
except Exception:
    TqdmProgressBarCallback = None

try:
    from tqdm import tqdm
except Exception:
    tqdm = None

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data, run_backtest
# Legacy Volume Channel Flow has been removed; use peak_trough strategy instead

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Globale Variablen
HISTORICAL_DATA = None
MAX_DRAWDOWN_CONSTRAINT = 30.0
MIN_WIN_RATE_CONSTRAINT = 50.0
MIN_PNL_CONSTRAINT = 0.0
MIN_TRADES = 10
START_CAPITAL = 1000
OPTIM_MODE = "strict"


def parse_param_spec(spec: str):
    """Parse a param spec string.

    Supported formats:
      - name:start:end:step    (numeric range, int if step is int)
      - name:val1,val2,...     (categorical)
      - name:0:1                (boolean as 0/1)
    Returns a tuple (name, kind, args)
    kind in {'int_range','float_range','categorical'}
    """
    if ':' not in spec:
        return None
    name, rest = spec.split(':', 1)
    if ',' in rest:
        # categorical list
        vals = [v.strip() for v in rest.split(',')]
        # convert numbers
        converted = []
        for v in vals:
            if v.lower() in ('true','false'):
                converted.append(v.lower()=='true')
            else:
                try:
                    if '.' in v:
                        converted.append(float(v))
                    else:
                        converted.append(int(v))
                except Exception:
                    converted.append(v)
        return (name, 'categorical', converted)
    parts = rest.split(':')
    if len(parts) == 3:
        a,b,c = parts
        try:
            # integer steps
            ia, ib, ic = int(a), int(b), int(c)
            return (name, 'int_range', (ia, ib, ic))
        except Exception:
            fa, fb, fc = float(a), float(b), float(c)
            return (name, 'float_range', (fa, fb, fc))
    return None


def objective(trial):
    """Optuna Objective für verschiedene Strategien (dynamisch)."""
    global HISTORICAL_DATA, STRATEGY, PARAM_SPECS

    params = {'strategy':{}, 'risk':{}, 'behavior':{}}

    # If PARAM_SPECS provided, create suggestions dynamically
    if STRATEGY == 'peak_trough':
        # default ranges if not specified
        default_specs = {
            'lookback_n': ('int_range', (3, 10, 1)),
            'reversal_threshold_pct': ('float_range', (0.1, 1.0, 0.1)),
            'atr_period': ('int_range', (7, 21, 2)),
            'atr_mult': ('float_range', (1.0, 2.0, 0.1)),
            'risk_reward_ratio': ('float_range', (1.0, 3.0, 0.1)),
            'risk_per_trade_pct': ('float_range', (0.5, 2.0, 0.25)),
            'use_volume_confirmation': ('categorical', [False, True]),
        }
        specs = {k:v for k,v in default_specs.items()}
        # override with user supplied PARAM_SPECS
        for spec in PARAM_SPECS:
            parsed = parse_param_spec(spec)
            if parsed:
                name, kind, args = parsed
                specs[name] = (kind, args)
        # suggest params
        for name, (kind,args) in specs.items():
            if kind == 'int_range':
                lo, hi, step = args
                params['strategy'][name] = trial.suggest_int(name, lo, hi, step=step)
            elif kind == 'float_range':
                lo, hi, step = args
                params['strategy'][name] = round(trial.suggest_float(name, lo, hi, step=step), 8)
            elif kind == 'categorical':
                params['strategy'][name] = trial.suggest_categorical(name, args)
        # behavior defaults
        params['behavior']['use_longs'] = True
        params['behavior']['use_shorts'] = True
    else:
        # The legacy 'volume_channel' strategy has been removed. Only 'peak_trough' is supported.
        raise ValueError(f"Unsupported strategy: {STRATEGY}. Use 'peak_trough'.")

    # Backtest durchführen
    result = run_backtest(HISTORICAL_DATA.copy(), params, start_capital=START_CAPITAL, verbose=False)
    
    pnl = result.get('total_pnl_pct', -1000)
    drawdown = result.get('max_drawdown_pct', 100)
    trades = result.get('trades_count', 0)
    win_rate = result.get('win_rate', 0)
    profit_factor = result.get('profit_factor', 0)
    
    # Constraints prüfen
    if OPTIM_MODE == "strict":
        if drawdown > MAX_DRAWDOWN_CONSTRAINT:
            raise optuna.exceptions.TrialPruned()
        if win_rate < MIN_WIN_RATE_CONSTRAINT:
            raise optuna.exceptions.TrialPruned()
        if pnl < MIN_PNL_CONSTRAINT:
            raise optuna.exceptions.TrialPruned()
        if trades < MIN_TRADES:
            raise optuna.exceptions.TrialPruned()
    elif OPTIM_MODE == "best_profit":
        if drawdown > MAX_DRAWDOWN_CONSTRAINT:
            raise optuna.exceptions.TrialPruned()
        if trades < 5:
            raise optuna.exceptions.TrialPruned()
    
    # Optimierungsziel: PnL / Drawdown (Risk-adjusted Return)
    drawdown_safe = max(drawdown, 0.1)
    score = pnl / drawdown_safe
    
    # Bonus für hohe Win-Rate
    if win_rate > 60:
        score *= 1.1
    
    return score


def create_safe_filename(symbol: str, timeframe: str) -> str:
    """Erstellt einen sicheren Dateinamen."""
    return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"


def save_config(symbol: str, timeframe: str, best_params: dict, 
                result: dict, start_date: str, end_date: str):
    """Speichert die beste Konfiguration."""
    
    safe_filename = create_safe_filename(symbol, timeframe)
    config_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    os.makedirs(config_dir, exist_ok=True)
    
    # Use best_params to populate strategy section directly (supports peak_trough keys)
    strategy_section = {}
    for k,v in best_params.items():
        if k in ('risk_per_trade_pct','leverage'):
            continue
        strategy_section[k] = v

    config = {
        "market": {"symbol": symbol, "timeframe": timeframe},
        "strategy": strategy_section,
        "risk": {
            "margin_mode": "isolated",
            "risk_per_trade_pct": best_params.get('risk_per_trade_pct', 1.0),
            "leverage": best_params.get('leverage', 5)
        },
        "behavior": {"use_longs": True, "use_shorts": True},
        "optimization": {
            "optimized_at": datetime.now().isoformat(),
            "data_range": f"{start_date} to {end_date}",
            "backtest_pnl_pct": round(result.get('total_pnl_pct', 0), 2),
            "backtest_win_rate": round(result.get('win_rate', 0), 1),
            "backtest_max_dd_pct": round(result.get('max_drawdown_pct', 0), 2),
            "backtest_trades": result.get('trades_count', 0),
            "backtest_profit_factor": round(result.get('profit_factor', 0), 2)
        }
    }
    
    config_path = os.path.join(config_dir, f"config_{safe_filename}.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    print(f"\n✅ Konfiguration gespeichert: {config_path}")
    return config_path


def main():
    global HISTORICAL_DATA, MAX_DRAWDOWN_CONSTRAINT, MIN_WIN_RATE_CONSTRAINT
    global MIN_PNL_CONSTRAINT, MIN_TRADES, START_CAPITAL, OPTIM_MODE
    global STRATEGY, PARAM_SPECS

    parser = argparse.ArgumentParser(description="KBot Optimizer")
    parser.add_argument('--strategy', type=str, default='peak_trough', help="Strategy to optimize (peak_trough)")
    parser.add_argument('--symbols', required=True, type=str, help="Symbole (z.B. BTC ETH)")
    parser.add_argument('--timeframes', required=True, type=str, help="Timeframes (z.B. 4h 1d)")
    parser.add_argument('--start_date', required=True, type=str, help="Start-Datum")
    parser.add_argument('--end_date', required=True, type=str, help="End-Datum")
    parser.add_argument('--trials', type=int, default=100, help="Anzahl Optuna Trials")
    parser.add_argument('--jobs', type=int, default=-1, help="CPU-Kerne (-1 = alle)")
    parser.add_argument('--max_drawdown', type=float, default=30, help="Max Drawdown %")
    parser.add_argument('--min_win_rate', type=float, default=50, help="Min Win-Rate %")
    parser.add_argument('--min_pnl', type=float, default=0, help="Min PnL %")
    parser.add_argument('--min_trades', type=int, default=10, help="Min Trades")
    parser.add_argument('--start_capital', type=float, default=1000, help="Startkapital")
    parser.add_argument('--mode', type=str, default='strict', choices=['strict', 'best_profit'])
    parser.add_argument('--param', action='append', help='Parameter spec, e.g. lookback_n:3:10:1 or atr_mult:1.0:2.0:0.1 or use_volume_confirmation:0,1')
    args = parser.parse_args()

    # read strategy and params
    STRATEGY = args.strategy
    PARAM_SPECS = args.param or []

    # Globale Constraints setzen
    MAX_DRAWDOWN_CONSTRAINT = args.max_drawdown
    MIN_WIN_RATE_CONSTRAINT = args.min_win_rate
    MIN_PNL_CONSTRAINT = args.min_pnl
    MIN_TRADES = args.min_trades
    START_CAPITAL = args.start_capital
    OPTIM_MODE = args.mode

    symbols = [f"{s}/USDT:USDT" for s in args.symbols.split()]
    timeframes = args.timeframes.split()

    print("\n" + "=" * 60)
    print("   KBot Optimizer")
    print("=" * 60)
    print(f"   Strategy:     {STRATEGY}")
    print(f"   Symbole:      {', '.join(symbols)}")
    print(f"   Timeframes:   {', '.join(timeframes)}")
    print(f"   Zeitraum:     {args.start_date} bis {args.end_date}")
    print(f"   Trials:       {args.trials}")
    print(f"   Modus:        {args.mode}")
    print("=" * 60)

    # Optimization loop
    now = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'optimizer_runs')
    os.makedirs(output_dir, exist_ok=True)

    for symbol in symbols:
        for timeframe in timeframes:
            safe_name = create_safe_filename(symbol, timeframe)
            print(f"\n--- Optimizing {symbol} {timeframe} ---")

            # Load data
            HISTORICAL_DATA = load_data(symbol, timeframe, args.start_date, args.end_date)
            if HISTORICAL_DATA.empty:
                print(f"Keine historischen Daten für {symbol} {timeframe} vorhanden. Überspringe.")
                continue

            # Init study (SQLite per-run to allow resume)
            db_path = os.path.join(output_dir, f"study_{safe_name}_{now}.db")
            storage = f"sqlite:///{db_path}"
            study_name = f"opt_{STRATEGY}_{safe_name}_{now}"
            print(f"Studie: {study_name} (storage: {db_path})")
            study = optuna.create_study(direction='maximize', study_name=study_name, storage=storage, load_if_exists=True, sampler=optuna.samplers.TPESampler())

            # Run optimization with progress feedback
            try:
                # Single-process: use Optuna's TqdmProgressBarCallback if available
                if args.jobs == 1 and TqdmProgressBarCallback is not None:
                    callbacks = [TqdmProgressBarCallback()]
                    study.optimize(objective, n_trials=args.trials, n_jobs=1, callbacks=callbacks)
                # Multi-process or callback not available: use a polling tqdm progress bar if tqdm is present
                elif args.jobs != 1 and tqdm is not None:
                    def _run_opt():
                        try:
                            study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)
                        except Exception as e:
                            # exceptions will be surfaced after thread joins
                            _run_opt._exc = e

                    # Start optimization in background thread and poll trial completion
                    t = threading.Thread(target=_run_opt, daemon=True)
                    t.start()

                    with tqdm(total=args.trials, desc=f"{study_name}") as pbar:
                        prev_completed = 0
                        while t.is_alive():
                            df = study.trials_dataframe()
                            completed = len(df[df['state'] == 'COMPLETE']) if not df.empty else 0
                            if completed > prev_completed:
                                pbar.update(completed - prev_completed)
                                prev_completed = completed
                            time.sleep(0.8)
                        # final update
                        df = study.trials_dataframe()
                        completed = len(df[df['state'] == 'COMPLETE']) if not df.empty else 0
                        if completed > prev_completed:
                            pbar.update(completed - prev_completed)
                        # re-raise any exception from thread
                        if hasattr(_run_opt, '_exc'):
                            raise _run_opt._exc
                else:
                    # fallback: no progress bar available
                    study.optimize(objective, n_trials=args.trials, n_jobs=args.jobs)
            except Exception as e:
                print(f"Fehler während der Optimierung: {e}")

            # Summarize
            try:
                best_trial = study.best_trial
            except ValueError:
                print("Keine gültigen Trials gefunden.")
                continue
            if best_trial is None:
                print("Keine gültigen Trials gefunden.")
                continue
            print(f"\nBeste Trial: #{best_trial.number} (Value={best_trial.value:.4f})")
            print(f"Params: {best_trial.params}")

            # Reconstruct hierarchical params for backtest
            final_params = {'strategy': {}, 'risk': {}, 'behavior': {'use_longs': True, 'use_shorts': True}}
            risk_keys = {'risk_per_trade_pct', 'leverage'}
            for k,v in best_trial.params.items():
                if k in risk_keys:
                    final_params['risk'][k] = v
                elif k in ('use_longs','use_shorts'):
                    final_params['behavior'][k] = v
                else:
                    final_params['strategy'][k] = v

            # Evaluate best config
            result = run_backtest(HISTORICAL_DATA.copy(), final_params, start_capital=START_CAPITAL, verbose=False)
            print(f"Result: PnL={result.get('total_pnl_pct',0):.2f}%, Trades={result.get('trades_count',0)}, WinRate={result.get('win_rate',0):.1f}%")

            # Save run summary
            summary = {
                'strategy': STRATEGY,
                'symbol': symbol,
                'timeframe': timeframe,
                'start_date': args.start_date,
                'end_date': args.end_date,
                'best_trial': best_trial.number,
                'best_value': best_trial.value,
                'best_params': best_trial.params,
                'result': result,
                'trials': study.trials_dataframe().astype(str).to_dict(orient='list')
            }
            summary_path = os.path.join(output_dir, f"summary_{safe_name}_{now}.json")
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
            print(f"Saved summary: {summary_path}")

            # Save config only if it meets trade/pnl thresholds
            if result.get('trades_count',0) >= args.min_trades and result.get('total_pnl_pct',0) >= args.min_pnl:
                merged_best = {}
                merged_best.update(final_params.get('strategy', {}))
                merged_best.update(final_params.get('risk', {}))
                save_config(symbol, timeframe, merged_best, result, args.start_date, args.end_date)
            else:
                print("Beste Konfiguration erfüllt nicht die Mindestanforderungen (Trades/PnL). Nicht gespeichert.")

    print("\nOptimierung abgeschlossen.")
    
    
# Optimization is executed inside main() to avoid argparse on import. Use main() when running as script.

if __name__ == "__main__":
    main()
