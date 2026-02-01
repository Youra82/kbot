# tests/test_fib_vp_strategy.py
# =============================================================================
# Tests für KBot: Fibonacci Bollinger Bands + Volume Profile Strategie
# =============================================================================

import pytest
import os
import sys
import json
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))


def create_sample_ohlcv_data(num_candles: int = 300) -> pd.DataFrame:
    """Erstellt synthetische OHLCV-Daten für Tests."""
    np.random.seed(42)
    
    # Simuliere einen Mean-Reversion Markt
    dates = pd.date_range(start='2024-01-01', periods=num_candles, freq='4h')
    
    # Basispreis mit Mean-Reversion
    base_price = 50000
    prices = [base_price]
    for i in range(1, num_candles):
        # Mean-Reversion: Tendenz zum Basispreis zurückzukehren
        deviation = prices[-1] - base_price
        mean_reversion = -0.01 * deviation
        random_walk = np.random.normal(0, 100)
        new_price = prices[-1] + mean_reversion + random_walk
        prices.append(max(new_price, 1000))  # Mindestpreis
    
    # OHLCV erstellen
    data = pd.DataFrame(index=dates)
    data['close'] = prices
    data['high'] = data['close'] * (1 + np.random.uniform(0, 0.02, num_candles))
    data['low'] = data['close'] * (1 - np.random.uniform(0, 0.02, num_candles))
    data['open'] = data['close'].shift(1).fillna(data['close'])
    data['volume'] = np.random.uniform(1000, 10000, num_candles)
    
    return data


class TestFibonacciBollingerBands:
    """Tests für die Fibonacci Bollinger Bands Berechnung."""
    
    def test_calculate_fibonacci_bands(self):
        """Testet die Berechnung der Fibonacci Bollinger Bands."""
        from kbot.analysis.backtester import calculate_fibonacci_bollinger_bands
        
        data = create_sample_ohlcv_data(250)
        bands = calculate_fibonacci_bollinger_bands(data, length=200, mult=3.0)
        
        # Prüfe, dass alle erwarteten Spalten existieren
        expected_cols = ['basis', 'dev', 'upper_1', 'lower_1', 'upper_6', 'lower_6']
        for col in expected_cols:
            assert col in bands.columns, f"Spalte {col} fehlt in den Bändern"
        
        # Nach 200 Kerzen sollten wir gültige Werte haben
        assert not bands['basis'].iloc[-1:].isna().any(), "Basis sollte berechnet sein"
        assert not bands['upper_6'].iloc[-1:].isna().any(), "Upper Band 6 sollte berechnet sein"
        
        # Fibonacci-Hierarchie: Band 6 > Band 3 > Band 1
        last_bands = bands.iloc[-1]
        assert last_bands['upper_6'] > last_bands['upper_3'] > last_bands['upper_1']
        assert last_bands['lower_6'] < last_bands['lower_3'] < last_bands['lower_1']
    
    def test_fibonacci_levels_correct(self):
        """Testet, dass die Fibonacci-Level korrekt berechnet werden."""
        from kbot.analysis.backtester import calculate_fibonacci_bollinger_bands
        
        data = create_sample_ohlcv_data(250)
        bands = calculate_fibonacci_bollinger_bands(data, length=200, mult=3.0)
        
        last = bands.iloc[-1]
        basis = last['basis']
        dev = last['dev']
        
        # Prüfe Fibonacci-Level (mit Toleranz für Rundungsfehler)
        assert abs(last['upper_1'] - (basis + 0.236 * dev)) < 0.01
        assert abs(last['upper_6'] - (basis + 1.0 * dev)) < 0.01
        assert abs(last['lower_1'] - (basis - 0.236 * dev)) < 0.01
        assert abs(last['lower_6'] - (basis - 1.0 * dev)) < 0.01


class TestVolumeProfile:
    """Tests für die Volume Profile Berechnung."""
    
    def test_calculate_volume_profile(self):
        """Testet die Berechnung des Volume Profiles."""
        from kbot.analysis.backtester import calculate_volume_profile
        
        data = create_sample_ohlcv_data(200)
        vp = calculate_volume_profile(data, num_bars=50, va_percent=68)
        
        assert vp is not None, "Volume Profile sollte berechnet werden"
        assert 'poc' in vp, "PoC (Point of Control) fehlt"
        assert 'vah' in vp, "VAH (Value Area High) fehlt"
        assert 'val' in vp, "VAL (Value Area Low) fehlt"
        
        # VAL < PoC < VAH
        assert vp['val'] <= vp['poc'] <= vp['vah'], "VAL <= PoC <= VAH sollte gelten"
    
    def test_volume_profile_with_insufficient_data(self):
        """Testet Volume Profile mit zu wenigen Daten."""
        from kbot.analysis.backtester import calculate_volume_profile
        
        data = create_sample_ohlcv_data(5)  # Nur 5 Kerzen
        vp = calculate_volume_profile(data)
        
        assert vp is None, "VP sollte None sein bei zu wenigen Daten"


