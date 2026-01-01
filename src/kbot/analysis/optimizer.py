#!/usr/bin/env python3
# src/kbot/analysis/optimizer.py
# KBot: Parameter-Optimierung für Kanal-Erkennungs-Strategie

import os
import sys
import json
import argparse
import numpy as np
from datetime import datetime, timedelta
import logging
from tqdm import tqdm
from itertools import product

# Setup Python Path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from kbot.strategy.run import load_ohlcv, detect_channels, channel_backtest

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def optimize_parameters(symbol, timeframe, start_date, end_date, start_capital=1000):
    """
    Optimiert die Kanal-Erkennungs-Parameter mittels Grid-Search.
    
    Args:
        symbol: Trading-Symbol (z.B. BTCUSDT)
        timeframe: Timeframe (z.B. 1d, 4h)
        start_date: Startdatum (YYYY-MM-DD)
        end_date: Enddatum (YYYY-MM-DD)
        start_capital: Startkapital in USD
    
    Returns:
        Dict mit optimalen Parametern und Ergebnissen
    """
    
    print(f"\n{'=' * 70}")
    print(f"Optimiere Parameter für {symbol} ({timeframe})")
    print(f"Zeitraum: {start_date} bis {end_date}")
    print(f"{'=' * 70}")
    
    try:
        # Lade Kursdaten
        df = load_ohlcv(symbol, start_date, end_date, timeframe)
        
        if df.empty or len(df) < 60:
            logger.error(f"Nicht genügend Kursdaten für {symbol} ({timeframe})")
            return None
        
        logger.info(f"Geladen: {len(df)} Kerzen")
        
        # Parameter-Grid für Grid-Search
        # window: Fenster-Größe für Kanal-Analyse
        # min_channel_width: Minimale Kanal-Breite (%)
        # slope_threshold: Minimale Steigung für bedeutungsvolle Trends
        # Erweitertes Grid für bessere Genauigkeit (1024 Kombinationen statt 243)
        param_grid = {
            'window': [35, 40, 45, 50, 55, 60],
            'min_channel_width': [0.0005, 0.001, 0.0015, 0.002, 0.0025, 0.003],
            'slope_threshold': [0.005, 0.01, 0.015, 0.02, 0.025, 0.03],
            'entry_threshold': [0.005, 0.01, 0.015, 0.02],
            'exit_threshold': [0.015, 0.02, 0.025, 0.03],
        }
        
        best_result = {
            'symbol': symbol,
            'timeframe': timeframe,
            'total_return': -999,
            'win_rate': 0,
            'num_trades': 0,
            'max_dd': 0,
            'params': {}
        }
        
        # Erstelle alle Parameter-Kombinationen für Grid-Search
        param_combinations = list(product(
            param_grid['window'],
            param_grid['min_channel_width'],
            param_grid['slope_threshold'],
            param_grid['entry_threshold'],
            param_grid['exit_threshold']
        ))
        
        logger.info(f"Starte Grid-Search mit {len(param_combinations)} Kombinationen...")
        print()  # Leerzeile für schönere Ausgabe
        
        # Grid-Search mit Ladebalken
        for window, min_width, slope_thresh, entry_thresh, exit_thresh in tqdm(
            param_combinations,
            desc=f"Optimiere {symbol} ({timeframe})",
            unit="combo",
            ncols=80
        ):
            try:
                # Erkenne Kanäle mit aktuellen Parametern
                channels = detect_channels(
                    df,
                    window=window,
                    min_channel_width=min_width,
                    slope_threshold=slope_thresh
                )
                
                # Backtest durchführen
                end_capital, total_return, num_trades, win_rate, trades, max_dd = channel_backtest(
                    df,
                    channels,
                    start_capital=start_capital,
                    entry_threshold=entry_thresh,
                    exit_threshold=exit_thresh
                )
                
                # Bewertungs-Score berechnen
                # Priorität: Return > Win Rate > Drawdown
                if num_trades > 0:
                    # Risk-adjusted Return
                    if max_dd < 0:
                        risk_adjusted_return = total_return / abs(max_dd)
                    else:
                        risk_adjusted_return = total_return * 1.5
                    
                    score = risk_adjusted_return + (win_rate * 0.5)
                else:
                    score = -999
                
                # Update Best
                if score > best_result['total_return']:
                    best_result = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'total_return': total_return,
                        'win_rate': win_rate,
                        'num_trades': num_trades,
                        'max_dd': max_dd,
                        'end_capital': end_capital,
                        'score': score,
                        'params': {
                            'window': window,
                            'min_channel_width': min_width,
                            'slope_threshold': slope_thresh,
                            'entry_threshold': entry_thresh,
                            'exit_threshold': exit_thresh
                        }
                    }
            
            except Exception as e:
                logger.debug(f"Fehler bei Kombination: {str(e)}")
                continue
        
        # Ergebnisse anzeigen
        if best_result['num_trades'] > 0:
            print(f"\n{'=' * 70}")
            print(f"OPTIMALE PARAMETER GEFUNDEN für {symbol} ({timeframe})")
            print(f"{'=' * 70}")
            print(f"✓ Endkapital:      ${best_result['end_capital']:,.2f}")
            print(f"✓ Gesamtrendite:   {best_result['total_return']:.2f}%")
            print(f"✓ Anzahl Trades:   {best_result['num_trades']}")
            print(f"✓ Gewinnquote:     {best_result['win_rate']:.1f}%")
            print(f"✓ Max Drawdown:    {best_result['max_dd']:.2f}%")
            print(f"\nOptimale Parameter:")
            print(f"  - Window:              {best_result['params']['window']}")
            print(f"  - Min Channel Width:   {best_result['params']['min_channel_width']:.4f}")
            print(f"  - Slope Threshold:     {best_result['params']['slope_threshold']:.4f}")
            print(f"  - Entry Threshold:     {best_result['params']['entry_threshold']:.4f}")
            print(f"  - Exit Threshold:      {best_result['params']['exit_threshold']:.4f}")
            print(f"{'=' * 70}\n")
            
            return best_result
        else:
            logger.warning(f"Keine profitablen Parameter-Kombinationen gefunden für {symbol} ({timeframe})")
            return None
    
    except Exception as e:
        logger.error(f"Fehler bei Parameter-Optimierung für {symbol} ({timeframe}): {str(e)}")
        return None


