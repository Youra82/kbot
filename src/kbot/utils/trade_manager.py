# src/kbot/utils/trade_manager.py
# KBot: Fibonacci Bollinger Bands + Volume Profile Mean-Reversion Strategy
# =========================================================================
# STRATEGIE:
# - Long Entry: Preis bei lower_6 UND nahe VAL/PoC (Konfluenz)
# - Short Entry: Preis bei upper_6 UND nahe VAH/PoC (Konfluenz)
# - TP1: PoC (50% Position), TP2: gegenüberliegendes Band 6
# - SL: Band 1 (Long: lower_1, Short: upper_1)
# =========================================================================

import logging
import time
import ccxt
import os
import json
import pandas as pd
import numpy as np
import math

from kbot.utils.telegram import send_message
from kbot.utils.exchange import Exchange
from kbot.utils.volume_profile import calculate_volume_profile, get_volume_profile_signal

# Pfade für die Lock-Datei definieren
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
LOCK_FILE_PATH = os.path.join(PROJECT_ROOT, 'artifacts', 'db', 'trade_lock.json')


# --------------------------------------------------------------------------- #
# Fibonacci Bollinger Bands Berechnung
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Trade-Lock-Hilfsfunktionen
# --------------------------------------------------------------------------- #
def get_trade_lock(strategy_id):
    """Liest den Zeitstempel des letzten Trades für eine Strategie."""
    if not os.path.exists(LOCK_FILE_PATH):
        return None
    try:
        with open(LOCK_FILE_PATH, 'r') as f:
            locks = json.load(f)
        return locks.get(strategy_id)
    except (json.JSONDecodeError, FileNotFoundError):
        return None


def set_trade_lock(strategy_id, candle_timestamp):
    """Setzt eine Sperre für eine Strategie."""
    os.makedirs(os.path.dirname(LOCK_FILE_PATH), exist_ok=True)
    locks = {}
    if os.path.exists(LOCK_FILE_PATH):
        try:
            with open(LOCK_FILE_PATH, 'r') as f:
                locks = json.load(f)
        except json.JSONDecodeError:
            locks = {}
    locks[strategy_id] = candle_timestamp.strftime('%Y-%m-%d %H:%M:%S')
    with open(LOCK_FILE_PATH, 'w') as f:
        json.dump(locks, f, indent=4)


