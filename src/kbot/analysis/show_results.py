#!/usr/bin/env python3
# src/kbot/analysis/show_results.py
# KBot: Interaktives Backtest-Tool für Kanalstrategie (3 Modi wie JaegerBot)

import os
import sys
import json
import argparse
from datetime import date, datetime, timedelta

# Setup Python Path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from kbot.strategy.run import load_ohlcv, detect_channels, channel_backtest


def load_optimal_config(symbol, timeframe):
    """Lade optimale Konfiguration aus src/kbot/strategy/configs/"""
    config_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    symbol_clean = symbol.replace('/', '').replace(':', '')
    config_file = os.path.join(config_dir, f'config_{symbol_clean}_{timeframe}.json')
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            return config.get('strategy', None), config_file
        except Exception:
            pass
    return None, None


def get_all_configs():
    """Hole alle vorhandenen Konfigurationsdateien"""
    config_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    if not os.path.exists(config_dir):
        return []
    
    configs = []
    for filename in os.listdir(config_dir):
        if filename.startswith('config_') and filename.endswith('.json'):
            config_path = os.path.join(config_dir, filename)
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                configs.append(config)
            except Exception:
                continue
    return configs


def get_lookback_days(timeframe):
    """Bestimme Lookback-Tage basierend auf Timeframe"""
    lookback_map = {
        '5m': 60, '15m': 60,
        '10m': 365,  # Default für 10m
        '30m': 180, '1h': 180,
        '2h': 365, '4h': 365,
        '6h': 730, '1d': 730
    }
    return lookback_map.get(timeframe, 365)


def format_currency(value):
    """Formatiere Wert als Währung"""
    return f"${value:,.2f}"


def format_percent(value):
    """Formatiere Wert als Prozentsatz"""
    return f"{value:.2f}%"


def run_single_backtest(symbol, timeframe, start_date, end_date, start_capital, use_optimal=True):
    """Führe einen einzelnen Backtest durch"""
    
    print(f"\nStarte Backtest für {symbol} ({timeframe})...")
    print("-" * 60)
    
    try:
        # Kursdaten laden
        df = load_ohlcv(symbol, start_date, end_date, timeframe)
        
        if df.empty or len(df) < 60:
            print(f"⚠️  Nicht genügend Kursdaten für {symbol} ({timeframe}). Min. 60 Kerzen erforderlich.")
            return None
        
        # Versuche optimale Konfiguration zu laden
        optimal_params, config_file = load_optimal_config(symbol, timeframe)
        
        if optimal_params and use_optimal:
            print(f"  ℹ Nutze optimierte Parameter aus src/kbot/strategy/configs/")
            channels = detect_channels(
                df, 
                window=optimal_params.get('window', 50),
                min_channel_width=optimal_params.get('min_channel_width', 0.002),
                slope_threshold=optimal_params.get('slope_threshold', 0.02)
            )
            
            end_capital, total_return, num_trades, win_rate, trades, max_dd = channel_backtest(
                df, 
                channels, 
                start_capital=start_capital,
                entry_threshold=optimal_params.get('entry_threshold', 0.015),
                exit_threshold=optimal_params.get('exit_threshold', 0.025)
            )
        else:
            # Verwende Standard-Parameter
            channels = detect_channels(
                df, 
                window=50,
                min_channel_width=0.002,
                slope_threshold=0.02
            )
            
            end_capital, total_return, num_trades, win_rate, trades, max_dd = channel_backtest(
                df, channels, start_capital=start_capital
            )
        
        # Ergebnisse anzeigen
        print(f"✓ {symbol} ({timeframe})")
        print(f"  Zeitraum:      {start_date} bis {end_date} ({len(df)} Kerzen)")
        print(f"  Endkapital:    {format_currency(end_capital)}")
        print(f"  Gesamtrendite: {format_percent(total_return)}")
        print(f"  Anzahl Trades: {num_trades}")
        print(f"  Gewinnquote:   {format_percent(win_rate)}")
        print(f"  Max Drawdown:  {format_percent(max_dd)}")
        
        # Einzelne Trades anzeigen (wenn nicht zu viele)
        if trades and len(trades) <= 20:
            print(f"\n  Trades:")
            for i, trade in enumerate(trades, 1):
                trade_type = trade['type']
                date_str = str(trade['date']).split()[0]
                price = trade['price']
                if trade_type == 'BUY':
                    print(f"    {i}. BUY  {date_str} @ {price:.2f}")
                else:
                    pnl = trade.get('pnl', 0)
                    pnl_pct = (pnl / start_capital * 100)
                    print(f"    {i}. SELL {date_str} @ {price:.2f} (PnL: {format_percent(pnl_pct)})")
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'end_capital': end_capital,
            'total_return': total_return,
            'num_trades': num_trades,
            'win_rate': win_rate,
            'max_dd': max_dd,
            'trades': trades
        }
        
    except Exception as e:
        print(f"❌ Fehler bei {symbol} ({timeframe}): {str(e)}")
        return None


