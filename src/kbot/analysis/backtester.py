# src/jaegerbot/analysis/backtester.py
import os
import pandas as pd
import numpy as np
from datetime import timedelta
import json
import sys
import ta # Import für ATR/ADX benötigt
import math # Import für math.ceil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.utils.exchange import Exchange
from kbot.utils.ann_model import prepare_data_for_ann, load_model_and_scaler, create_ann_features
from kbot.utils.supertrend_indicator import SuperTrendLocal

# =============================================================================
# VOLUME PROFILE - Berechnung von PoC, VAH, VAL
# =============================================================================
def calculate_volume_profile(df, num_bars=50, va_percent=68):
    """
    Berechnet das Volume Profile für einen DataFrame.
    
    Args:
        df: OHLCV DataFrame
        num_bars: Anzahl der Preis-Level für das Profil
        va_percent: Prozentsatz für die Value Area (Standard: 68%)
    
    Returns:
        dict mit: poc, vah, val, volumes, price_levels
    """
    if len(df) < 10:
        return None
    
    price_min = df['low'].min()
    price_max = df['high'].max()
    price_range = price_max - price_min
    
    if price_range <= 0:
        return None
    
    interval = price_range / num_bars
    volumes = np.zeros(num_bars)
    
    for i in range(len(df)):
        row_low = df['low'].iloc[i]
        row_high = df['high'].iloc[i]
        row_volume = df['volume'].iloc[i]
        
        for j in range(num_bars):
            price_level = price_min + interval * j
            price_level_high = price_level + interval
            
            if row_low <= price_level_high and row_high >= price_level:
                overlap_low = max(row_low, price_level)
                overlap_high = min(row_high, price_level_high)
                candle_range = row_high - row_low if row_high > row_low else 1
                overlap_pct = (overlap_high - overlap_low) / candle_range
                volumes[j] += row_volume * max(0, overlap_pct)
    
    poc_idx = np.argmax(volumes)
    poc_price = price_min + interval * (poc_idx + 0.5)
    
    total_vol = volumes.sum()
    if total_vol == 0:
        return None
    
    va_vol = total_vol * (va_percent / 100)
    va_up, va_dn = poc_idx, poc_idx
    va_sum = volumes[poc_idx]
    
    while va_sum < va_vol:
        v_up = volumes[va_up + 1] if va_up < num_bars - 1 else 0
        v_dn = volumes[va_dn - 1] if va_dn > 0 else 0
        
        if v_up == 0 and v_dn == 0:
            break
        
        if v_up >= v_dn and va_up < num_bars - 1:
            va_sum += v_up
            va_up += 1
        elif va_dn > 0:
            va_sum += v_dn
            va_dn -= 1
        else:
            break
    
    vah = price_min + interval * (va_up + 1)
    val = price_min + interval * va_dn
    
    return {
        'poc': poc_price,
        'vah': vah,
        'val': val,
        'volumes': volumes,
        'price_min': price_min,
        'price_max': price_max,
        'interval': interval
    }


