# src/kbot/analysis/show_results.py
# =============================================================================
# KBot: Backtest-Ergebnisse anzeigen (Volume Channel Flow)
# =============================================================================

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import date
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data, run_backtest
from kbot.strategy.volume_channel_engine import VolumeChannelEngine


def show_channel_summary(symbol: str, timeframe: str, data: pd.DataFrame, 
                          params: dict) -> dict:
    """Zeigt eine Zusammenfassung des Volume Channel Flow."""
    strategy = params.get('strategy', {})
    
    engine = VolumeChannelEngine(settings=strategy)
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
    
    print(f"\n  📊 Volume Channel Flow für {symbol} ({timeframe}):")
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


def run_single_backtest(start_date: str, end_date: str, start_capital: float = 1000):
    """Führt Backtests für alle Konfigurationen durch."""
    print("=" * 60)
    print("KBot Backtest - Volume Channel Flow Strategie")
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

        # Channel-Zusammenfassung
        show_channel_summary(symbol, timeframe, data, config)

        # Backtest durchführen
        print(f"\n  🔄 Führe Backtest durch...")
        result = run_backtest(data, config, start_capital=start_capital, verbose=False)
        
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
        avg_pf = df['profit_factor'].mean()
        
        print(f"\nAnzahl Strategien:     {len(all_results)}")
        print(f"Gesamte Trades:        {total_trades}")
        print(f"Durchschn. Win-Rate:   {avg_win_rate:.1f}%")
        print(f"Durchschn. Rendite:    {total_return:.2f}%")
        print(f"Durchschn. PF:         {avg_pf:.2f}")
        
        # Top/Flop Strategien
        df_sorted = df.sort_values('total_pnl_pct', ascending=False)
        
        print(f"\n🏆 TOP 3 Strategien:")
        for _, row in df_sorted.head(3).iterrows():
            print(f"   {row['strategy']}: {row['total_pnl_pct']:.2f}%")
        
        if len(df_sorted) > 3:
            print(f"\n📉 FLOP 3 Strategien:")
            for _, row in df_sorted.tail(3).iterrows():
                print(f"   {row['strategy']}: {row['total_pnl_pct']:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="KBot Backtest-Ergebnisse anzeigen")
    parser.add_argument('--mode', type=int, default=1, choices=[1, 2, 3, 4],
                       help='Analyse-Modus: 1=Einzel, 2=Portfolio, 3=Optimizer, 4=Charts')
    parser.add_argument('--start', type=str, default='2024-01-01', 
                       help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=str(date.today()), 
                       help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=1000, 
                       help='Startkapital')
    args = parser.parse_args()
    
    # Alle Modi führen aktuell den gleichen Backtest aus
    run_single_backtest(args.start, args.end, args.capital)


if __name__ == "__main__":
    main()