def mode_1_single_analysis():
    """Modus 1: Einzel-Analyse (jede Strategie isoliert)"""
    print("\n" + "=" * 60)
    print("MODUS 1: Einzel-Analyse")
    print("=" * 60)
    
    configs = get_all_configs()
    if not configs:
        print("\n⚠️ Keine optimierten Konfigurationen gefunden!")
        print("   Bitte führe zuerst ./run_pipeline.sh aus.")
        return
    
    print(f"\nGefundene Konfigurationen: {len(configs)}")
    for cfg in configs:
        market = cfg.get('market', {})
        print(f"  • {market.get('symbol')} ({market.get('timeframe')})")
    
    # Frage nach Zeitraum
    print("\n" + "-" * 60)
    start_date_input = input("Startdatum (YYYY-MM-DD) oder 'a' für automatisch [Standard: a]: ").strip() or 'a'
    end_date = input("Enddatum (YYYY-MM-DD, Enter = heute): ").strip() or str(date.today())
    
    try:
        start_capital = float(input("Startkapital (USD, Standard: 1000): ").strip() or "1000")
    except ValueError:
        start_capital = 1000
    
    print("\n" + "=" * 60)
    
    # Backtests durchführen
    all_results = []
    for cfg in configs:
        market = cfg.get('market', {})
        symbol = market.get('symbol')
        timeframe = market.get('timeframe')
        
        if not symbol or not timeframe:
            continue
        
        # Automatisches Datum basierend auf Timeframe
        if start_date_input.lower() == 'a':
            lookback_days = get_lookback_days(timeframe)
            start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        else:
            start_date = start_date_input
        
        result = run_single_backtest(symbol, timeframe, start_date, end_date, start_capital)
        if result:
            all_results.append(result)
    
    # Zusammenfassung
    print_summary(all_results, start_capital)