def add_volume_profile_features(data, lookback=200, update_interval=5):
    """
    Fügt Volume Profile Features zum DataFrame hinzu.
    
    Args:
        data: OHLCV DataFrame
        lookback: Anzahl Kerzen für VP-Berechnung
        update_interval: VP nur alle N Kerzen neu berechnen (Performance-Optimierung)
    
    Features:
        - vp_poc: Point of Control
        - vp_vah: Value Area High
        - vp_val: Value Area Low
        - vp_poc_dist: Relative Distanz zum PoC
        - vp_vah_dist: Relative Distanz zur VAH
        - vp_val_dist: Relative Distanz zur VAL
        - vp_in_value_area: 1 wenn Preis in VA, sonst 0
        - vp_volume_at_price: Relatives Volumen am aktuellen Preis
    """
    data = data.copy()
    
    # Initialisiere Spalten
    data['vp_poc'] = np.nan
    data['vp_vah'] = np.nan
    data['vp_val'] = np.nan
    data['vp_poc_dist'] = np.nan
    data['vp_vah_dist'] = np.nan
    data['vp_val_dist'] = np.nan
    data['vp_in_value_area'] = 0
    data['vp_volume_at_price'] = np.nan
    
    last_vp = None  # Cache für VP zwischen Updates
    
    for i in range(lookback, len(data)):
        # VP nur alle N Kerzen neu berechnen
        if i % update_interval == 0 or last_vp is None:
            last_vp = calculate_volume_profile(data.iloc[i-lookback:i], num_bars=50)
        
        vp = last_vp
        if vp is None:
            continue
        
        price = data['close'].iloc[i]
        
        data.iloc[i, data.columns.get_loc('vp_poc')] = vp['poc']
        data.iloc[i, data.columns.get_loc('vp_vah')] = vp['vah']
        data.iloc[i, data.columns.get_loc('vp_val')] = vp['val']
        
        # Relative Distanzen
        if vp['poc'] > 0:
            data.iloc[i, data.columns.get_loc('vp_poc_dist')] = (price - vp['poc']) / vp['poc']
        if vp['vah'] > 0:
            data.iloc[i, data.columns.get_loc('vp_vah_dist')] = (price - vp['vah']) / vp['vah']
        if vp['val'] > 0:
            data.iloc[i, data.columns.get_loc('vp_val_dist')] = (price - vp['val']) / vp['val']
        
        # In Value Area?
        if vp['val'] <= price <= vp['vah']:
            data.iloc[i, data.columns.get_loc('vp_in_value_area')] = 1
        
        # Volume at Price
        idx = int((price - vp['price_min']) / vp['interval'])
        idx = max(0, min(idx, len(vp['volumes']) - 1))
        max_vol = vp['volumes'].max()
        if max_vol > 0:
            data.iloc[i, data.columns.get_loc('vp_volume_at_price')] = vp['volumes'][idx] / max_vol
    
    return data


# --- load_data und get_higher_timeframe ---
def load_data(symbol, timeframe, start_date_str, end_date_str):
    cache_dir = os.path.join(PROJECT_ROOT, 'data', 'cache')
    os.makedirs(cache_dir, exist_ok=True)
    symbol_filename = symbol.replace('/', '-').replace(':', '-')
    cache_file = os.path.join(cache_dir, f"{symbol_filename}_{timeframe}.csv")
    if os.path.exists(cache_file):
        data = pd.read_csv(cache_file, index_col='timestamp', parse_dates=True)
        try:
            if data.index.min() <= pd.to_datetime(start_date_str, utc=True) and data.index.max() >= pd.to_datetime(end_date_str, utc=True):
                return data.loc[start_date_str:end_date_str]
        except Exception:
            pass
    print(f"Starte Download für {symbol} ({timeframe}) von der Börse...")
    try:
        with open(os.path.join(PROJECT_ROOT, 'secret.json'), "r") as f: secrets = json.load(f)
        api_setup = secrets.get('kbot')[0]
        exchange = Exchange(api_setup)
        exchange.validate_timeframe(timeframe)
        full_data = exchange.fetch_historical_ohlcv(symbol, timeframe, start_date_str, end_date_str)
        if not full_data.empty:
            full_data.to_csv(cache_file)
            return full_data
    except Exception as e:
        print(f"Fehler beim Daten-Download: {e}")
    return pd.DataFrame()

def get_higher_timeframe(tf):
    """Wählt einen passenden höheren Zeitrahmen für den Filter."""
    # --- KORREKTUR: ADX/HTF-Logik entfernt, Funktion bleibt nur als Platzhalter
    if 'm' in tf: return '1h'
    if tf == '1h': return '4h'
    if tf in ['2h', '4h', '6h']: return '1d'
    if tf == '1d': return None
    return '1d'
    # ---

# *** NEUE HELFERFUNKTION: SuperTrend-Richtung berechnen ***
def calculate_supertrend_direction(data):
    """Berechnet die SuperTrend-Richtung für den Trendfilter."""
    st_indicator = SuperTrendLocal(data['high'], data['low'], data['close'], window=10, multiplier=3.0)
    # 1.0 für Long-Trend, -1.0 für Short-Trend
    return st_indicator.get_supertrend_direction().shift(1) # Shift, um den ST der VORHERIGEN Kerze zu verwenden


