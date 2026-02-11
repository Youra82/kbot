# src/kbot/analysis/show_results.py
# =============================================================================
# KBot: Backtest-Ergebnisse anzeigen (Peak/Trough Reversal)
# Interaktive Abfragen wie bei JaegerBot/DBot
# =============================================================================

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import date, datetime
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data, run_backtest
from kbot.strategy.peak_trough_engine import PeakTroughEngine
# Backwards-compat: old VolumeChannelEngine removed; use PeakTroughEngine


def show_channel_summary(symbol: str, timeframe: str, data: pd.DataFrame, 
                          params: dict) -> dict:
    """Zeigt eine Zusammenfassung des Peak/Trough Reversal."""
    strategy = params.get('strategy', {})
    
    engine = PeakTroughEngine(settings=strategy)
    df = engine.process_dataframe(data)
    
    if df.empty or df['channel_top'].isna().all():
        print(f"  ⓘ Channel konnte nicht berechnet werden")
        return None
    
    current = df.iloc[-1]
    current_price = current['close']
    channel_top = current['channel_top']
    channel_bot = current['channel_bot']
    channel_avg = current['channel_avg']
    trend = current['channel_trend']
    
    # Bestimme Position im Channel
    if current_price >= channel_top:
        position = "ÜBER dem Channel (Breakout Long)"
        signal_hint = "🟢 LONG aktiv"
    elif current_price <= channel_bot:
        position = "UNTER dem Channel (Breakout Short)"
        signal_hint = "🔴 SHORT aktiv"
    elif current_price > channel_avg:
        position = "Obere Hälfte des Channels"
        signal_hint = "⚪ Abwarten"
    else:
        position = "Untere Hälfte des Channels"
        signal_hint = "⚪ Abwarten"
    
    trend_str = "🟢 BULLISH" if trend == 1 else "🔴 BEARISH" if trend == -1 else "⚪ NEUTRAL"
    
    print(f"\n  📊 Peak/Trough Reversal für {symbol} ({timeframe}):")
    print(f"     Channel Top:         {channel_top:.2f}")
    print(f"     Channel Avg:         {channel_avg:.2f}")
    print(f"     Channel Bot:         {channel_bot:.2f}")
    print(f"     Aktueller Preis:     {current_price:.2f}")
    print(f"     Channel Trend:       {trend_str}")
    print(f"     Position:            {position}")
    print(f"     Signal-Tendenz:      {signal_hint}")
    
    return {
        'channel_top': channel_top,
        'channel_bot': channel_bot,
        'channel_avg': channel_avg,
        'trend': trend,
        'current_price': current_price
    }


def run_single_analysis(start_date: str, end_date: str, start_capital: float = 1000):
    """Modus 1: Führt Backtests für alle Konfigurationen einzeln durch."""
    print("\n--- KBot Ergebnis-Analyse (Einzel-Modus) ---")
    
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    all_results = []
    
    config_files = sorted([f for f in os.listdir(configs_dir) 
                          if f.startswith('config_') and f.endswith('.json')])

    if not config_files:
        print("\nKeine Konfigurationen gefunden.")
        print("Führe zuerst './run_pipeline.sh' aus, um Strategien zu optimieren.")
        return

    for filename in config_files:
        config_path = os.path.join(configs_dir, filename)
        if not os.path.exists(config_path):
            continue

        with open(config_path, 'r') as f:
            config = json.load(f)

        symbol = config.get('market', {}).get('symbol', 'BTC/USDT:USDT')
        timeframe = config.get('market', {}).get('timeframe', '4h')
        strategy_name = f"{symbol} ({timeframe})"

        print(f"\nAnalysiere: {strategy_name}...")

        # Daten laden
        data = load_data(symbol, timeframe, start_date, end_date)
        if data.empty:
            print(f"  --> WARNUNG: Keine Daten verfügbar. Überspringe.")
            continue

        # Backtest durchführen
        result = run_backtest(data, config, start_capital=start_capital, verbose=False)
        
        all_results.append({
            "Strategie": strategy_name,
            "Trades": result['trades_count'],
            "Win-Rate %": result['win_rate'],
            "PnL %": result['total_pnl_pct'],
            "Max DD %": result['max_drawdown_pct'],
            "PF": result.get('profit_factor', 0),
            "Endkapital": result['end_capital']
        })

    if not all_results:
        print("\nKeine gültigen Konfigurationen gefunden.")
        return

    # Ergebnis-Tabelle anzeigen
    results_df = pd.DataFrame(all_results)
    results_df = results_df.sort_values(by="PnL %", ascending=False)

    pd.set_option('display.width', 1000)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.float_format', '{:.2f}'.format)
    
    print("\n\n==================================================================================")
    print(f"           Zusammenfassung (Startkapital: {start_capital} USDT)")
    print(f"           Zeitraum: {start_date} bis {end_date}")
    print("==================================================================================")
    print(results_df.to_string(index=False))
    print("==================================================================================")