def mode_2_manual_input():
    """Modus 2: Manuelle Portfolio-Simulation (du wählst die Strategien)"""
    print("\n" + "=" * 60)
    print("MODUS 2: Manuelle Portfolio-Simulation")
    print("=" * 60)
    
    configs = get_all_configs()
    if not configs:
        print("\n⚠️ Keine optimierten Konfigurationen gefunden!")
        print("   Bitte führe zuerst ./run_pipeline.sh aus.")
        return
    
    # Zeige verfügbare Strategien
    print("\nVerfügbare Strategien:")
    available_strategies = []
    for i, cfg in enumerate(configs):
        market = cfg.get('market', {})
        symbol = market.get('symbol')
        timeframe = market.get('timeframe')
        filename = f"config_{symbol.replace('/', '').replace(':', '')}_{timeframe}.json"
        available_strategies.append((symbol, timeframe, filename))
        print(f"  {i+1}) {filename}")
    
    # Auswahl
    selection = input("\nWelche Strategien sollen simuliert werden? (Zahlen mit Komma, z.B. 1,3,4 oder 'alle'): ").strip()
    
    selected_configs = []
    try:
        if selection.lower() == 'alle':
            selected_configs = configs
        else:
            indices = [int(i.strip()) - 1 for i in selection.split(',')]
            selected_configs = [configs[idx] for idx in indices if 0 <= idx < len(configs)]
    except (ValueError, IndexError):
        print("❌ Ungültige Auswahl. Abgebrochen.")
        return
    
    if not selected_configs:
        print("❌ Keine Strategien ausgewählt. Abgebrochen.")
        return
    
    # Frage nach Zeitraum
    print("\n" + "-" * 60)
    start_date = input("Startdatum (YYYY-MM-DD): ").strip()
    if not start_date:
        print("❌ Kein Startdatum eingegeben. Abgebrochen.")
        return
    
    end_date = input("Enddatum (YYYY-MM-DD, Enter = heute): ").strip() or str(date.today())
    
    try:
        start_capital = float(input("Startkapital (USD, Standard: 1000): ").strip() or "1000")
    except ValueError:
        start_capital = 1000
    
    print("\n" + "=" * 60)
    print(f"Starte Backtest für {len(selected_configs)} Strategie(n)...")
    print("=" * 60)
    
    # Backtests durchführen
    all_results = []
    for cfg in selected_configs:
        market = cfg.get('market', {})
        symbol = market.get('symbol')
        timeframe = market.get('timeframe')
        
        if not symbol or not timeframe:
            continue
        
        result = run_single_backtest(symbol, timeframe, start_date, end_date, start_capital)
        if result:
            all_results.append(result)
    
    # Zusammenfassung
    print_summary(all_results, start_capital)


def run_portfolio_optimizer(start_capital, start_date, end_date, max_drawdown, configs):
    """Findet die beste Kombination von Strategien (Greedy-Algorithmus wie JaegerBot)
    Wichtig: Jeder Coin wird nur EINMAL verwendet (beste Timeframe wird automatisch gewählt)"""
    print("\n1/3: Analysiere Einzel-Performance jeder Strategie...")
    
    all_results = []
    
    # Teste jede Strategie einzeln
    for cfg in configs:
        market = cfg.get('market', {})
        symbol = market.get('symbol')
        timeframe = market.get('timeframe')
        
        if not symbol or not timeframe:
            continue
        
        result = run_single_backtest(symbol, timeframe, start_date, end_date, start_capital, use_optimal=True)
        
        if result and result['num_trades'] > 0 and abs(result['max_dd']) <= max_drawdown:
            # Risikoadjustierte Rendite (Calmar Ratio)
            dd_abs = abs(result['max_dd'])
            score = result['total_return'] / dd_abs if dd_abs > 0 else result['total_return']
            all_results.append({
                'symbol': symbol,
                'timeframe': timeframe,
                'score': score,
                'result': result
            })
    
    if not all_results:
        return None
    
    # WICHTIG: Gruppiere nach Symbol und wähle für jeden Coin die beste Timeframe
    # Normalisiere Symbole: BTCUSDT -> BTC, ETHUSDT -> ETH, etc.
    symbol_groups = {}
    for res in all_results:
        symbol = res['symbol']
        # Entferne USDT, USD, BUSD Suffixe für die Grouping
        normalized_symbol = symbol.replace('USDT', '').replace('USD', '').replace('BUSD', '')
        
        if normalized_symbol not in symbol_groups:
            symbol_groups[normalized_symbol] = []
        symbol_groups[normalized_symbol].append(res)
    
    # Wähle für jeden Symbol nur die beste Timeframe
    single_results = []
    for normalized_symbol, candidates in symbol_groups.items():
        # Sortiere nach Score und nehme den besten
        candidates.sort(key=lambda x: x['score'], reverse=True)
        best_for_symbol = candidates[0]
        single_results.append(best_for_symbol)
        print(f"  • {best_for_symbol['symbol']}: {best_for_symbol['timeframe']} (Score: {best_for_symbol['score']:.2f})")
    
    # Sortiere alle besten nach Score
    single_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Star-Spieler (beste Einzelstrategie)
    best_portfolio = [single_results[0]]
    best_score = single_results[0]['score']
    
    print(f"\n2/3: Star-Spieler gefunden: {single_results[0]['symbol']} ({single_results[0]['timeframe']}) (Score: {best_score:.2f})")
    print("3/3: Suche die besten Team-Kollegen...")
    
    # Kandidaten-Pool (ohne Star-Spieler)
    candidates = single_results[1:]
    
    # Greedy: Füge schrittweise Strategien hinzu
    while candidates:
        best_addition = None
        best_new_score = best_score
        
        for candidate in candidates:
            # Teste Portfolio mit dieser zusätzlichen Strategie
            test_portfolio = best_portfolio + [candidate]
            
            # Simuliere kombiniertes Portfolio
            combined_capital = start_capital
            combined_trades = 0
            combined_dd = 0.0
            
            for strat in test_portfolio:
                res = strat['result']
                combined_capital += (res['end_capital'] - start_capital)
                combined_trades += res['num_trades']
                combined_dd = min(combined_dd, res['max_dd'])
            
            # Prüfe DD-Limit
            if abs(combined_dd) > max_drawdown:
                continue
            
            # Berechne Score
            combined_return = ((combined_capital - start_capital) / start_capital) * 100
            dd_abs = abs(combined_dd)
            score = combined_return / dd_abs if dd_abs > 0 else combined_return
            
            if score > best_new_score:
                best_new_score = score
                best_addition = candidate
        
        if best_addition:
            print(f"-> Füge hinzu: {best_addition['symbol']} ({best_addition['timeframe']}) (Neuer Score: {best_new_score:.2f})")
            best_portfolio.append(best_addition)
            best_score = best_new_score
            candidates.remove(best_addition)
        else:
            print("Keine weitere Verbesserung möglich. Optimierung beendet.")
            break
    
    # Berechne finale Performance
    final_capital = start_capital
    final_trades = 0
    final_dd = 0.0
    
    for strat in best_portfolio:
        res = strat['result']
        final_capital += (res['end_capital'] - start_capital)
        final_trades += res['num_trades']
        final_dd = min(final_dd, res['max_dd'])
    
    final_pnl = final_capital - start_capital
    final_pnl_pct = (final_pnl / start_capital) * 100
    
    return {
        'portfolio': best_portfolio,
        'end_capital': final_capital,
        'total_pnl': final_pnl,
        'total_pnl_pct': final_pnl_pct,
        'trade_count': final_trades,
        'max_dd': final_dd
    }