# *** HELFERFUNKTION: Volume Profile Konfluenz-Check ***
def check_vp_confluence(price, vp, tolerance_pct=1.0):
    """
    Prüft ob der aktuelle Preis nahe an einem Volume Profile Level ist.
    
    Returns:
        tuple: (is_near_support, is_near_resistance, confluence_strength)
    """
    if vp is None:
        return (False, False, 0.5)
    
    poc, vah, val = vp['poc'], vp['vah'], vp['val']
    
    # Prüfe Nähe zu Levels
    near_val = abs(price - val) / val < (tolerance_pct / 100) if val > 0 else False
    near_poc = abs(price - poc) / poc < (tolerance_pct / 100) if poc > 0 else False
    near_vah = abs(price - vah) / vah < (tolerance_pct / 100) if vah > 0 else False
    
    # Support-Levels (für Long)
    is_near_support = near_val or (near_poc and price < poc)
    
    # Resistance-Levels (für Short)
    is_near_resistance = near_vah or (near_poc and price > poc)
    
    # Konfluenz-Stärke
    confluence_strength = 0.5
    if near_poc:
        confluence_strength = 1.0  # PoC ist stärkstes Level
    elif near_val or near_vah:
        confluence_strength = 0.8
    
    return (is_near_support, is_near_resistance, confluence_strength)


