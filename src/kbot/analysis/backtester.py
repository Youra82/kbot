# src/kbot/analysis/backtester.py
# =============================================================================
# KBot Backtester: Fibonacci Bollinger Bands + Volume Profile Strategy
# =============================================================================

import os
import pandas as pd
import numpy as np
from datetime import timedelta
import json
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.utils.exchange import Exchange

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
    if 'm' in tf: return '1h'
    if tf == '1h': return '4h'
    if tf in ['2h', '4h', '6h']: return '1d'
    if tf == '1d': return None
    return '1d'


# =============================================================================
# FIBONACCI BOLLINGER BANDS
# =============================================================================
def calculate_fibonacci_bollinger_bands(df: pd.DataFrame, length: int = 200, mult: float = 3.0) -> pd.DataFrame:
    """
    Berechnet Fibonacci Bollinger Bands basierend auf VWMA.
    
    Args:
        df: OHLCV DataFrame
        length: VWMA-Periode (Standard: 200)
        mult: Standardabweichungs-Multiplikator (Standard: 3.0)
    
    Returns:
        DataFrame mit allen Fibonacci-Bändern
    """
    # HLC3 (Typical Price)
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # VWMA (Volume Weighted Moving Average)
    vwma = (hlc3 * df['volume']).rolling(window=length).sum() / df['volume'].rolling(window=length).sum()
    
    # Standardabweichung
    stdev = hlc3.rolling(window=length).std()
    
    # Basis und Deviation
    basis = vwma
    dev = mult * stdev
    
    # Fibonacci-Levels
    fib_levels = {
        1: 0.236,
        2: 0.382,
        3: 0.5,
        4: 0.618,
        5: 0.764,
        6: 1.0
    }
    
    bands = pd.DataFrame(index=df.index)
    bands['basis'] = basis
    bands['dev'] = dev
    
    for level, fib in fib_levels.items():
        bands[f'upper_{level}'] = basis + (fib * dev)
        bands[f'lower_{level}'] = basis - (fib * dev)
    
    return bands


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