def run_portfolio_simulation(start_date: str, end_date: str, start_capital: float, 
                             selected_configs: list = None):
    """Modus 2: Manuelle Portfolio-Simulation."""
    print("\n--- KBot Manuelle Portfolio-Simulation ---")
    
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    
    # Verfügbare Strategien laden
    config_files = sorted([f for f in os.listdir(configs_dir) 
                          if f.startswith('config_') and f.endswith('.json')])
    
    if not config_files:
        print("Keine Strategien gefunden. Führe zuerst './run_pipeline.sh' aus.")
        return
    
    # Strategie-Auswahl
    print("\nVerfügbare Strategien:")
    for i, name in enumerate(config_files):
        print(f"  {i+1}) {name}")
    
    selection = input("\nWelche Strategien simulieren? (Zahlen mit Komma, z.B. 1,3 oder 'alle'): ")
    
    try:
        if selection.lower() == 'alle':
            selected_files = config_files
        else:
            selected_files = [config_files[int(i.strip()) - 1] for i in selection.split(',')]
    except (ValueError, IndexError):
        print("Ungültige Auswahl. Breche ab.")
        return
    
    # Portfolio-Simulation
    print(f"\nSimuliere Portfolio mit {len(selected_files)} Strategien...")
    
    total_pnl = 0
    total_trades = 0
    max_dd = 0
    
    for filename in selected_files:
        config_path = os.path.join(configs_dir, filename)
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        symbol = config.get('market', {}).get('symbol')
        timeframe = config.get('market', {}).get('timeframe')
        
        data = load_data(symbol, timeframe, start_date, end_date)
        if data.empty:
            continue
        
        result = run_backtest(data, config, start_capital=start_capital, verbose=False)
        
        total_pnl += result['total_pnl_pct']
        total_trades += result['trades_count']
        max_dd = max(max_dd, result['max_drawdown_pct'])
        
        print(f"  {symbol} ({timeframe}): {result['total_pnl_pct']:.2f}% ({result['trades_count']} Trades)")
    
    # Zusammenfassung
    avg_pnl = total_pnl / len(selected_files) if selected_files else 0
    end_capital = start_capital * (1 + avg_pnl / 100)
    
    print("\n=======================================================")
    print("     Ergebnis der Portfolio-Simulation")
    print("=======================================================")
    print(f"Zeitraum:         {start_date} bis {end_date}")
    print(f"Startkapital:     {start_capital:.2f} USDT")
    print(f"Strategien:       {len(selected_files)}")
    print(f"Anzahl Trades:    {total_trades}")
    print(f"Durchschn. PnL:   {avg_pnl:.2f}%")
    print(f"Max Drawdown:     {max_dd:.2f}%")
    print(f"Endkapital:       {end_capital:.2f} USDT")
    print("=======================================================")