def save_optimal_config(result, output_dir):
    """Speichere optimale Konfiguration als JSON"""
    
    if not result:
        return None
    
    os.makedirs(output_dir, exist_ok=True)
    
    config_filename = f"optimal_{result['symbol']}_{result['timeframe']}.json"
    config_path = os.path.join(output_dir, config_filename)
    
    config = {
        'symbol': result['symbol'],
        'timeframe': result['timeframe'],
        'parameters': result['params'],
        'performance': {
            'total_return': result['total_return'],
            'win_rate': result['win_rate'],
            'num_trades': result['num_trades'],
            'max_drawdown': result['max_dd'],
            'end_capital': result['end_capital']
        },
        'timestamp': datetime.now().isoformat()
    }
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"Konfiguration gespeichert: {config_path}")
    return config_path


def main():
    parser = argparse.ArgumentParser(
        description="KBot Parameter-Optimizer für Kanal-Erkennungs-Strategie"
    )
    parser.add_argument('--symbol', type=str, required=True, help='Trading-Symbol (z.B. BTCUSDT)')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe (z.B. 1d, 4h)')
    parser.add_argument('--start-date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start-capital', type=float, default=1000, help='Startkapital (Standard: 1000)')
    parser.add_argument('--save-config', action='store_true', help='Speichere optimale Konfiguration')
    
    args = parser.parse_args()
    
    # Optimiere Parameter
    result = optimize_parameters(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=args.start_date,
        end_date=args.end_date,
        start_capital=args.start_capital
    )
    
    # Speichere Konfiguration wenn gewünscht
    if result and args.save_config:
        config_dir = os.path.join(PROJECT_ROOT, 'artifacts', 'optimal_configs')
        save_optimal_config(result, config_dir)


if __name__ == "__main__":
    main()