class TestBacktest:
    """Tests für die Backtest-Funktion."""
    
    def test_run_fib_vp_backtest(self):
        """Testet die Backtest-Funktion."""
        from kbot.analysis.backtester import run_fib_vp_backtest
        
        data = create_sample_ohlcv_data(400)
        
        params = {
            'strategy': {
                'fib_length': 200,
                'fib_mult': 3.0,
                'band_tolerance_pct': 0.5,
                'vp_tolerance_pct': 1.0
            },
            'volume_profile': {
                'lookback': 200
            },
            'risk': {
                'risk_per_trade_pct': 1.0,
                'leverage': 5
            },
            'behavior': {
                'use_longs': True,
                'use_shorts': True
            }
        }
        
        result = run_fib_vp_backtest(data, params, start_capital=1000)
        
        # Prüfe, dass alle erwarteten Keys existieren
        expected_keys = ['total_pnl_pct', 'trades_count', 'win_rate', 
                        'max_drawdown_pct', 'end_capital']
        for key in expected_keys:
            assert key in result, f"Key {key} fehlt im Ergebnis"
        
        # Plausibilitätsprüfungen
        assert result['win_rate'] >= 0 and result['win_rate'] <= 100
        assert result['max_drawdown_pct'] >= 0
        assert result['end_capital'] > 0
    
    def test_backtest_with_equity_curve(self):
        """Testet, dass die Equity-Curve zurückgegeben wird."""
        from kbot.analysis.backtester import run_fib_vp_backtest
        
        data = create_sample_ohlcv_data(400)
        params = {
            'strategy': {'fib_length': 200, 'fib_mult': 3.0},
            'volume_profile': {'lookback': 200},
            'risk': {'risk_per_trade_pct': 1.0, 'leverage': 5},
            'behavior': {'use_longs': True, 'use_shorts': True}
        }
        
        result, equity = run_fib_vp_backtest(data, params, start_capital=1000, 
                                            return_equity=True)
        
        assert isinstance(equity, list), "Equity sollte eine Liste sein"
        assert len(equity) > 0, "Equity-Curve sollte Einträge haben"


class TestTradeManager:
    """Tests für den Trade Manager."""
    
    def test_fibonacci_bollinger_bands_function(self):
        """Testet die Fibonacci BB Funktion im Trade Manager."""
        from kbot.utils.trade_manager import calculate_fibonacci_bollinger_bands
        
        data = create_sample_ohlcv_data(250)
        bands = calculate_fibonacci_bollinger_bands(data, length=200, mult=3.0)
        
        assert 'basis' in bands.columns
        assert 'upper_6' in bands.columns
        assert 'lower_6' in bands.columns
    
    def test_detect_fib_vp_signal(self):
        """Testet die Signal-Erkennung."""
        from kbot.utils.trade_manager import detect_fib_vp_signal
        from kbot.utils.volume_profile import calculate_volume_profile
        
        data = create_sample_ohlcv_data(250)
        
        # Hole aktuelle Werte
        current_close = data['close'].iloc[-1]
        current_high = data['high'].iloc[-1]
        current_low = data['low'].iloc[-1]
        
        # Berechne Indikatoren
        from kbot.utils.trade_manager import calculate_fibonacci_bollinger_bands
        bands = calculate_fibonacci_bollinger_bands(data, length=200, mult=3.0)
        last_band = bands.iloc[-1]
        
        vp = calculate_volume_profile(data.iloc[-200:])
        
        # Signal-Erkennung
        signal, reason = detect_fib_vp_signal(
            current_close, current_high, current_low,
            last_band, vp,
            band_tolerance_pct=0.5, vp_tolerance_pct=1.0
        )
        
        # Signal sollte 'long', 'short', oder None sein
        assert signal in ['long', 'short', None], f"Ungültiges Signal: {signal}"


class TestConfigFiles:
    """Tests für Konfigurationsdateien."""
    
    def test_config_structure(self):
        """Testet, dass alle Configs die richtige Struktur haben."""
        configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
        
        if not os.path.exists(configs_dir):
            pytest.skip("Configs-Verzeichnis nicht gefunden")
        
        config_files = [f for f in os.listdir(configs_dir) 
                       if f.startswith('config_') and f.endswith('.json')]
        
        assert len(config_files) > 0, "Keine Config-Dateien gefunden"
        
        required_sections = ['market', 'strategy', 'volume_profile', 'risk', 'behavior']
        
        for filename in config_files:
            config_path = os.path.join(configs_dir, filename)
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            for section in required_sections:
                assert section in config, f"{filename}: Sektion '{section}' fehlt"
            
            # Prüfe Fibonacci-Parameter
            assert 'fib_length' in config['strategy'], f"{filename}: fib_length fehlt"
            assert 'fib_mult' in config['strategy'], f"{filename}: fib_mult fehlt"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