def mode_3_auto_configs():
    """Modus 3: Automatische Portfolio-Optimierung"""
    print("\n" + "=" * 60)
    print("MODUS 3: Automatische Portfolio-Optimierung")
    print("=" * 60)
    
    configs = get_all_configs()
    if not configs:
        print("\n⚠️ Keine optimierten Konfigurationen gefunden!")
        print("   Bitte führe zuerst ./run_pipeline.sh aus.")
        return
    
    print(f"\nGefundene Konfigurationen: {len(configs)}")
    for cfg in configs:
        market = cfg.get('market', {})
        print(f"  • {market.get('symbol')} ({market.get('timeframe')})")
    
    # Frage nach Parametern
    print("\n" + "-" * 60)
    start_date = input("Startdatum (YYYY-MM-DD, Standard: 2023-01-01): ").strip() or "2023-01-01"
    end_date = input("Enddatum (YYYY-MM-DD, Enter = heute): ").strip() or str(date.today())
    
    try:
        start_capital = float(input("Startkapital (USD, Standard: 1000): ").strip() or "1000")
    except ValueError:
        start_capital = 1000
    
    try:
        max_drawdown = float(input("Gewünschten maximalen Drawdown in % (Standard: 30): ").strip() or "30.0")
    except ValueError:
        max_drawdown = 30.0
    
    print("\n" + "=" * 60)
    print(f"INFO: Starte Optimierung mit maximal {max_drawdown:.2f}% Drawdown-Beschränkung.")
    print("=" * 60)
    
    # Portfolio-Optimierung durchführen
    result = run_portfolio_optimizer(start_capital, start_date, end_date, max_drawdown, configs)
    
    # Berechne Zeitdauer
    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (d2 - d1).days
        if total_days <= 0: total_days = 1
    except Exception:
        total_days = 0
    
    # Ergebnis anzeigen
    print("\n" + "=" * 60)
    print("     Ergebnis der automatischen Portfolio-Optimierung")
    print("=" * 60)
    
    if result:
        days_per_trade_str = ""
        if result['trade_count'] > 0 and total_days > 0:
            days_per_trade = total_days / result['trade_count']
            days_per_trade_str = f" (entspricht 1 Trade alle {days_per_trade:.1f} Tage)"
        
        print(f"Zeitraum: {start_date} bis {end_date} ({total_days} Tage)")
        print(f"Startkapital: {format_currency(start_capital)}")
        print(f"Maximal erlaubter DD: {max_drawdown:.2f}%")
        print(f"\nOptimales Portfolio gefunden ({len(result['portfolio'])} Strategien):")
        for strat in result['portfolio']:
            print(f"  - {strat['symbol']} ({strat['timeframe']})")
        
        print("\n--- Simulierte Performance dieses optimalen Portfolios ---")
        print(f"Endkapital:       {format_currency(result['end_capital'])}")
        pnl_sign = '+' if result['total_pnl'] >= 0 else ''
        print(f"Gesamt PnL:       {pnl_sign}{format_currency(result['total_pnl'])} ({result['total_pnl_pct']:.2f}%)")
        print(f"Anzahl Trades:    {result['trade_count']}{days_per_trade_str}")
        print(f"Portfolio Max DD: {result['max_dd']:.2f}%")
        print(f"Liquidiert:       NEIN")
        
        # Speichere optimale Strategien in .optimal_configs.tmp
        optimal_configs_file = os.path.join(PROJECT_ROOT, '.optimal_configs.tmp')
        with open(optimal_configs_file, 'w') as f:
            for strat in result['portfolio']:
                symbol_clean = strat['symbol'].replace('/', '').replace(':', '')
                f.write(f"config_{symbol_clean}_{strat['timeframe']}.json\n")
        
        print("\n--- Export ---")
        print(f"✔ Optimale Configs wurden nach '.optimal_configs.tmp' exportiert.")
        print("=" * 60)
    else:
        print(f"❌ Es konnte kein Portfolio gefunden werden, das die Drawdown-Beschränkung von {max_drawdown:.2f}% erfüllt.")
        print("=" * 60)


