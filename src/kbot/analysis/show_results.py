#!/usr/bin/env python3
# src/kbot/analysis/show_results.py
# KBot: Interaktives Backtest-Tool für Kanalstrategie

import os
import sys
import argparse
from datetime import date

# Setup Python Path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from kbot.strategy.run import load_ohlcv, detect_channels, channel_backtest


def format_currency(value):
    """Formatiere Wert als Währung"""
    return f"${value:,.2f}"


def format_percent(value):
    """Formatiere Wert als Prozentsatz"""
    return f"{value:.2f}%"


def run_backtest_interactive():
    """Interaktiver Backtest mit Einzelsymbolen"""
    print("\n" + "=" * 60)
    print("KBot Backtest-Tool (Kanalstrategie)")
    print("=" * 60)
    
    # Input erfassen
    symbols = input("\nSymbol(e) (z.B. BTCUSDT ETHUSDT): ").strip().split()
    if not symbols:
        print("Keine Symbole eingegeben. Abgebrochen.")
        return
    
    timeframes = input("Timeframe(s) (z.B. 4h 1d): ").strip().split()
    if not timeframes:
        print("Keine Timeframes eingegeben. Abgebrochen.")
        return
    
    start_date = input("Startdatum (YYYY-MM-DD): ").strip()
    if not start_date:
        print("Kein Startdatum eingegeben. Abgebrochen.")
        return
    
    end_date = input("Enddatum (YYYY-MM-DD, Enter = heute): ").strip()
    if not end_date:
        end_date = str(date.today())
    
    try:
        start_capital = float(input("Startkapital (USD, z.B. 1000): ").strip())
    except ValueError:
        print("Ungültige Eingabe für Startkapital. Standard: 1000 USD")
        start_capital = 1000
    
    print("\n" + "=" * 60)
    
    # Backtest durchführen für jede Kombination
    all_results = []
    
    for symbol in symbols:
        for timeframe in timeframes:
            result = run_single_backtest(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                start_capital=start_capital
            )
            if result:
                all_results.append(result)
    
    # Zusammenfassung
    if all_results:
        print("\n" + "=" * 60)
        print("BACKTEST-ZUSAMMENFASSUNG")
        print("=" * 60)
        
        total_capital = start_capital
        total_trades = 0
        total_profit = 0
        
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
            
            total_capital += (end_cap - start_capital)
            total_trades += trades
            total_profit += (ret / 100 * start_capital)
            
            print(f"{symbol:<12} {timeframe:<6} {format_currency(end_cap):<15} {format_percent(ret):<10} {trades:<8} {format_percent(wr):<10} {format_percent(dd):<10}")
        
        print("-" * 70)
        overall_return = ((total_capital - len(all_results) * start_capital) / (len(all_results) * start_capital)) * 100 if all_results else 0
        print(f"{'GESAMT':<12} {'':<6} {format_currency(total_capital):<15} {format_percent(overall_return):<10} {total_trades:<8}")
        print("=" * 60)


def run_single_backtest(symbol, timeframe, start_date, end_date, start_capital):
    """Führe einen einzelnen Backtest durch"""
    
    print(f"\nStarte Backtest für {symbol} ({timeframe})...")
    print("-" * 60)
    
    try:
        # Kursdaten laden
        df = load_ohlcv(symbol, start_date, end_date, timeframe)
        
        if df.empty or len(df) < 60:
            print(f"⚠️  Nicht genügend Kursdaten für {symbol} ({timeframe}). Min. 60 Kerzen erforderlich.")
            return None
        
        # Kanäle erkennen mit optimierten Parametern
        channels = detect_channels(
            df, 
            window=50,
            min_channel_width=0.002,  # 0.2% Minimum Breite
            slope_threshold=0.02       # Geringere Slope-Anforderung
        )
        
        # Backtest durchführen
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


def main():
    parser = argparse.ArgumentParser(
        description="KBot Interaktives Backtest-Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python3 show_results.py              # Interaktiver Modus
  python3 show_results.py --symbol BTCUSDT --timeframe 1d --start-date 2025-01-01 --start-capital 1000
        """
    )
    
    parser.add_argument('--symbol', type=str, help='Symbol (z.B. BTCUSDT)')
    parser.add_argument('--timeframe', type=str, help='Timeframe (z.B. 1d, 4h)')
    parser.add_argument('--start-date', type=str, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='Enddatum (YYYY-MM-DD, Standard: heute)')
    parser.add_argument('--start-capital', type=float, default=1000, help='Startkapital in USD (Standard: 1000)')
    
    args = parser.parse_args()
    
    # Wenn alle erforderlichen Argumente vorhanden sind, stille Ausführung
    if args.symbol and args.timeframe and args.start_date:
        result = run_single_backtest(
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date or date.today().isoformat(),
            start_capital=args.start_capital
        )
    else:
        # Interaktiver Modus
        run_backtest_interactive()


if __name__ == "__main__":
    main()
