# src/kbot/analysis/show_results.py
# =============================================================================
# KBot: Backtest-Ergebnisse anzeigen (Fibonacci BB + Volume Profile)
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

from kbot.analysis.backtester import (
    load_data, 
    calculate_volume_profile,
    calculate_fibonacci_bollinger_bands,
    run_fib_vp_backtest
)
from kbot.utils.telegram import send_document


def show_volume_profile_summary(symbol: str, timeframe: str, data: pd.DataFrame) -> dict:
    """Zeigt eine Zusammenfassung des Volume Profiles."""
    if len(data) < 200:
        print(f"  ⓘ Nicht genug Daten für Volume Profile ({len(data)} < 200)")
        return None
    
    vp = calculate_volume_profile(data.tail(200), num_bars=50)
    
    if vp is None:
        print(f"  ⓘ Volume Profile konnte nicht berechnet werden")
        return None
    
    current_price = data['close'].iloc[-1]
    
    # Bestimme Position relativ zu VP Levels
    if current_price < vp['val']:
        position = "UNTER Value Area (überverkauft)"
        signal_hint = "🟢 Long-Bias"
    elif current_price > vp['vah']:
        position = "ÜBER Value Area (überkauft)"
        signal_hint = "🔴 Short-Bias"
    else:
        position = "IN Value Area (neutral)"
        signal_hint = "⚪ Abwarten"
    
    print(f"\n  📊 Volume Profile für {symbol} ({timeframe}):")
    print(f"     PoC (Point of Control):  {vp['poc']:.2f}")
    print(f"     VAH (Value Area High):   {vp['vah']:.2f}")
    print(f"     VAL (Value Area Low):    {vp['val']:.2f}")
    print(f"     Aktueller Preis:         {current_price:.2f}")
    print(f"     Position:                {position}")
    print(f"     Signal-Tendenz:          {signal_hint}")
    
    return vp


def show_fibonacci_bands_summary(symbol: str, timeframe: str, data: pd.DataFrame, 
                                  fib_length: int = 200, fib_mult: float = 3.0) -> dict:
    """Zeigt eine Zusammenfassung der Fibonacci Bollinger Bands."""
    if len(data) < fib_length:
        print(f"  ⓘ Nicht genug Daten für Fibonacci BB ({len(data)} < {fib_length})")
        return None
    
    bands = calculate_fibonacci_bollinger_bands(data, length=fib_length, mult=fib_mult)
    
    if bands.empty or bands['basis'].isna().all():
        print(f"  ⓘ Fibonacci BB konnte nicht berechnet werden")
        return None
    
    current_price = data['close'].iloc[-1]
    latest_bands = bands.iloc[-1]
    
    # Bestimme Position relativ zu Bändern
    if current_price <= latest_bands['lower_6']:
        position = "Bei/Unter Band 6 (stark überverkauft)"
        signal_hint = "🟢 LONG Signal!"
    elif current_price <= latest_bands['lower_3']:
        position = "Bei Band 3-6 (überverkauft)"
        signal_hint = "🟢 Long-Bias"
    elif current_price >= latest_bands['upper_6']:
        position = "Bei/Über Band 6 (stark überkauft)"
        signal_hint = "🔴 SHORT Signal!"
    elif current_price >= latest_bands['upper_3']:
        position = "Bei Band 3-6 (überkauft)"
        signal_hint = "🔴 Short-Bias"
    else:
        position = "Im mittleren Bereich (neutral)"
        signal_hint = "⚪ Kein Signal"
    
    print(f"\n  📈 Fibonacci Bollinger Bands für {symbol} ({timeframe}):")
    print(f"     VWMA Basis:              {latest_bands['basis']:.2f}")
    print(f"     Upper Band 6 (100%):     {latest_bands['upper_6']:.2f}")
    print(f"     Upper Band 3 (50%):      {latest_bands['upper_3']:.2f}")
    print(f"     Lower Band 3 (50%):      {latest_bands['lower_3']:.2f}")
    print(f"     Lower Band 6 (100%):     {latest_bands['lower_6']:.2f}")
    print(f"     Aktueller Preis:         {current_price:.2f}")
    print(f"     Position:                {position}")
    print(f"     Signal-Tendenz:          {signal_hint}")
    
    return {
        'basis': latest_bands['basis'],
        'upper_6': latest_bands['upper_6'],
        'lower_6': latest_bands['lower_6'],
        'current_price': current_price,
        'signal_hint': signal_hint
    }