def print_summary(all_results, start_capital):
    """Drucke Zusammenfassung aller Backtests"""
    if not all_results:
        return
    
    print("\n" + "=" * 60)
    print("BACKTEST-ZUSAMMENFASSUNG")
    print("=" * 60)
    
    total_capital = 0
    total_trades = 0
    
    print(f"\n{'Symbol':<12} {'TF':<6} {'Endkapital':<15} {'Return':<10} {'Trades':<8} {'Win Rate':<10} {'Max DD':<10}")
    print("-" * 70)
    
    for res in all_results:
        symbol = res['symbol']
        timeframe = res['timeframe']
        end_cap = res['end_capital']
        ret = res['total_return']
        trades = res['num_trades']
        wr = res['win_rate']
        dd = res['max_dd']
        
        total_capital += end_cap
        total_trades += trades
        
        print(f"{symbol:<12} {timeframe:<6} {format_currency(end_cap):<15} {format_percent(ret):<10} {trades:<8} {format_percent(wr):<10} {format_percent(dd):<10}")
    
    print("-" * 70)
    overall_return = ((total_capital - len(all_results) * start_capital) / (len(all_results) * start_capital)) * 100 if all_results else 0
    print(f"{'GESAMT':<12} {'':<6} {format_currency(total_capital):<15} {format_percent(overall_return):<10} {total_trades:<8}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="KBot Interaktives Backtest-Tool")
    parser.add_argument('--mode', type=int, default=1, choices=[1, 2, 3],
                       help='Modus: 1=Einzel-Analyse, 2=Manuelle Eingabe, 3=Auto-Configs')
    
    args = parser.parse_args()
    
    if args.mode == 1:
        mode_1_single_analysis()
    elif args.mode == 2:
        mode_2_manual_input()
    elif args.mode == 3:
        mode_3_auto_configs()


if __name__ == "__main__":
    main()
