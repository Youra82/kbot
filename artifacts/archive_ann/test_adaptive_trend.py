#!/usr/bin/env python3
"""
Test-Skript für den Adaptive Trend Finder
"""
import sys
import os
import pandas as pd
import numpy as np

# Projekt-Root zum Path hinzufügen
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from kbot.utils.ann_model import calculate_adaptive_trend_features, create_ann_features

def generate_test_data(periods=500, trend='up'):
    """Generiert synthetische Preisdaten mit Trend"""
    np.random.seed(42)
    
    # Basis-Preis
    base_price = 100
    
    # Trend-Komponente
    if trend == 'up':
        trend_component = np.linspace(0, 30, periods)
    elif trend == 'down':
        trend_component = np.linspace(30, 0, periods)
    else:  # sideways
        trend_component = np.sin(np.linspace(0, 4*np.pi, periods)) * 5
    
    # Noise
    noise = np.random.normal(0, 2, periods)
    
    # Finale Preise
    close_prices = base_price + trend_component + noise
    
    # DataFrame erstellen
    dates = pd.date_range(start='2024-01-01', periods=periods, freq='1h')
    df = pd.DataFrame({
        'open': close_prices * 0.99,
        'high': close_prices * 1.01,
        'low': close_prices * 0.98,
        'close': close_prices,
        'volume': np.random.uniform(1000, 5000, periods)
    }, index=dates)
    
    return df

def test_adaptive_trend_finder():
    """Testet den Adaptive Trend Finder mit verschiedenen Szenarien"""
    print("=" * 80)
    print("TEST: Adaptive Trend Finder")
    print("=" * 80)
    
    # Test 1: Aufwärtstrend
    print("\n--- Test 1: Aufwärtstrend ---")
    df_up = generate_test_data(periods=500, trend='up')
    atf_up = calculate_adaptive_trend_features(df_up, use_long_term=False)
    
    print(f"Pearson R: {atf_up['atf_pearson_r']:.4f}")
    print(f"Trend Strength: {atf_up['atf_trend_strength']:.4f}")
    print(f"Detected Period: {atf_up['atf_detected_period']}")
    print(f"Slope: {atf_up['atf_slope']:.6f}")
    print(f"Std Dev: {atf_up['atf_std_dev']:.6f}")
    print(f"Price to Trend: {atf_up['atf_price_to_trend']:.4f}")
    print(f"Upper Channel Dist: {atf_up['atf_upper_channel_dist']:.4f}")
    print(f"Lower Channel Dist: {atf_up['atf_lower_channel_dist']:.4f}")
    
    # Test 2: Abwärtstrend
    print("\n--- Test 2: Abwärtstrend ---")
    df_down = generate_test_data(periods=500, trend='down')
    atf_down = calculate_adaptive_trend_features(df_down, use_long_term=False)
    
    print(f"Pearson R: {atf_down['atf_pearson_r']:.4f}")
    print(f"Trend Strength: {atf_down['atf_trend_strength']:.4f}")
    print(f"Detected Period: {atf_down['atf_detected_period']}")
    print(f"Slope: {atf_down['atf_slope']:.6f}")
    
    # Test 3: Seitwärtstrend
    print("\n--- Test 3: Seitwärtstrend ---")
    df_sideways = generate_test_data(periods=500, trend='sideways')
    atf_sideways = calculate_adaptive_trend_features(df_sideways, use_long_term=False)
    
    print(f"Pearson R: {atf_sideways['atf_pearson_r']:.4f}")
    print(f"Trend Strength: {atf_sideways['atf_trend_strength']:.4f}")
    print(f"Detected Period: {atf_sideways['atf_detected_period']}")
    print(f"Slope: {atf_sideways['atf_slope']:.6f}")
    
    # Test 4: Integration in create_ann_features
    print("\n--- Test 4: Integration in ANN Features ---")
    df_test = generate_test_data(periods=500, trend='up')
    df_features = create_ann_features(df_test)
    
    # Überprüfe, ob ATF Features vorhanden sind
    atf_columns = [col for col in df_features.columns if col.startswith('atf_')]
    print(f"ATF Features gefunden: {len(atf_columns)}")
    print(f"ATF Features: {atf_columns}")
    
    # Zeige erste und letzte Werte
    print("\nErste Werte:")
    for col in atf_columns:
        print(f"  {col}: {df_features[col].iloc[0]:.4f}")
    
    print("\nLetzte Werte:")
    for col in atf_columns:
        print(f"  {col}: {df_features[col].iloc[-1]:.4f}")
    
    print("\n" + "=" * 80)
    print("ALLE TESTS ERFOLGREICH ABGESCHLOSSEN!")
    print("=" * 80)

if __name__ == "__main__":
    test_adaptive_trend_finder()