# *** KORRIGIERTE BACKTESTER FUNKTION (Fibonacci BB + Volume Profile) ***
def run_fib_vp_backtest(data, params, start_capital=1000, verbose=False, return_equity=False):
    """
    Führt einen Backtest der Fibonacci BB + Volume Profile Strategie durch.
    
    Args:
        data: OHLCV DataFrame
        params: Strategy-Parameter Dictionary
        start_capital: Startkapital
        verbose: Detaillierte Ausgabe
        return_equity: Ob die Equity-Curve zurückgegeben werden soll
    
    Returns:
        Dictionary mit Backtest-Ergebnissen (und optional Equity-Curve)
    """
    # Parameter extrahieren
    fib_length = params.get('strategy', {}).get('fib_length', 200)
    fib_mult = params.get('strategy', {}).get('fib_mult', 3.0)
    vp_lookback = params.get('volume_profile', {}).get('lookback', 200)
    band_tolerance_pct = params.get('strategy', {}).get('band_tolerance_pct', 0.5) / 100
    vp_tolerance_pct = params.get('strategy', {}).get('vp_tolerance_pct', 1.0) / 100
    risk_pct = params.get('risk', {}).get('risk_per_trade_pct', 1.0) / 100
    leverage = params.get('risk', {}).get('leverage', 5)
    use_longs = params.get('behavior', {}).get('use_longs', True)
    use_shorts = params.get('behavior', {}).get('use_shorts', True)
    
    fee_pct = 0.05 / 100  # 0.05% Gebühr pro Trade
    
    # Fibonacci Bollinger Bands berechnen
    bands = calculate_fibonacci_bollinger_bands(data, length=fib_length, mult=fib_mult)
    
    # Backtest-Variablen
    capital = start_capital
    position = None
    trades = []
    trades_list = []
    equity_snapshots = []
    peak_capital = start_capital
    max_drawdown_pct = 0.0
    wins_count = 0
    
    # Mindestens fib_length + vp_lookback Kerzen für valide Berechnung
    start_idx = max(fib_length, vp_lookback) + 10
    
    for i in range(start_idx, len(data)):
        current = data.iloc[i]
        band = bands.iloc[i]
        timestamp = current.name
        
        # Equity Snapshot
        equity_snapshots.append({'timestamp': timestamp, 'equity': capital})
        
        current_close = current['close']
        current_high = current['high']
        current_low = current['low']
        
        upper_6 = band['upper_6']
        lower_6 = band['lower_6']
        upper_1 = band['upper_1']
        lower_1 = band['lower_1']
        basis = band['basis']
        
        # Volume Profile berechnen
        vp_data = data.iloc[max(0, i-vp_lookback):i]
        vp = calculate_volume_profile(vp_data)
        
        if vp is None:
            continue
        
        poc = vp['poc']
        vah = vp['vah']
        val = vp['val']
        
        # Position-Management
        if position:
            exit_price = None
            
            if position['side'] == 'long':
                # Check SL
                if current_low <= position['sl']:
                    exit_price = position['sl']
                # Check TP
                elif current_high >= position['tp']:
                    exit_price = position['tp']
                    
                if exit_price:
                    pnl_pct = (exit_price - position['entry']) / position['entry']
                    notional_value = position['margin_used'] * leverage
                    pnl_usd = notional_value * pnl_pct
                    total_fees = notional_value * fee_pct * 2
                    net_pnl = pnl_usd - total_fees
                    
                    capital += net_pnl
                    if net_pnl > 0:
                        wins_count += 1
                    
                    trades.append({
                        'side': 'long',
                        'entry': position['entry'],
                        'exit': exit_price,
                        'pnl_pct': pnl_pct * 100,
                        'result': 'TP' if exit_price >= position['tp'] else 'SL'
                    })
                    
                    entry_time_str = str(position.get('entry_time', ''))
                    exit_time_str = str(timestamp)
                    trades_list.append({
                        'entry_long': {'time': entry_time_str, 'price': position['entry']},
                        'exit_long': {'time': exit_time_str, 'price': exit_price}
                    })
                    position = None
            
            else:  # short
                # Check SL
                if current_high >= position['sl']:
                    exit_price = position['sl']
                # Check TP
                elif current_low <= position['tp']:
                    exit_price = position['tp']
                    
                if exit_price:
                    pnl_pct = (position['entry'] - exit_price) / position['entry']
                    notional_value = position['margin_used'] * leverage
                    pnl_usd = notional_value * pnl_pct
                    total_fees = notional_value * fee_pct * 2
                    net_pnl = pnl_usd - total_fees
                    
                    capital += net_pnl
                    if net_pnl > 0:
                        wins_count += 1
                    
                    trades.append({
                        'side': 'short',
                        'entry': position['entry'],
                        'exit': exit_price,
                        'pnl_pct': pnl_pct * 100,
                        'result': 'TP' if exit_price <= position['tp'] else 'SL'
                    })
                    
                    entry_time_str = str(position.get('entry_time', ''))
                    exit_time_str = str(timestamp)
                    trades_list.append({
                        'entry_short': {'time': entry_time_str, 'price': position['entry']},
                        'exit_short': {'time': exit_time_str, 'price': exit_price}
                    })
                    position = None
            
            # Update Drawdown
            peak_capital = max(peak_capital, capital)
            if peak_capital > 0:
                dd = (peak_capital - capital) / peak_capital
                max_drawdown_pct = max(max_drawdown_pct, dd)
            
            if capital <= 0:
                break
        
        # Entry-Logik (nur wenn keine Position)
        if not position:
            # LONG: Preis bei lower_6 UND nahe VAL/PoC
            at_lower_band = current_low <= lower_6 * (1 + band_tolerance_pct)
            near_vp_support = (abs(current_close - val) <= val * vp_tolerance_pct or 
                              abs(current_close - poc) <= poc * vp_tolerance_pct)
            
            if use_longs and at_lower_band and near_vp_support:
                entry_price = current_close
                sl_price = lower_1
                tp_price = poc if poc > entry_price else upper_6
                
                # Position Sizing
                risk_amount_usd = capital * risk_pct
                sl_distance_pct = abs(entry_price - sl_price) / entry_price
                if sl_distance_pct > 0:
                    notional_value = risk_amount_usd / sl_distance_pct
                    margin_used = notional_value / leverage
                    
                    if margin_used <= capital:
                        position = {
                            'side': 'long',
                            'entry': entry_price,
                            'sl': sl_price,
                            'tp': tp_price,
                            'margin_used': margin_used,
                            'entry_time': timestamp
                        }
                        if verbose:
                            print(f"  [LONG] Entry: {entry_price:.2f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}")
            
            # SHORT: Preis bei upper_6 UND nahe VAH/PoC
            at_upper_band = current_high >= upper_6 * (1 - band_tolerance_pct)
            near_vp_resistance = (abs(current_close - vah) <= vah * vp_tolerance_pct or 
                                 abs(current_close - poc) <= poc * vp_tolerance_pct)
            
            if use_shorts and at_upper_band and near_vp_resistance and position is None:
                entry_price = current_close
                sl_price = upper_1
                tp_price = poc if poc < entry_price else lower_6
                
                # Position Sizing
                risk_amount_usd = capital * risk_pct
                sl_distance_pct = abs(sl_price - entry_price) / entry_price
                if sl_distance_pct > 0:
                    notional_value = risk_amount_usd / sl_distance_pct
                    margin_used = notional_value / leverage
                    
                    if margin_used <= capital:
                        position = {
                            'side': 'short',
                            'entry': entry_price,
                            'sl': sl_price,
                            'tp': tp_price,
                            'margin_used': margin_used,
                            'entry_time': timestamp
                        }
                        if verbose:
                            print(f"  [SHORT] Entry: {entry_price:.2f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}")
    
    # Metriken berechnen
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len(trades)
    win_rate = (wins_count / num_trades * 100) if num_trades > 0 else 0
    
    # Profit Factor
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    gross_profit = sum(t['pnl_pct'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl_pct'] for t in losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    stats = {
        'total_pnl_pct': total_return,
        'trades_count': num_trades,
        'win_rate': win_rate,
        'max_drawdown_pct': max_drawdown_pct * 100,
        'end_capital': capital,
        'profit_factor': profit_factor,
        'wins': len(wins),
        'losses': len(losses),
        'trades': trades_list
    }
    
    if return_equity:
        return stats, equity_snapshots
    return stats


# Legacy-Wrapper für Kompatibilität
def run_ann_backtest(data, params, model_paths=None, start_capital=1000, use_macd_filter=False, 
                     htf_data=None, timeframe=None, verbose=False, params_for_htf_load=None, 
                     use_volume_profile=True, vp_precomputed=False, return_equity=False, **kwargs):
    """
    Legacy-Wrapper für Kompatibilität mit altem Code.
    Ruft jetzt run_fib_vp_backtest auf.
    """
    result = run_fib_vp_backtest(data, params, start_capital=start_capital, 
                                 verbose=verbose, return_equity=return_equity)
    return result
