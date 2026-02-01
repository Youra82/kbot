# tests/test_volume_channel_flow.py
# =============================================================================
# Tests für KBot: Volume Channel Flow Strategie
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
    
    dates = pd.date_range(start='2024-01-01', periods=num_candles, freq='4h')
    
    # Simuliere Trending-Markt mit Breakouts
    base_price = 50000
    prices = [base_price]
    
    for i in range(1, num_candles):
        # Trend + Random Walk
        trend = 0.0005 * (1 if i % 100 < 50 else -1)  # Wechselnder Trend
        random_walk = np.random.normal(0, 0.01)
        new_price = prices[-1] * (1 + trend + random_walk)
        prices.append(max(new_price, 1000))
    
    data = pd.DataFrame(index=dates)
    data['close'] = prices
    data['high'] = data['close'] * (1 + np.random.uniform(0, 0.02, num_candles))
    data['low'] = data['close'] * (1 - np.random.uniform(0, 0.02, num_candles))
    data['open'] = data['close'].shift(1).fillna(data['close'])
    data['volume'] = np.random.uniform(1000, 10000, num_candles)
    
    return data


class TestVolumeChannelEngine:
    """Tests für die Volume Channel Engine."""
    
    def test_process_dataframe(self):
        """Testet die Verarbeitung des DataFrames."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(300)
        engine = VolumeChannelEngine(settings={'atr_period': 50})
        
        result = engine.process_dataframe(data)
        
        # Prüfe neue Spalten
        expected_cols = ['channel_top', 'channel_bot', 'channel_avg', 
                        'channel_trend', 'breakout_signal', 'volume_delta']
        for col in expected_cols:
            assert col in result.columns, f"Spalte {col} fehlt"
        
        # Nach ATR-Periode sollten wir gültige Werte haben
        valid_rows = result.iloc[60:]
        assert not valid_rows['channel_top'].isna().all()
        assert not valid_rows['channel_bot'].isna().all()
    
    def test_channel_boundaries(self):
        """Testet dass Channel-Grenzen korrekt sind."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(300)
        engine = VolumeChannelEngine(settings={'atr_period': 50, 'channel_width': 3.0})
        
        result = engine.process_dataframe(data)
        
        # Channel Top sollte immer > Channel Bot sein
        valid = result.dropna(subset=['channel_top', 'channel_bot'])
        assert (valid['channel_top'] > valid['channel_bot']).all()
        
        # Channel Avg sollte zwischen Top und Bot liegen
        assert (valid['channel_avg'] > valid['channel_bot']).all()
        assert (valid['channel_avg'] < valid['channel_top']).all()
    
    def test_breakout_signals(self):
        """Testet dass Breakout-Signale generiert werden."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(500)
        engine = VolumeChannelEngine(settings={'atr_period': 50})
        
        result = engine.process_dataframe(data)
        
        # Es sollte mindestens ein Breakout-Signal geben
        breakouts = result[result['breakout_signal'] != 0]
        assert len(breakouts) > 0, "Keine Breakout-Signale gefunden"
        
        # Breakout-Signale sollten 1 oder -1 sein
        assert set(breakouts['breakout_signal'].unique()).issubset({1, -1})
    
    def test_get_signal(self):
        """Testet die Signal-Funktion."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(300)
        engine = VolumeChannelEngine(settings={'atr_period': 50})
        
        result = engine.process_dataframe(data)
        signal, reason = engine.get_signal(result, use_volume_confirmation=False)
        
        # Signal sollte None, 'long', oder 'short' sein
        assert signal in [None, 'long', 'short']
        assert isinstance(reason, str)
    
    def test_get_stop_loss_take_profit(self):
        """Testet SL/TP Berechnung."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(300)
        engine = VolumeChannelEngine(settings={'atr_period': 50})
        
        result = engine.process_dataframe(data)
        
        sl, tp = engine.get_stop_loss_take_profit(result, 'long', risk_reward=2.0)
        
        current_price = result['close'].iloc[-1]
        
        # Long: SL < Entry < TP
        assert sl < current_price
        assert tp > current_price
        
        sl_short, tp_short = engine.get_stop_loss_take_profit(result, 'short', risk_reward=2.0)
        
        # Short: TP < Entry < SL
        assert sl_short > current_price
        assert tp_short < current_price


class TestVolumeProfile:
    """Tests für das integrierte Volume Profile."""
    
    def test_volume_profile_calculation(self):
        """Testet die Volume Profile Berechnung."""
        from kbot.strategy.volume_channel_engine import VolumeChannelEngine
        
        data = create_sample_ohlcv_data(300)
        engine = VolumeChannelEngine(settings={
            'atr_period': 50,
            'min_channel_length': 10,
            'volume_bins': 30
        })
        
        # Berechne VP für ein Segment
        vp = engine.calculate_volume_profile(data, 100, 200)
        
        assert vp is not None
        assert vp.poc > 0
        assert vp.value_area_low < vp.poc < vp.value_area_high
        assert vp.total_volume > 0


class TestBacktest:
    """Tests für den Backtester."""
    
    def test_run_backtest(self):
        """Testet die Backtest-Funktion."""
        from kbot.analysis.backtester import run_backtest
        
        data = create_sample_ohlcv_data(500)
        
        params = {
            'strategy': {
                'atr_period': 50,
                'channel_width': 3.0,
                'use_volume_confirmation': False,
                'risk_reward_ratio': 2.0
            },
            'risk': {
                'risk_per_trade_pct': 1.0,
                'leverage': 10
            },
            'behavior': {
                'use_longs': True,
                'use_shorts': True
            }
        }
        
        result = run_backtest(data, params, start_capital=1000)
        
        # Prüfe Ergebnis-Keys
        expected_keys = ['total_pnl_pct', 'trades_count', 'win_rate', 
                        'max_drawdown_pct', 'end_capital', 'profit_factor']
        for key in expected_keys:
            assert key in result, f"Key {key} fehlt"
        
        # Plausibilitätsprüfungen
        assert result['win_rate'] >= 0 and result['win_rate'] <= 100
        assert result['max_drawdown_pct'] >= 0
        assert result['end_capital'] > 0
    
    def test_backtest_with_equity(self):
        """Testet Backtest mit Equity-Curve."""
        from kbot.analysis.backtester import run_backtest
        
        data = create_sample_ohlcv_data(500)
        params = {
            'strategy': {'atr_period': 50, 'channel_width': 3.0},
            'risk': {'risk_per_trade_pct': 1.0, 'leverage': 10},
            'behavior': {'use_longs': True, 'use_shorts': True}
        }
        
        result, equity = run_backtest(data, params, start_capital=1000, 
                                      return_equity=True)
        
        assert isinstance(equity, list)
        assert len(equity) > 0


class TestConfigFiles:
    """Tests für Konfigurationsdateien."""
    
    def test_config_structure(self):
        """Testet dass alle Configs die richtige Struktur haben."""
        configs_dir = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs')
        
        if not os.path.exists(configs_dir):
            pytest.skip("Configs-Verzeichnis nicht gefunden")
        
        config_files = [f for f in os.listdir(configs_dir) 
                       if f.startswith('config_') and f.endswith('.json')]
        
        assert len(config_files) > 0, "Keine Config-Dateien gefunden"
        
        required_sections = ['market', 'strategy', 'risk', 'behavior']
        
        for filename in config_files:
            config_path = os.path.join(configs_dir, filename)
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            for section in required_sections:
                assert section in config, f"{filename}: Sektion '{section}' fehlt"
            
            # Prüfe Volume Channel Flow Parameter
            assert 'atr_period' in config['strategy'], f"{filename}: atr_period fehlt"
            assert 'channel_width' in config['strategy'], f"{filename}: channel_width fehlt"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