def run_single_backtest(start_date: str, end_date: str, start_capital: float = 1000):
    """Führt Backtests für alle Konfigurationen durch."""
    print("=" * 60)
    print("KBot Backtest - Fibonacci BB + Volume Profile Strategie")
    print("=" * 60)
    
    configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
    all_results = []
    
    config_files = sorted([f for f in os.listdir(configs_dir) 
                          if f.startswith('config_') and f.endswith('.json')])

    if not config_files:
        print("\nKeine Konfigurationen gefunden.")
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

        print(f"\n{'─' * 50}")
        print(f"Analysiere: {strategy_name}")
        print(f"{'─' * 50}")

        # Daten laden
        data = load_data(symbol, timeframe, start_date, end_date)
        if data.empty:
            print(f"  ⚠️ Keine Daten verfügbar. Überspringe.")
            continue

        print(f"  📅 Datenbereich: {data.index.min()} bis {data.index.max()}")
        print(f"  📊 Anzahl Kerzen: {len(data)}")

        # Indikatoren-Zusammenfassung
        fib_length = config.get('strategy', {}).get('fib_length', 200)
        fib_mult = config.get('strategy', {}).get('fib_mult', 3.0)
        
        show_fibonacci_bands_summary(symbol, timeframe, data, fib_length, fib_mult)
        show_volume_profile_summary(symbol, timeframe, data)

        # Backtest durchführen
        print(f"\n  🔄 Führe Backtest durch...")
        result = run_fib_vp_backtest(data, config, start_capital=start_capital, verbose=False)
        
        print(f"\n  📊 BACKTEST-ERGEBNISSE:")
        print(f"     Trades:              {result['trades_count']}")
        print(f"     Win-Rate:            {result['win_rate']:.1f}%")
        print(f"     Gesamtrendite:       {result['total_pnl_pct']:.2f}%")
        print(f"     Max Drawdown:        {result['max_drawdown_pct']:.2f}%")
        print(f"     Profit Factor:       {result.get('profit_factor', 0):.2f}")
        print(f"     Endkapital:          ${result['end_capital']:.2f}")
        
        all_results.append({
            'strategy': strategy_name,
            'symbol': symbol,
            'timeframe': timeframe,
            **result
        })

    # Zusammenfassung
    if all_results:
        print(f"\n{'=' * 60}")
        print("GESAMTÜBERSICHT")
        print(f"{'=' * 60}")
        
        df = pd.DataFrame(all_results)
        total_return = df['total_pnl_pct'].mean()
        avg_win_rate = df['win_rate'].mean()
        total_trades = df['trades_count'].sum()
        
        print(f"\nAnzahl Strategien:     {len(all_results)}")
        print(f"Gesamte Trades:        {total_trades}")
        print(f"Durchschn. Win-Rate:   {avg_win_rate:.1f}%")
        print(f"Durchschn. Rendite:    {total_return:.2f}%")
        
        # Top/Flop Strategien
        df_sorted = df.sort_values('total_pnl_pct', ascending=False)
        
        print(f"\n🏆 TOP 3 Strategien:")
        for i, row in df_sorted.head(3).iterrows():
            print(f"   {row['strategy']}: {row['total_pnl_pct']:.2f}%")
        
        print(f"\n📉 FLOP 3 Strategien:")
        for i, row in df_sorted.tail(3).iterrows():
            print(f"   {row['strategy']}: {row['total_pnl_pct']:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="KBot Backtest-Ergebnisse anzeigen")
    parser.add_argument('--start', type=str, default='2024-01-01', 
                       help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=str(date.today()), 
                       help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=1000, 
                       help='Startkapital')
    args = parser.parse_args()
    
    run_single_backtest(args.start, args.end, args.capital)


if __name__ == "__main__":
    main()
