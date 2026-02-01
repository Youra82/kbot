#!/usr/bin/env python3
# src/kbot/strategy/run.py
# =============================================================================
# KBot: Fibonacci Bollinger Bands + Volume Profile Mean-Reversion Strategy
# =============================================================================
# STRATEGIE:
# - Fibonacci Bollinger Bands: VWMA-basierte Bänder mit 6 Fibonacci-Levels
# - Volume Profile: PoC (Point of Control), VAH, VAL Berechnung
# - Entry: Nur bei Konfluenz von Fib-Band UND Volume-Level
# - Long: Preis bei lower_6 + nahe VAL/PoC
# - Short: Preis bei upper_6 + nahe VAH/PoC
# - SL: Band 1 (Long: lower_1, Short: upper_1)
# - TP: PoC (50%), gegenüberliegendes Band 6 (50%)
# =============================================================================

import sys
import argparse
import pandas as pd
import numpy as np
import datetime
import ccxt
import os

# Ensure local `src` is on sys.path
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)


# --------------------------------------------------------------------------- #
# Hilfsfunktion: Kursdaten laden (Bitget via ccxt)
# --------------------------------------------------------------------------- #
def load_ohlcv(symbol, start, end, timeframe):
    """Lädt OHLCV-Daten von Bitget."""
    exchange = ccxt.bitget()
    
    # Symbol-Format anpassen
    if '/' not in symbol:
        if symbol.upper().endswith('USDT'):
            symbol = symbol[:-4]
        symbol = symbol.upper() + '/USDT:USDT'
    elif not symbol.endswith(':USDT'):
        symbol = symbol + ':USDT'
    
    since = int(pd.Timestamp(start).timestamp() * 1000)
    end_ts = int(pd.Timestamp(end).timestamp() * 1000)
    tf_map = {'1d':'1d','4h':'4h','1h':'1h','6h':'6h','30m':'30m','15m':'15m','5m':'5m','10m':'10m','2h':'2h'}
    tf = tf_map.get(timeframe, '1d')
    
    timeframe_duration_in_ms = exchange.parse_timeframe(tf) * 1000
    
    all_ohlcv = []
    limit = 500
    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv += ohlcv
        last = ohlcv[-1][0]
        since = last + timeframe_duration_in_ms
        
    if not all_ohlcv:
        raise Exception(f"Keine Daten von Bitget für {symbol}")
        
    df = pd.DataFrame(all_ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    return df[['open','high','low','close','volume']]


# --------------------------------------------------------------------------- #
# Fibonacci Bollinger Bands Berechnung
# --------------------------------------------------------------------------- #
def fibonacci_bollinger_bands(df, length=200, mult=3.0):
    """
    Fibonacci Bollinger Bands Strategy.
    
    Args:
        df: OHLC DataFrame
        length: VWMA-Periode (Standard: 200)
        mult: Standardabweichungs-Multiplikator (Standard: 3.0)

    Returns:
        DataFrame mit Bändern: upper_1-6, lower_1-6, basis
    """
    # HLC3 (Typical Price)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    # VWMA (Volume Weighted Moving Average)
    vwma = (typical_price * df['volume']).rolling(window=length).sum() / df['volume'].rolling(window=length).sum()

    # Standardabweichung
    stdev = typical_price.rolling(window=length).std()

    # Basis und Deviation
    basis = vwma
    dev = mult * stdev

    # Fibonacci-Level
    fib_levels = [0.236, 0.382, 0.5, 0.618, 0.764, 1.0]

    bands = pd.DataFrame(index=df.index)
    bands['basis'] = basis
    bands['dev'] = dev

    for i, fib in enumerate(fib_levels, start=1):
        bands[f'upper_{i}'] = basis + (fib * dev)
        bands[f'lower_{i}'] = basis - (fib * dev)

    bands['type'] = 'fibonacci'

    return bands


# --------------------------------------------------------------------------- #
# Volume Profile Berechnung (für Backtest)
# --------------------------------------------------------------------------- #
def calculate_volume_profile_simple(df, lookback=200):
    """Vereinfachte Volume Profile Berechnung für Backtest."""
    data = df.tail(lookback)
    
    if len(data) < 10:
        return {'poc': df['close'].iloc[-1], 'vah': df['close'].iloc[-1], 'val': df['close'].iloc[-1]}
    
    num_bins = 50
    highest = data['high'].max()
    lowest = data['low'].min()
    price_range = highest - lowest
    if price_range == 0:
        price_range = 0.01
    
    price_interval = price_range / (num_bins - 1)
    price_levels = [lowest + (i * price_interval) for i in range(num_bins)]
    volumes = [0.0] * num_bins
    
    for idx, row in data.iterrows():
        for i, pl in enumerate(price_levels):
            if row['low'] <= pl <= row['high']:
                volumes[i] += row['volume']
    
    max_idx = volumes.index(max(volumes))
    poc = price_levels[max_idx]
    
    # Value Area (68%)
    total_vol = sum(volumes)
    va_target = total_vol * 0.68
    va_sum = volumes[max_idx]
    va_up, va_dn = max_idx, max_idx
    
    while va_sum < va_target:
        vol_up = volumes[va_up + 1] if va_up < num_bins - 1 else 0
        vol_dn = volumes[va_dn - 1] if va_dn > 0 else 0
        if vol_up == 0 and vol_dn == 0:
            break
        if vol_up >= vol_dn:
            va_sum += vol_up
            va_up += 1
        else:
            va_sum += vol_dn
            va_dn -= 1
    
    return {'poc': poc, 'vah': price_levels[va_up], 'val': price_levels[va_dn]}


# --------------------------------------------------------------------------- #
# Backtest-Funktion für Fibonacci Bollinger Bands + Volume Profile
# --------------------------------------------------------------------------- #
def fib_vp_backtest(df, bands, start_capital=1000, risk_pct=0.01):
    """
    Backtest für Fibonacci Bollinger Bands + Volume Profile Strategie.
    
    Entry:
    - Long: Preis <= lower_6 UND nahe VAL/PoC
    - Short: Preis >= upper_6 UND nahe VAH/PoC
    
    Exit:
    - SL: lower_1/upper_1
    - TP: PoC oder gegenüberliegendes Band 6
    """
    capital = start_capital
    position = None
    trades = []
    equity_curve = [capital]
    
    for i in range(200, len(df) - 1):
        current = df.iloc[i]
        band = bands.iloc[i]
        
        # Volume Profile
        vp = calculate_volume_profile_simple(df.iloc[:i+1], lookback=200)
        poc, vah, val = vp['poc'], vp['vah'], vp['val']
        
        current_close = current['close']
        current_low = current['low']
        current_high = current['high']
        
        upper_6 = band['upper_6']
        lower_6 = band['lower_6']
        upper_1 = band['upper_1']
        lower_1 = band['lower_1']
        
        # Position-Management
        if position:
            # Check SL/TP
            if position['side'] == 'long':
                # SL bei lower_1
                if current_low <= position['sl']:
                    pnl = (position['sl'] - position['entry']) / position['entry']
                    capital *= (1 + pnl * position['leverage'])
                    trades.append({'side': 'long', 'entry': position['entry'], 'exit': position['sl'], 
                                   'pnl_pct': pnl * 100, 'result': 'SL'})
                    position = None
                # TP bei PoC oder upper_6
                elif current_high >= position['tp']:
                    pnl = (position['tp'] - position['entry']) / position['entry']
                    capital *= (1 + pnl * position['leverage'])
                    trades.append({'side': 'long', 'entry': position['entry'], 'exit': position['tp'], 
                                   'pnl_pct': pnl * 100, 'result': 'TP'})
                    position = None
            else:  # short
                # SL bei upper_1
                if current_high >= position['sl']:
                    pnl = (position['entry'] - position['sl']) / position['entry']
                    capital *= (1 + pnl * position['leverage'])
                    trades.append({'side': 'short', 'entry': position['entry'], 'exit': position['sl'], 
                                   'pnl_pct': pnl * 100, 'result': 'SL'})
                    position = None
                # TP bei PoC oder lower_6
                elif current_low <= position['tp']:
                    pnl = (position['entry'] - position['tp']) / position['entry']
                    capital *= (1 + pnl * position['leverage'])
                    trades.append({'side': 'short', 'entry': position['entry'], 'exit': position['tp'], 
                                   'pnl_pct': pnl * 100, 'result': 'TP'})
                    position = None
        
        else:
            # Entry-Logik
            tolerance = 0.005  # 0.5% Toleranz
            
            # Long: Preis bei lower_6 UND nahe VAL
            if current_low <= lower_6 * (1 + tolerance):
                if abs(current_close - val) <= val * 0.01 or abs(current_close - poc) <= poc * 0.01:
                    position = {
                        'side': 'long',
                        'entry': current_close,
                        'sl': lower_1,
                        'tp': poc if poc > current_close else upper_6,
                        'leverage': 5
                    }
            
            # Short: Preis bei upper_6 UND nahe VAH
            elif current_high >= upper_6 * (1 - tolerance):
                if abs(current_close - vah) <= vah * 0.01 or abs(current_close - poc) <= poc * 0.01:
                    position = {
                        'side': 'short',
                        'entry': current_close,
                        'sl': upper_1,
                        'tp': poc if poc < current_close else lower_6,
                        'leverage': 5
                    }
        
        equity_curve.append(capital)
    
    # Berechne Metriken
    total_return = (capital - start_capital) / start_capital * 100
    num_trades = len(trades)
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    win_rate = (wins / num_trades * 100) if num_trades > 0 else 0
    
    # Max Drawdown
    peak = start_capital
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return capital, total_return, num_trades, win_rate, trades, max_dd


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="KBot: Fibonacci Bollinger Bands + Volume Profile Strategy")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol, z.B. ETHUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe, z.B. 6h')
    parser.add_argument('--start_date', type=str, required=False, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=False, help='Enddatum (YYYY-MM-DD)')
    parser.add_argument('--start_capital', type=float, default=1000, help='Startkapital in USD')
    parser.add_argument('--live', action='store_true', help='Live-Modus (kein Backtest)')
    args = parser.parse_args()

    if args.live:
        # ============================================================
        # LIVE MODUS - Fibonacci Bollinger Bands + Volume Profile
        # ============================================================
        import json
        import logging
        from kbot.utils.trade_manager import full_trade_cycle
        from kbot.utils.exchange import Exchange

        print("\n" + "=" * 60)
        print("🤖 KBot Live Mode")
        print("📐 Strategie: Fibonacci Bollinger Bands + Volume Profile")
        print("=" * 60)
        print(f"Symbol:     {args.symbol}")
        print(f"Timeframe:  {args.timeframe}")
        print("")

        PROJECT_ROOT = os.path.abspath(os.path.join(SRC_ROOT, '..'))
        
        def create_safe_filename(symbol, timeframe):
            return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"

        safe_name = create_safe_filename(args.symbol, args.timeframe)
        config_path = os.path.join(PROJECT_ROOT, 'src', 'kbot', 'strategy', 'configs', f'config_{safe_name}.json')

        if not os.path.exists(config_path):
            print(f"Fehler: Strategy-Config nicht gefunden: {config_path}")
            return

        with open(config_path, 'r') as f:
            params = json.load(f)

        # Lade Secrets für Exchange + Telegram
        secret_file = os.path.join(PROJECT_ROOT, 'secret.json')
        try:
            with open(secret_file, 'r') as f:
                secrets = json.load(f)
            account_config = secrets.get('kbot', [])[0]
            telegram_config = secrets.get('telegram', {})
        except Exception as e:
            print(f"Warnung: secret.json konnte nicht geladen werden: {e}")
            account_config = {}
            telegram_config = {}

        # Logger
        logger = logging.getLogger('kbot_live')
        logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

        try:
            exchange = Exchange(account_config)
        except Exception as e:
            print(f"Fehler beim Initialisieren der Exchange: {e}")
            return

        print(f"Starte Live-Zyklus für {args.symbol} ({args.timeframe})")
        try:
            # Führe EINEN Handelszyklus aus
            full_trade_cycle(exchange, params, telegram_config, logger)
            print(f"Live-Zyklus für {args.symbol} abgeschlossen.")
        except Exception as e:
            logger.error(f"Fehler im Handelszyklus: {e}", exc_info=True)
        return

    # ============================================================
    # BACKTEST MODUS
    # ============================================================
    print("\n" + "=" * 60)
    print("📊 KBot Backtest")
    print("📐 Strategie: Fibonacci Bollinger Bands + Volume Profile")
    print("=" * 60)
    print(f"Symbol:       {args.symbol}")
    print(f"Timeframe:    {args.timeframe}")
    print(f"Zeitraum:     {args.start_date} bis {args.end_date}")
    print(f"Startkapital: {args.start_capital:.2f} USD\n")

    try:
        df = load_ohlcv(args.symbol, args.start_date, args.end_date, args.timeframe)
    except Exception as e:
        print(f"Fehler beim Laden der Kursdaten: {e}")
        sys.exit(1)
        
    if df.empty or len(df) < 200:
        print("Nicht genügend Kursdaten für Backtest (min. 200 Kerzen).")
        sys.exit(1)

    bands = fibonacci_bollinger_bands(df, length=200, mult=3.0)
    capital, total_return, num_trades, win_rate, trades, max_dd = fib_vp_backtest(df, bands, start_capital=args.start_capital)

    print("=" * 60)
    print("📈 ERGEBNISSE:")
    print("=" * 60)
    print(f"  Endkapital:    {capital:.2f} USD")
    print(f"  Gesamtrendite: {total_return:+.2f} %")
    print(f"  Trades:        {num_trades}")
    print(f"  Gewinnquote:   {win_rate:.1f} %")
    print(f"  Max. Drawdown: {max_dd:.2f} %")
    print("=" * 60)

    if trades:
        wins = [t for t in trades if t['pnl_pct'] > 0]
        losses = [t for t in trades if t['pnl_pct'] <= 0]
        print(f"\n📊 Trade-Statistik:")
        print(f"   Gewinner: {len(wins)} | Verlierer: {len(losses)}")
        if wins:
            print(f"   Ø Gewinn: +{sum(t['pnl_pct'] for t in wins)/len(wins):.2f}%")
        if losses:
            print(f"   Ø Verlust: {sum(t['pnl_pct'] for t in losses)/len(losses):.2f}%")
    else:
        print("\nKeine Trades im Zeitraum.")


if __name__ == "__main__":
    main()