def run_portfolio_optimizer(start_date: str, end_date: str, start_capital: float, 
                            max_drawdown: float = 30.0):
    """Modus 3: Automatische Portfolio-Optimierung."""
    print("\n--- KBot Automatische Portfolio-Optimierung ---")
    print(f"Max. erlaubter Drawdown: {max_drawdown}%")
    
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    
    config_files = sorted([f for f in os.listdir(configs_dir) 
                          if f.startswith('config_') and f.endswith('.json')])
    
    if not config_files:
        print("Keine Strategien gefunden.")
        return
    
    # Alle Strategien backtesten und nach PnL/DD sortieren
    results = []
    
    print("\nAnalysiere alle Strategien...")
    for filename in config_files:
        config_path = os.path.join(configs_dir, filename)
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        symbol = config.get('market', {}).get('symbol')
        timeframe = config.get('market', {}).get('timeframe')
        
        data = load_data(symbol, timeframe, start_date, end_date)
        if data.empty:
            continue
        
        result = run_backtest(data, config, start_capital=start_capital, verbose=False)
        
        # Nur Strategien mit akzeptablem Drawdown
        if result['max_drawdown_pct'] <= max_drawdown and result['trades_count'] >= 3:
            results.append({
                'filename': filename,
                'symbol': symbol,
                'timeframe': timeframe,
                'pnl': result['total_pnl_pct'],
                'dd': result['max_drawdown_pct'],
                'trades': result['trades_count'],
                'pf': result.get('profit_factor', 0)
            })
    
    if not results:
        print(f"\n❌ Keine Strategien gefunden, die den Drawdown-Constraint von {max_drawdown}% erfüllen.")
        return
    
    # Nach PnL/DD-Verhältnis sortieren (Risk-adjusted Return)
    for r in results:
        r['score'] = r['pnl'] / max(r['dd'], 0.1)
    
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    
    # Optimales Portfolio: Top-Strategien
    optimal = results[:min(5, len(results))]
    
    print("\n=======================================================")
    print("     Optimales Portfolio gefunden!")
    print("=======================================================")
    print(f"Anzahl Strategien: {len(optimal)}")
    print("\nAusgewählte Strategien:")
    
    total_pnl = 0
    for r in optimal:
        print(f"  - {r['symbol']} ({r['timeframe']}): {r['pnl']:.2f}% PnL, {r['dd']:.2f}% DD")
        total_pnl += r['pnl']
    
    avg_pnl = total_pnl / len(optimal)
    
    print(f"\nDurchschn. PnL:   {avg_pnl:.2f}%")
    print(f"Max Drawdown:     {max(r['dd'] for r in optimal):.2f}%")
    print("=======================================================")
    
    # Speichere optimale Configs für Bash-Script
    optimal_configs_file = os.path.join(PROJECT_ROOT, '.optimal_configs.tmp')
    with open(optimal_configs_file, 'w') as f:
        f.write('\n'.join(r['filename'] for r in optimal))
    print(f"\n✔ Optimale Strategien wurden in '.optimal_configs.tmp' gespeichert.")


def main():
    parser = argparse.ArgumentParser(description="KBot Backtest-Ergebnisse")
    parser.add_argument('--mode', type=str, default='1', 
                       help='Analyse-Modus: 1=Einzel, 2=Portfolio, 3=Optimizer, 4=Charts')
    args = parser.parse_args()
    
    # --- Interaktive Abfragen (wie bei JaegerBot) ---
    print("\n--- Bitte Konfiguration für den Backtest festlegen ---")
    start_date = input(f"Startdatum (JJJJ-MM-TT) [Standard: 2024-01-01]: ") or "2024-01-01"
    end_date = input(f"Enddatum (JJJJ-MM-TT) [Standard: Heute]: ") or date.today().strftime("%Y-%m-%d")
    start_capital = int(input(f"Startkapital in USDT [Standard: 1000]: ") or 1000)
    
    max_dd_input = 100.0
    if args.mode == '3':
        max_dd_input = float(input(f"Gewünschten maximalen Drawdown in % [Standard: 30]: ") or 30.0)
    
    print("--------------------------------------------------")
    
    # --- Modus-Auswahl ---
    if args.mode == '2':
        run_portfolio_simulation(start_date, end_date, start_capital)
    elif args.mode == '3':
        run_portfolio_optimizer(start_date, end_date, start_capital, max_dd_input)
    elif args.mode == '4':
        print("\nModus 4 (Interaktive Charts) wird in interactive_status.py behandelt.")
    else:
        run_single_analysis(start_date, end_date, start_capital)


if __name__ == "__main__":
    main()
