# src/kbot/analysis/optimizer.py
# =============================================================================
# KBot: Parameter-Optimierung für Volume Channel Flow Strategie
# =============================================================================

import os
import sys
import json
import glob
import optuna
import argparse
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data, run_backtest
from kbot.strategy.volume_channel_engine import VolumeChannelEngine

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Globale Variablen
HISTORICAL_DATA = None
MAX_DRAWDOWN_CONSTRAINT = 30.0
MIN_WIN_RATE_CONSTRAINT = 50.0
MIN_PNL_CONSTRAINT = 0.0
MIN_TRADES = 10
START_CAPITAL = 1000
OPTIM_MODE = "strict"


def objective(trial):
    """Optuna Objective für Volume Channel Flow Parameter."""
    global HISTORICAL_DATA
    
    # Volume Channel Flow Parameter zum Optimieren
    params = {
        'strategy': {
            'atr_period': trial.suggest_int('atr_period', 100, 300, step=20),
            'channel_width': trial.suggest_float('channel_width', 2.0, 5.0, step=0.25),
            'min_channel_length': trial.suggest_int('min_channel_length', 5, 20),
            'volume_bins': trial.suggest_int('volume_bins', 15, 50, step=5),
            'use_volume_confirmation': trial.suggest_categorical('use_volume_confirmation', [True, False]),
            'risk_reward_ratio': trial.suggest_float('risk_reward_ratio', 1.5, 4.0, step=0.25),
        },
        'risk': {
            'risk_per_trade_pct': trial.suggest_float('risk_per_trade_pct', 0.5, 2.0, step=0.25),
            'leverage': trial.suggest_int('leverage', 3, 20),
        },
        'behavior': {
            'use_longs': True,
            'use_shorts': True,
        }
    }
    
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
    """Speichert die beste Konfiguration. Dateiname enthält einen Zeitstempel zur Eindeutigkeit."""
    
    safe_filename = create_safe_filename(symbol, timeframe)
    config_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    os.makedirs(config_dir, exist_ok=True)
    
    config = {
        "market": {
            "symbol": symbol,
            "timeframe": timeframe
        },
        "strategy": {
            "atr_period": best_params.get('atr_period', 200),
            "channel_width": best_params.get('channel_width', 3.0),
            "min_channel_length": best_params.get('min_channel_length', 10),
            "volume_bins": best_params.get('volume_bins', 30),
            "use_volume_confirmation": best_params.get('use_volume_confirmation', True),
            "risk_reward_ratio": best_params.get('risk_reward_ratio', 2.0)
        },
        "risk": {
            "margin_mode": "isolated",
            "risk_per_trade_pct": best_params.get('risk_per_trade_pct', 1.0),
            "leverage": best_params.get('leverage', 5)
        },
        "behavior": {
            "use_longs": True,
            "use_shorts": True
        },
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
    
    timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    config_path = os.path.join(config_dir, f"config_{safe_filename}_{timestamp}.json")
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    pid = os.getpid()
    print(f"\n✅ Konfiguration gespeichert: {config_path} (PID: {pid})")
    return config_path


def send_warning_telegram(message: str):
    try:
        from kbot.utils.telegram import send_message
        secret_path = os.path.join(PROJECT_ROOT, 'secret.json')
        if os.path.exists(secret_path):
            with open(secret_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tg = data.get('telegram', {})
                bot = tg.get('bot_token')
                chat = tg.get('chat_id')
                if bot and chat:
                    send_message(bot, chat, message)
    except Exception:
        pass


def get_best_existing_pnl(safe_filename: str):
    config_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    pattern = os.path.join(config_dir, f"config_{safe_filename}_*.json")
    best = None
    for path in glob.glob(pattern):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                pnl = data.get('optimization', {}).get('backtest_pnl_pct')
                if pnl is not None:
                    if best is None or pnl > best:
                        best = pnl
        except Exception:
            continue
    return best


def main():
    global HISTORICAL_DATA, MAX_DRAWDOWN_CONSTRAINT, MIN_WIN_RATE_CONSTRAINT
    global MIN_PNL_CONSTRAINT, MIN_TRADES, START_CAPITAL, OPTIM_MODE
    
    parser = argparse.ArgumentParser(description="KBot Volume Channel Flow Optimizer")
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
    args = parser.parse_args()    
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
    print("   KBot Volume Channel Flow - Parameter Optimierung")
    print("=" * 60)
    print(f"   Symbole:      {', '.join(symbols)}")
    print(f"   Timeframes:   {', '.join(timeframes)}")
    print(f"   Zeitraum:     {args.start_date} bis {args.end_date}")
    print(f"   Trials:       {args.trials}")
    print(f"   Modus:        {args.mode}")
    print("=" * 60)
    
    # Collector for per-run notifications
    notifications = {
        'saved': [],
        'skipped_worse': [],
        'skipped_zero_trades': [],
        'errors': []
    }

    for symbol in symbols:
        for timeframe in timeframes:
            print(f"\n{'─' * 50}")
            print(f"🔍 Optimiere: {symbol} ({timeframe})")
            print(f"{'─' * 50}")
            
            # Daten laden
            HISTORICAL_DATA = load_data(symbol, timeframe, args.start_date, args.end_date)
            
            if HISTORICAL_DATA.empty or len(HISTORICAL_DATA) < 100:
                print(f"⚠️ Nicht genug Daten für {symbol} ({timeframe}). Überspringe.")
                continue
            
            print(f"📊 Daten geladen: {len(HISTORICAL_DATA)} Kerzen")
            print(f"📅 Zeitraum: {HISTORICAL_DATA.index.min()} bis {HISTORICAL_DATA.index.max()}")
            
            # Optuna Study erstellen
            safe_filename = create_safe_filename(symbol, timeframe)
            db_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'db')
            os.makedirs(db_dir, exist_ok=True)
            
            storage_url = f"sqlite:///{db_dir}/optuna_vcf.db?timeout=60"
            study_name = f"vcf_{safe_filename}_{args.mode}"
            
            study = optuna.create_study(
                storage=storage_url,
                study_name=study_name,
                direction="maximize",
                load_if_exists=True
            )
            
            print(f"\n🚀 Starte Optimierung mit {args.trials} Trials...")
            
            study.optimize(
                objective,
                n_trials=args.trials,
                n_jobs=args.jobs if args.jobs > 0 else 1,
                show_progress_bar=True
            )
            
            # Ergebnisse auswerten
            valid_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
            
            if not valid_trials:
                print(f"\n❌ Keine gültigen Parameter gefunden für {symbol} ({timeframe})")
                continue
            
            best = study.best_trial
            print(f"\n✅ Beste Parameter gefunden (Score: {best.value:.2f}):")
            for key, value in best.params.items():
                print(f"   {key}: {value}")
            
            # Finaler Backtest mit besten Parametern
            final_params = {
                'strategy': {
                    'atr_period': best.params.get('atr_period', 200),
                    'channel_width': best.params.get('channel_width', 3.0),
                    'min_channel_length': best.params.get('min_channel_length', 10),
                    'volume_bins': best.params.get('volume_bins', 30),
                    'use_volume_confirmation': best.params.get('use_volume_confirmation', True),
                    'risk_reward_ratio': best.params.get('risk_reward_ratio', 2.0),
                },
                'risk': {
                    'risk_per_trade_pct': best.params.get('risk_per_trade_pct', 1.0),
                    'leverage': best.params.get('leverage', 5),
                },
                'behavior': {
                    'use_longs': True,
                    'use_shorts': True,
                }
            }
            
            final_result = run_backtest(HISTORICAL_DATA.copy(), final_params, 
                                        start_capital=START_CAPITAL, verbose=False)
            
            run_ts = datetime.now().strftime('%Y%m%dT%H%M%S')
            pid = os.getpid()
            run_id = f"{run_ts}-{pid}"

            print(f"\n\n[{run_id}] 📊 FINALES BACKTEST-ERGEBNIS:")
            print(f"[{run_id}]    Trades:        {final_result['trades_count']}")
            print(f"[{run_id}]    Win-Rate:      {final_result['win_rate']:.1f}%")
            print(f"[{run_id}]    Rendite:       {final_result['total_pnl_pct']:.2f}%")
            print(f"[{run_id}]    Max Drawdown:  {final_result['max_drawdown_pct']:.2f}%")
            print(f"[{run_id}]    Profit Factor: {final_result.get('profit_factor', 0):.2f}")
            print(f"[{run_id}]    Endkapital:    ${final_result['end_capital']:.2f}")
            
            # Config speichern — nur wenn Trades vorhanden sind und Ergebnis besser als bestehende
            trades = final_result.get('trades_count', 0)
            final_pnl = round(final_result.get('total_pnl_pct', 0), 4)
            safe_filename = create_safe_filename(symbol, timeframe)
            best_existing_pnl = get_best_existing_pnl(safe_filename)

            if trades <= 0:
                msg = f"⚠️ [{run_id}] Keine Trades im finalen Backtest für {symbol} ({timeframe})."
                print(msg)
                notifications['skipped_zero_trades'].append({'symbol': symbol, 'timeframe': timeframe})
            else:
                if best_existing_pnl is not None and final_pnl <= best_existing_pnl:
                    msg = f"⚠️ [{run_id}] Ergebnis nicht besser als bestehende Konfiguration ({final_pnl}% <= {best_existing_pnl}%). Überspringe Speichern für {symbol} ({timeframe})."
                    print(msg)
                    notifications['skipped_worse'].append({'symbol': symbol, 'timeframe': timeframe, 'final_pnl': final_pnl, 'best_existing_pnl': best_existing_pnl})
                else:
                    saved = save_config(symbol, timeframe, best.params, final_result,
                               args.start_date, args.end_date)
                    print(f"[{run_id}] ✅ Konfiguration gespeichert: {saved}")
                    notifications['saved'].append({'symbol': symbol, 'timeframe': timeframe, 'file': saved, 'final_pnl': final_pnl})

    
    # Write run summary to artifacts for scheduler to pick up
    try:
        runs_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'optimizer_runs')
        os.makedirs(runs_dir, exist_ok=True)
        summary = {
            'run_id': run_id,
            'start_date': args.start_date,
            'end_date': args.end_date,
            'symbols': symbols,
            'timeframes': timeframes,
            'saved': notifications['saved'],
            'skipped_worse': notifications['skipped_worse'],
            'skipped_zero_trades': notifications['skipped_zero_trades'],
            'errors': notifications['errors']
        }
        summary_path = os.path.join(runs_dir, f"optimizer_summary_{run_id}.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        print(f"\n🔔 Run summary written: {summary_path}")
    except Exception as e:
        print(f"Fehler beim Schreiben der Run-Summary: {e}")

    print("\n" + "=" * 60)
    print("   ✅ Optimierung abgeschlossen!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