# --------------------------------------------------------------------------- #
# Housekeeper
# --------------------------------------------------------------------------- #
def housekeeper_routine(exchange, symbol, logger):
    """Storniert alle offenen Orders und schließt verwaiste Positionen."""
    logger.info(f"Starte Aufräum-Routine für {symbol}...")

    try:
        cancelled_count = exchange.cleanup_all_open_orders(symbol)
        if cancelled_count > 0:
            logger.info(f"{cancelled_count} verwaiste Order(s) storniert.")
    except Exception as e:
        logger.error(f"Fehler während der Order-Aufräumung: {e}")

    try:
        position = exchange.fetch_open_positions(symbol)
        if position:
            pos_info = position[0]
            close_side = 'sell' if pos_info['side'] == 'long' else 'buy'
            contracts = float(pos_info['contracts'])

            logger.warning(f"Schließe verwaiste Position ({pos_info['side']} {contracts:.6f})...")
            exchange.create_market_order(symbol, close_side, contracts, {'reduceOnly': True})
            time.sleep(2)

            if exchange.fetch_open_positions(symbol):
                logger.error("Position konnte nicht geschlossen werden!")
                return False
        return True
    except Exception as e:
        logger.error(f"Housekeeper-Fehler: {e}", exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Signal-Erkennung: Fibonacci Bollinger Bands + Volume Profile Konfluenz
# --------------------------------------------------------------------------- #
def detect_fib_vp_signal(df: pd.DataFrame, bands: pd.DataFrame, params: dict) -> dict:
    """
    Erkennt Mean-Reversion Signale basierend auf Fibonacci Bollinger Bands
    und Volume Profile Konfluenz.
    
    Entry-Logik:
    - LONG: Preis bei/unter lower_6 UND nahe VAL oder PoC
    - SHORT: Preis bei/über upper_6 UND nahe VAH oder PoC
    
    Args:
        df: OHLCV DataFrame
        bands: Fibonacci Bollinger Bands DataFrame
        params: Strategy-Parameter
    
    Returns:
        Dictionary mit Signal-Informationen
    """
    # Aktuelle Werte (letzte geschlossene Kerze = iloc[-2])
    current_close = df['close'].iloc[-2]
    current_low = df['low'].iloc[-2]
    current_high = df['high'].iloc[-2]
    candle_timestamp = df.index[-2]
    
    # Fibonacci Bands der letzten Kerze
    upper_6 = bands['upper_6'].iloc[-2]
    upper_1 = bands['upper_1'].iloc[-2]
    lower_6 = bands['lower_6'].iloc[-2]
    lower_1 = bands['lower_1'].iloc[-2]
    basis = bands['basis'].iloc[-2]
    
    # Volume Profile berechnen
    vp_lookback = params.get('volume_profile', {}).get('lookback', 200)
    vp = get_volume_profile_signal(df, current_close, lookback=vp_lookback)
    
    poc = vp['poc']
    vah = vp['vah']
    val = vp['val']
    
    # Konfluenz-Toleranz (wie weit Preis von Band/VP-Level entfernt sein darf)
    band_tolerance_pct = params.get('strategy', {}).get('band_tolerance_pct', 0.5)
    vp_tolerance_pct = params.get('strategy', {}).get('vp_tolerance_pct', 1.0)
    
    # Signal-Erkennung
    signal = {
        'side': None,
        'entry_price': current_close,
        'candle_timestamp': candle_timestamp,
        'reason': [],
        # Fibonacci Bands
        'upper_6': upper_6,
        'upper_1': upper_1,
        'lower_6': lower_6,
        'lower_1': lower_1,
        'basis': basis,
        # Volume Profile
        'poc': poc,
        'vah': vah,
        'val': val,
        'vp_position': vp['position_in_va'],
        # Konfluenz-Flags
        'at_lower_band': False,
        'at_upper_band': False,
        'near_vp_support': False,
        'near_vp_resistance': False,
        'confluence': False
    }
    
    # Prüfe ob Preis am unteren Band 6 ist (Long-Zone)
    band_tolerance = lower_6 * (band_tolerance_pct / 100)
    if current_low <= lower_6 + band_tolerance:
        signal['at_lower_band'] = True
        signal['reason'].append(f"Preis bei lower_6 ({lower_6:.2f})")
    
    # Prüfe ob Preis am oberen Band 6 ist (Short-Zone)
    band_tolerance = upper_6 * (band_tolerance_pct / 100)
    if current_high >= upper_6 - band_tolerance:
        signal['at_upper_band'] = True
        signal['reason'].append(f"Preis bei upper_6 ({upper_6:.2f})")
    
    # Prüfe VP-Konfluenz für Long (nahe VAL oder PoC)
    vp_tolerance = val * (vp_tolerance_pct / 100)
    if abs(current_close - val) <= vp_tolerance or abs(current_close - poc) <= vp_tolerance:
        signal['near_vp_support'] = True
        signal['reason'].append(f"Nahe VAL ({val:.2f}) oder PoC ({poc:.2f})")
    
    # Prüfe VP-Konfluenz für Short (nahe VAH oder PoC)
    vp_tolerance = vah * (vp_tolerance_pct / 100)
    if abs(current_close - vah) <= vp_tolerance or abs(current_close - poc) <= vp_tolerance:
        signal['near_vp_resistance'] = True
        signal['reason'].append(f"Nahe VAH ({vah:.2f}) oder PoC ({poc:.2f})")
    
    # Finale Signal-Entscheidung: Konfluenz von Fib-Band + VP-Level
    use_longs = params.get('behavior', {}).get('use_longs', True)
    use_shorts = params.get('behavior', {}).get('use_shorts', True)
    
    # LONG Signal: Bei lower_6 UND VP-Support (VAL/PoC)
    if signal['at_lower_band'] and signal['near_vp_support'] and use_longs:
        signal['side'] = 'buy'
        signal['confluence'] = True
        signal['reason'].append("✅ KONFLUENZ: Fib-Band + VP-Support")
    
    # SHORT Signal: Bei upper_6 UND VP-Resistance (VAH/PoC)
    elif signal['at_upper_band'] and signal['near_vp_resistance'] and use_shorts:
        signal['side'] = 'sell'
        signal['confluence'] = True
        signal['reason'].append("✅ KONFLUENZ: Fib-Band + VP-Resistance")
    
    return signal


# --------------------------------------------------------------------------- #
# Position eröffnen mit SL und TP
# --------------------------------------------------------------------------- #
def open_position_with_sl_tp(exchange: Exchange, signal: dict, params: dict, telegram_config: dict, logger):
    """
    Eröffnet eine Position mit Stop-Loss und Take-Profit basierend auf Fibonacci Bands.
    
    SL-Logik:
    - Long: SL bei lower_1 (erstes Fibonacci-Band)
    - Short: SL bei upper_1
    
    TP-Logik:
    - TP1 (50%): Bei PoC
    - TP2 (50%): Bei gegenüberliegendem Band 6
    """
    symbol = params['market']['symbol']
    side = signal['side']
    entry_price = signal['entry_price']
    
    # Berechne Positionsgröße basierend auf Risiko
    risk_pct = params.get('risk', {}).get('risk_per_trade_pct', 1.0) / 100
    
    # Stop-Loss Level
    if side == 'buy':
        sl_price = signal['lower_1']  # SL bei lower_1
        sl_distance_pct = (entry_price - sl_price) / entry_price
    else:
        sl_price = signal['upper_1']  # SL bei upper_1
        sl_distance_pct = (sl_price - entry_price) / entry_price
    
    # Hole Balance und berechne Positionsgröße
    try:
        balance = exchange.fetch_account_balance()
        total_balance = balance.get('total', 0)
        
        if total_balance <= 0:
            logger.error("Kein Guthaben verfügbar!")
            return False
        
        # Risikobetrag
        risk_amount = total_balance * risk_pct
        
        # Leverage
        leverage = params.get('risk', {}).get('leverage', 5)
        exchange.set_leverage(symbol, leverage)
        
        # Positionsgröße = Risikobetrag / SL-Distanz
        position_value = risk_amount / sl_distance_pct if sl_distance_pct > 0 else 0
        position_value = min(position_value, total_balance * leverage * 0.95)  # Max 95% der Margin
        
        # Contracts berechnen
        market_info = exchange.get_market_info(symbol)
        contract_size = market_info.get('contractSize', 1)
        min_qty = market_info.get('limits', {}).get('amount', {}).get('min', 0.001)
        qty_precision = market_info.get('precision', {}).get('amount', 3)
        
        contracts = position_value / entry_price / contract_size
        contracts = round(contracts, qty_precision)
        contracts = max(contracts, min_qty)
        
        logger.info(f"Position: {contracts} Kontrakte @ ~{entry_price:.2f} (Leverage: {leverage}x)")
        
    except Exception as e:
        logger.error(f"Fehler bei Positionsberechnung: {e}")
        return False
    
    # Order platzieren
    try:
        order = exchange.create_market_order(symbol, side, contracts)
        time.sleep(1)
        
        # Position verifizieren
        position = exchange.fetch_open_positions(symbol)
        if not position:
            logger.error("Position konnte nicht eröffnet werden!")
            return False
        
        pos_info = position[0]
        actual_entry = float(pos_info.get('entryPrice', entry_price))
        
        logger.info(f"✅ Position eröffnet: {side.upper()} @ {actual_entry:.2f}")
        
        # SL platzieren
        sl_side = 'sell' if side == 'buy' else 'buy'
        sl_order = exchange.create_stop_loss_order(symbol, sl_side, contracts, sl_price)
        logger.info(f"🛡️ Stop-Loss gesetzt bei {sl_price:.2f}")
        
        # TP berechnen
        if side == 'buy':
            tp1_price = signal['poc']  # TP1 bei PoC
            tp2_price = signal['upper_6']  # TP2 bei upper_6
        else:
            tp1_price = signal['poc']  # TP1 bei PoC
            tp2_price = signal['lower_6']  # TP2 bei lower_6
        
        # Telegram Nachricht
        try:
            msg = (
                f"🚀 *KBot Trade Eröffnet*\n\n"
                f"📊 *{symbol}*\n"
                f"📈 Richtung: *{side.upper()}*\n"
                f"💰 Entry: {actual_entry:.2f}\n"
                f"🛡️ Stop-Loss: {sl_price:.2f}\n"
                f"🎯 TP1 (PoC): {tp1_price:.2f}\n"
                f"🎯 TP2 (Band): {tp2_price:.2f}\n"
                f"📏 Leverage: {leverage}x\n"
                f"💵 Positionsgröße: {contracts} Kontrakte\n\n"
                f"📋 *Grund:* Fib-Band + VP Konfluenz"
            )
            send_message(telegram_config.get('bot_token'), telegram_config.get('chat_id'), msg)
        except Exception as e:
            logger.warning(f"Telegram-Nachricht fehlgeschlagen: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Fehler beim Eröffnen der Position: {e}", exc_info=True)
        return False


# --------------------------------------------------------------------------- #
# Hauptfunktion: Neue Position prüfen und eröffnen
# --------------------------------------------------------------------------- #
def check_and_open_new_position(exchange: Exchange, params: dict, telegram_config: dict, logger):
    """
    Prüft auf neue Trading-Signale basierend auf Fibonacci Bollinger Bands
    und Volume Profile Konfluenz.
    """
    symbol = params['market']['symbol']
    timeframe = params['market']['timeframe']
    strategy_id = f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"
    
    logger.info("Suche nach neuen Signalen...")
    
    # Daten laden
    data = exchange.fetch_recent_ohlcv(symbol, timeframe, limit=500)
    
    if len(data) < 200:  # Mindestens 200 Kerzen für VWMA
        logger.warning(f"Nicht genug Daten ({len(data)} < 200). Überspringe.")
        return
    
    # Prüfe ob bereits auf dieser Kerze gehandelt wurde
    last_candle_timestamp = data.index[-2]
    last_trade_timestamp_str = get_trade_lock(strategy_id)
    if last_trade_timestamp_str and last_trade_timestamp_str == last_candle_timestamp.strftime('%Y-%m-%d %H:%M:%S'):
        logger.info(f"Signal für Kerze {last_candle_timestamp} wurde bereits gehandelt. Überspringe.")
        return
    
    # Fibonacci Bollinger Bands berechnen
    fib_length = params.get('strategy', {}).get('fib_length', 200)
    fib_mult = params.get('strategy', {}).get('fib_mult', 3.0)
    bands = calculate_fibonacci_bollinger_bands(data, length=fib_length, mult=fib_mult)
    
    # Signal erkennen (Fib-Band + VP Konfluenz)
    signal = detect_fib_vp_signal(data, bands, params)
    
    # Aktuelle Werte für Log
    current_close = data['close'].iloc[-2]
    
    # *** MENSCHENLESBARE LOG-AUSGABE ***
    print("=" * 60)
    print(f"📊 SIGNAL-ANALYSE für Kerze {signal['candle_timestamp']}")
    print("-" * 60)
    print(f"💰 Aktueller Preis: {current_close:.2f}")
    print("")
    print("📈 Fibonacci Bollinger Bands:")
    print(f"   Upper 6: {signal['upper_6']:.2f} | Upper 1: {signal['upper_1']:.2f}")
    print(f"   Basis:   {signal['basis']:.2f}")
    print(f"   Lower 1: {signal['lower_1']:.2f} | Lower 6: {signal['lower_6']:.2f}")
    print("")
    print("📊 Volume Profile:")
    print(f"   VAH (Resistance): {signal['vah']:.2f}")
    print(f"   PoC (Control):    {signal['poc']:.2f}")
    print(f"   VAL (Support):    {signal['val']:.2f}")
    print(f"   Position: {signal['vp_position'].upper()}")
    print("")
    print("🔍 Konfluenz-Check:")
    at_lower = "✅" if signal['at_lower_band'] else "❌"
    at_upper = "✅" if signal['at_upper_band'] else "❌"
    vp_support = "✅" if signal['near_vp_support'] else "❌"
    vp_resistance = "✅" if signal['near_vp_resistance'] else "❌"
    print(f"   {at_lower} Am unteren Band (lower_6)")
    print(f"   {at_upper} Am oberen Band (upper_6)")
    print(f"   {vp_support} Nahe VP-Support (VAL/PoC)")
    print(f"   {vp_resistance} Nahe VP-Resistance (VAH/PoC)")
    print("-" * 60)
    
    if signal['side'] and signal['confluence']:
        print(f"🟢 ENTSCHEIDUNG: TRADE {signal['side'].upper()} wird eröffnet!")
        for reason in signal['reason']:
            print(f"   → {reason}")
        print("=" * 60)
        
        # Trade-Lock setzen
        set_trade_lock(strategy_id, last_candle_timestamp)
        
        # Position eröffnen
        success = open_position_with_sl_tp(exchange, signal, params, telegram_config, logger)
        if not success:
            logger.error("Trade konnte nicht eröffnet werden!")
    
    elif signal['at_lower_band'] or signal['at_upper_band']:
        print("🟡 ENTSCHEIDUNG: KEIN TRADE - Band erreicht, aber KEINE VP-Konfluenz")
        for reason in signal['reason']:
            print(f"   → {reason}")
        print("=" * 60)
    
    else:
        print("🔴 ENTSCHEIDUNG: KEIN TRADE - Preis nicht an Entry-Zone")
        print(f"   → Warte auf Preis bei upper_6 ({signal['upper_6']:.2f}) oder lower_6 ({signal['lower_6']:.2f})")
        print("=" * 60)


# --------------------------------------------------------------------------- #
# Haupt-Handelszyklus
# --------------------------------------------------------------------------- #
def full_trade_cycle(exchange: Exchange, params: dict, telegram_config: dict, logger):
    """
    Der Haupt-Handelszyklus für die Fibonacci Bollinger Bands + Volume Profile Strategie.
    """
    symbol = params['market']['symbol']
    timeframe = params['market'].get('timeframe', 'unknown')
    
    print("")
    print("╔" + "═" * 58 + "╗")
    print(f"║  🤖 KBOT HANDELSZYKLUS - {symbol} ({timeframe})")
    print(f"║  📐 Strategie: Fibonacci Bollinger Bands + Volume Profile")
    print("╚" + "═" * 58 + "╝")
    
    try:
        position = exchange.fetch_open_positions(symbol)
        position = position[0] if position else None

        if not position:
            print("📋 Status: Keine offene Position → Suche nach neuem Signal...")
            if not housekeeper_routine(exchange, symbol, logger):
                print("❌ Housekeeper konnte die Umgebung nicht säubern. Breche ab.")
                return
            check_and_open_new_position(exchange, params, telegram_config, logger)
        else:
            pos_side = position.get('side', 'unknown')
            pos_size = position.get('contracts', 0)
            entry_price = position.get('entryPrice', 0)
            unrealized_pnl = position.get('unrealizedPnl', 0)
            pnl_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
            print(f"📋 Status: Offene {pos_side.upper()} Position gefunden")
            print(f"   → Größe: {pos_size} Kontrakte @ {entry_price}")
            print(f"   → Unrealisierter PnL: {pnl_emoji} {unrealized_pnl:.2f} USDT")
            print(f"   → Warte auf SL/TP-Trigger...")
        
        print("─" * 60)

    except ccxt.InsufficientFunds as e:
        print(f"❌ Fehler: Nicht genügend Guthaben. {e}")
    except Exception as e:
        print(f"❌ Unerwarteter Fehler im Handelszyklus: {e}")
