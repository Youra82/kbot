#!/usr/bin/env python3
"""
Visualisierung des Adaptive Trend Finders mit echten Marktdaten
"""
import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Projekt-Root zum Path hinzufügen
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from kbot.analysis.backtester import load_data
from kbot.utils.ann_model import calculate_adaptive_trend_features

def plot_adaptive_trend(symbol, timeframe, days_back=30):
    """
    Lädt Marktdaten und visualisiert den Adaptive Trend Finder
    """
    # Daten laden
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    print(f"Lade Daten für {symbol} ({timeframe})...")
    df = load_data(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )
    
    if df.empty:
        print("Keine Daten verfügbar!")
        return
    
    print(f"Daten geladen: {len(df)} Bars")
    
    # ATF Features berechnen
    print("Berechne Adaptive Trend Features...")
    atf = calculate_adaptive_trend_features(df, use_long_term=False)
    
    # Ergebnisse ausgeben
    print("\n" + "="*80)
    print(f"ADAPTIVE TREND FINDER ANALYSE: {symbol}")
    print("="*80)
    print(f"Pearson Korrelation:     {atf['atf_pearson_r']:.4f}")
    print(f"Trend Stärke:            {atf['atf_trend_strength']:.4f}")
    print(f"Optimale Periode:        {atf['atf_detected_period']} Bars")
    print(f"Trend Slope:             {atf['atf_slope']:.6f}")
    print(f"Standardabweichung:      {atf['atf_std_dev']:.6f}")
    print(f"Preis zu Trendlinie:     {atf['atf_price_to_trend']*100:.2f}%")
    print(f"Distanz oberer Channel:  {atf['atf_upper_channel_dist']*100:.2f}%")
    print(f"Distanz unterer Channel: {atf['atf_lower_channel_dist']*100:.2f}%")
    
    # Trend-Interpretation
    print("\nINTERPRETATION:")
    if atf['atf_pearson_r'] > 0.9:
        strength_label = "Ultra/Exceptionally Strong"
    elif atf['atf_pearson_r'] > 0.8:
        strength_label = "Strong/Moderately Strong"
    elif atf['atf_pearson_r'] > 0.7:
        strength_label = "Moderate"
    else:
        strength_label = "Weak"
    
    direction = "Aufwärtstrend" if atf['atf_trend_strength'] > 0 else "Abwärtstrend"
    print(f"→ {direction} mit {strength_label} Korrelation")
    
    if abs(atf['atf_price_to_trend']) < 0.02:
        print("→ Preis nahe der Trendlinie (Trend-Following-Signal)")
    elif atf['atf_price_to_trend'] > 0.05:
        print("→ Preis deutlich über Trend (Gewinnmitnahme erwägen)")
    elif atf['atf_price_to_trend'] < -0.05:
        print("→ Preis deutlich unter Trend (Kaufgelegenheit?)")
    
    if atf['atf_upper_channel_dist'] < 0:
        print("→ WARNUNG: Preis über oberem Channel (überkauft)")
    elif atf['atf_lower_channel_dist'] < 0:
        print("→ WARNUNG: Preis unter unterem Channel (überverkauft)")
    
    print("="*80)
    
    # Visualisierung
    print("\nErstelle Visualisierung...")
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    
    # Plot 1: Preis mit Trendlinie und Channels
    close_prices = df['close'].values
    detected_period = atf['atf_detected_period']
    
    if len(close_prices) >= detected_period:
        # Trendlinie berechnen
        x_values = np.arange(detected_period)
        log_prices = np.log(close_prices[-detected_period:])
        
        # Regression durchführen
        sum_x = np.sum(x_values + 1)
        sum_xx = np.sum((x_values + 1) * (x_values + 1))
        sum_y = np.sum(log_prices)
        sum_yx = np.sum((x_values + 1) * log_prices)
        
        slope = (detected_period * sum_yx - sum_x * sum_y) / (detected_period * sum_xx - sum_x * sum_x)
        average = sum_y / detected_period
        intercept = average - slope * sum_x / detected_period + slope
        
        # Trendlinie (exponential zurück)
        trend_line = np.exp(intercept + slope * x_values)
        
        # Channels (2 sigma)
        std_dev = atf['atf_std_dev']
        upper_channel = trend_line * np.exp(2.0 * std_dev)
        lower_channel = trend_line / np.exp(2.0 * std_dev)
        
        # Plot
        plot_range = slice(-detected_period, None)
        plot_dates = df.index[plot_range]
        
        ax1.plot(plot_dates, close_prices[plot_range], label='Close Price', color='black', linewidth=1.5)
        ax1.plot(plot_dates, trend_line, label='Trend Line', color='blue', linestyle='--', linewidth=2)
        ax1.fill_between(plot_dates, upper_channel, lower_channel, alpha=0.2, color='gray', label='2σ Channel')
        ax1.plot(plot_dates, upper_channel, color='gray', linestyle=':', linewidth=1)
        ax1.plot(plot_dates, lower_channel, color='gray', linestyle=':', linewidth=1)
        
        ax1.set_title(f'{symbol} - Adaptive Trend Finder (Period: {detected_period} bars)', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Price', fontsize=12)
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
    
    # Plot 2: Pearson R und Trend Strength über Zeit
    ax2.axhline(y=atf['atf_pearson_r'], color='green', linestyle='--', label=f"Pearson R: {atf['atf_pearson_r']:.3f}")
    ax2.axhline(y=0.9, color='red', linestyle=':', alpha=0.5, label='Strong Threshold (0.9)')
    ax2.axhline(y=0.7, color='orange', linestyle=':', alpha=0.5, label='Moderate Threshold (0.7)')
    ax2.set_ylabel('Correlation', fontsize=12)
    ax2.set_title('Trend Correlation Strength', fontsize=12, fontweight='bold')
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 1)
    
    # Plot 3: Channel Distances
    ax3.axhline(y=atf['atf_upper_channel_dist']*100, color='red', linestyle='--', label=f"Upper Channel: {atf['atf_upper_channel_dist']*100:.2f}%")
    ax3.axhline(y=atf['atf_lower_channel_dist']*100, color='blue', linestyle='--', label=f"Lower Channel: {atf['atf_lower_channel_dist']*100:.2f}%")
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax3.set_ylabel('Distance (%)', fontsize=12)
    ax3.set_xlabel('Date', fontsize=12)
    ax3.set_title('Distance to Channels', fontsize=12, fontweight='bold')
    ax3.legend(loc='best')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Speichern
    filename = f"atf_analysis_{symbol.replace('/', '_').replace(':', '_')}_{timeframe}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"Grafik gespeichert: {filename}")
    
    plt.show()

if __name__ == "__main__":
    # Beispiel: Analysiere verschiedene Symbole
    symbols_to_analyze = [
        ("BTC/USDT:USDT", "1h"),
        ("ETH/USDT:USDT", "1h"),
        ("DOGE/USDT:USDT", "4h"),
    ]
    
    print("ADAPTIVE TREND FINDER - MARKTANALYSE")
    print("="*80)
    
    for symbol, timeframe in symbols_to_analyze:
        try:
            plot_adaptive_trend(symbol, timeframe, days_back=30)
            print("\n")
        except Exception as e:
            print(f"Fehler bei {symbol}: {e}")
            continue