# *** KORRIGIERTE BACKTESTER FUNKTION (SuperTrend + Volume Profile Filter) ***
def run_ann_backtest(data, params, model_paths, start_capital=1000, use_macd_filter=False, htf_data=None, timeframe=None, verbose=False, params_for_htf_load=None, use_volume_profile=True, vp_precomputed=False):

    model, scaler = load_model_and_scaler(model_paths['model'], model_paths['scaler'])
    if not model or not scaler: raise Exception("Modell/Scaler nicht gefunden!")

    if not timeframe:
        raise ValueError("Backtester benötigt ein 'timeframe' Argument für die Daten-Vorbereitung!")

    # Speichere VP-Spalten wenn vorberechnet
    vp_columns = ['vp_poc', 'vp_vah', 'vp_val', 'vp_poc_dist', 'vp_vah_dist', 'vp_val_dist', 'vp_in_value_area', 'vp_volume_at_price']
    vp_data = None
    if vp_precomputed and any(col in data.columns for col in vp_columns):
        vp_data = data[vp_columns].copy()

    data_with_features = create_ann_features(data.copy())
    data_with_features.dropna(inplace=True)
    
    # Füge VP-Spalten wieder hinzu wenn vorberechnet
    if vp_data is not None:
        for col in vp_columns:
            if col in vp_data.columns:
                data_with_features[col] = vp_data[col]
    
    # --- NEU: SuperTrend Richtung hinzufügen (ST-Richtung der VORHERIGEN Kerze) ---
    data_with_features['supertrend_direction'] = calculate_supertrend_direction(data_with_features)
    data_with_features.dropna(inplace=True)
    # ---

    if data_with_features.empty:
        return {"total_pnl_pct": 0, "trades_count": 0, "win_rate": 0, "max_drawdown_pct": 1.0, "end_capital": start_capital}

    # *** ERWEITERTE FEATURE-LISTE FÜR BACKTEST ***
    # Muss exakt mit ann_model.py übereinstimmen (Scaler-Feature-Reihenfolge!)
    feature_cols = [
        # Basis-Features
        'bb_width', 'bb_pband', 'obv', 'rsi', 'macd_diff', 'macd',
        'atr_normalized', 'adx', 'adx_pos', 'adx_neg',

        # Volume-Features
        'volume_ratio', 'mfi', 'cmf',

        # Trend-Features
        'price_to_ema20', 'price_to_ema50',

        # Momentum-Features
        'stoch_k', 'stoch_d', 'williams_r', 'roc', 'cci',

        # Support/Resistance
        'price_to_resistance', 'price_to_support',

        # Price Action
        'high_low_range', 'close_to_high', 'close_to_low',

        # Zeitliche Features
        'day_of_week', 'hour_of_day',

        # Returns & Volatilität
        'returns_lag1', 'returns_lag2', 'returns_lag3', 'hist_volatility',

        # Adaptive Trend Finder
        'atf_pearson_r', 'atf_trend_strength', 'atf_slope',
        'atf_std_dev', 'atf_upper_channel_dist', 'atf_lower_channel_dist',
        'atf_price_to_trend'
    ]
    # ---
    
    missing_cols = [col for col in feature_cols if col not in data_with_features.columns]
    if missing_cols:
        raise ValueError(f"Fehlende Spalten in data_with_features: {missing_cols}")

    data_for_scaling = data_with_features[feature_cols]

    features_scaled = scaler.transform(data_for_scaling)
    predictions = model.predict(features_scaled, verbose=0).flatten()
    data_with_features['prediction'] = pd.Series(predictions, index=data_with_features.index)

    pred_threshold = params.get('prediction_threshold', 0.6)
    risk_reward_ratio = params.get('risk_reward_ratio', 1.5)
    risk_per_trade_pct = params.get('risk_per_trade_pct', 1.0) / 100

    # TSL-Parameter aus Configs
    activation_rr = params.get('trailing_stop_activation_rr', 2.0)
    callback_rate = params.get('trailing_stop_callback_rate_pct', 1.0) / 100

    initial_sl_pct = params.get('initial_sl_pct', 1.0) / 100.0 # Der initiale SL ist noch prozentbasiert
    leverage = params.get('leverage', 10)
    fee_pct = 0.05 / 100

    current_capital, trades_count, wins_count = start_capital, 0, 0
    
    # *** VP EINMALIG VORBERECHNEN für Effizienz (überspringen wenn bereits vorberechnet) ***
    if use_volume_profile and not vp_precomputed:
        if verbose:
            print("  → Berechne Volume Profile (einmalig)...", end=" ", flush=True)
        data_with_features = add_volume_profile_features(data_with_features, lookback=200)
        if verbose:
            print("✓")
    # *** ENDE VP VORBERECHNUNG ***
    peak_capital, max_drawdown_pct = start_capital, 0.0
    position = None

    # --- KORREKTUR: ADX / HTF-Filter-Initialisierung entfernt ---
    # Entferne die Lade-Logik für HTF-Daten, da der ADX-Filter entfernt wurde
    # ---

    for i in range(len(data_with_features)):
        current = data_with_features.iloc[i]

        if position:
            exit_price, reason = None, None

            # *** TSL-Logik (unverändert) ***
            if position['side'] == 'long':
                if not position['trailing_active'] and current['high'] >= position['activation_price']:
                    position['trailing_active'] = True
                if position['trailing_active']:
                    position['peak_price'] = max(position['peak_price'], current['high'])
                    trailing_sl = position['peak_price'] * (1 - callback_rate)
                    position['stop_loss'] = max(position['stop_loss'], trailing_sl)
                if current['low'] <= position['stop_loss']: exit_price = position['stop_loss']
                elif not position['trailing_active'] and current['high'] >= position['take_profit']: exit_price = position['take_profit']

            elif position['side'] == 'short':
                if not position['trailing_active'] and current['low'] <= position['activation_price']:
                    position['trailing_active'] = True
                if position['trailing_active']:
                    position['peak_price'] = min(position['peak_price'], current['low'])
                    trailing_sl = position['peak_price'] * (1 + callback_rate)
                    position['stop_loss'] = min(position['stop_loss'], trailing_sl)
                if current['high'] >= position['stop_loss']: exit_price = position['stop_loss']
                elif not position['trailing_active'] and current['low'] <= position['take_profit']: exit_price = position['take_profit']
            # *** Ende TSL-Logik ***

            if exit_price:
                pnl_pct = (exit_price / position['entry_price'] - 1) if position['side'] == 'long' else (1 - exit_price / position['entry_price'])
                notional_value = position['margin_used'] * leverage
                pnl_usd = notional_value * pnl_pct
                total_fees = notional_value * fee_pct * 2
                
                # Begrenze Verlust auf den riskierten Betrag (Fix gegen Overflow)
                risk_amount_usd = start_capital * risk_per_trade_pct
                
                net_pnl = pnl_usd - total_fees
                
                if net_pnl < -risk_amount_usd:
                    net_pnl = -risk_amount_usd
                    
                current_capital += net_pnl
                
                if net_pnl > 0: wins_count += 1
                trades_count += 1
                position = None
                peak_capital = max(peak_capital, current_capital)
                if peak_capital > 0:
                    drawdown = (peak_capital - current_capital) / peak_capital
                    max_drawdown_pct = max(max_drawdown_pct, drawdown)
                if current_capital <= 0: break

        if not position:
            side = 'long' if current['prediction'] >= pred_threshold else 'short' if current['prediction'] <= (1 - pred_threshold) else None
            trade_allowed = True # Wird für den SuperTrend-Filter verwendet

            if side:
                # --- NEUER SUPER TREND FILTER ---
                st_direction = current['supertrend_direction']
                
                if st_direction == 1.0 and side == 'short':
                    trade_allowed = False # Nur Longs bei Long-Trend
                elif st_direction == -1.0 and side == 'long':
                    trade_allowed = False # Nur Shorts bei Short-Trend
                # --- ENDE NEUER SUPER TREND FILTER ---
                
                # *** VOLUME PROFILE KONFLUENZ-FILTER (nutzt vorberechnete Spalten) ***
                if trade_allowed and use_volume_profile and 'vp_val' in current.index:
                    vp_val = current.get('vp_val', np.nan)
                    vp_vah = current.get('vp_vah', np.nan)
                    vp_poc = current.get('vp_poc', np.nan)
                    price = current['close']
                    
                    if not np.isnan(vp_val) and not np.isnan(vp_vah):
                        tolerance = 0.01  # 1% Toleranz
                        
                        # Long nur wenn nahe VAL (Support) oder PoC
                        if side == 'long':
                            near_val = price <= vp_val * (1 + tolerance)
                            near_poc_support = price <= vp_poc * (1 + tolerance * 0.5)
                            if not (near_val or near_poc_support):
                                trade_allowed = False
                        
                        # Short nur wenn nahe VAH (Resistance) oder PoC
                        if side == 'short':
                            near_vah = price >= vp_vah * (1 - tolerance)
                            near_poc_resistance = price >= vp_poc * (1 - tolerance * 0.5)
                            if not (near_vah or near_poc_resistance):
                                trade_allowed = False
                # *** ENDE VOLUME PROFILE FILTER ***
                
                # *** NEUE FILTER: ADX & VOLUME (wie in trade_manager) ***
                if trade_allowed:
                    # ADX-Filter
                    current_adx = current.get('adx', 0)
                    if current_adx < 20:
                        trade_allowed = False
                    
                    # Volume-Filter (wenn vorhanden)
                    if 'volume_ratio' in current.index:
                        if current['volume_ratio'] < 0.8:
                            trade_allowed = False
                    
                    # Volatilitäts-Filter
                    if i >= 50:  # Genug Daten für Rolling Mean
                        avg_atr = data_with_features['atr_normalized'].iloc[i-50:i].mean()
                        if current['atr_normalized'] > avg_atr * 2.0:
                            trade_allowed = False
                # *** ENDE NEUE FILTER ***

                if side and trade_allowed:
                    entry_price = current['close']
                    risk_amount_usd = current_capital * risk_per_trade_pct

                    sl_distance = entry_price * initial_sl_pct
                    if sl_distance == 0: continue

                    notional_value = risk_amount_usd / initial_sl_pct
                    margin_used = notional_value / leverage
                    if margin_used > current_capital: continue

                    stop_loss_distance = entry_price * initial_sl_pct
                    stop_loss = entry_price - stop_loss_distance if side == 'long' else entry_price + stop_loss_distance

                    take_profit = entry_price + (entry_price - stop_loss) * risk_reward_ratio if side == 'long' else entry_price - (stop_loss - entry_price) * risk_reward_ratio

                    # TSL-Aktivierungspreis basierend auf Activation RR
                    activation_price = entry_price + stop_loss_distance * activation_rr if side == 'long' else entry_price - stop_loss_distance * activation_rr

                    position = {'side': side, 'entry_price': entry_price, 'stop_loss': stop_loss,
                                'take_profit': take_profit, 'margin_used': margin_used,
                                'notional_value': notional_value,
                                'trailing_active': False,
                                'activation_price': activation_price,
                                'peak_price': entry_price,
                                'callback_rate': callback_rate} # Speichern der Callback Rate für den TSL-Update

    win_rate = (wins_count / trades_count * 100) if trades_count > 0 else 0
    final_pnl_pct = ((current_capital - start_capital) / start_capital) * 100 if start_capital > 0 else 0
    return {"total_pnl_pct": final_pnl_pct, "trades_count": trades_count, "win_rate": win_rate, "max_drawdown_pct": max_drawdown_pct, "end_capital": current_capital}
