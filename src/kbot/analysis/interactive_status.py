#!/usr/bin/env python3
# =============================================================================
# KBot: Interactive Charts für Volume Channel Flow
# =============================================================================
# Zeigt Candlestick-Chart mit Trade-Signalen (Entry/Exit Long/Short)
# und Volume Channel Flow Visualisierung
# Generiert HTML-Dateien für Telegram-Versand
# =============================================================================

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Tuple

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kbot.analysis.backtester import load_data, run_backtest
from kbot.strategy.volume_channel_engine import VolumeChannelEngine

OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "vcf_plots"


def load_config_strategies(config_dir: Path) -> List[Dict]:
    """Lädt alle Konfigurationsdateien"""
    strategies: List[Dict] = []
    for cfg in sorted(config_dir.glob("config_*.json")):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            market = data.get("market", {})
            symbol = market.get("symbol")
            timeframe = market.get("timeframe")
            if symbol and timeframe:
                strategies.append({
                    "symbol": symbol, 
                    "timeframe": timeframe,
                    "config": data,
                    "filename": cfg.name
                })
        except Exception as e:
            print(f"⚠️  Konnte {cfg.name} nicht laden: {e}")
    return strategies


def sanitize(text: str) -> str:
    """Entferne problematische Zeichen für Dateinamen"""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text)


def select_configs(strategies: List[Dict]) -> List[Dict]:
    """Zeigt durchnummerierte Konfigurationen und lässt User wählen"""
    if not strategies:
        print("❌ Keine Konfigurationsdateien gefunden!")
        print("   Führe zuerst './run_pipeline.sh' aus")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("Verfügbare Konfigurationen:")
    print("="*60)
    for idx, strat in enumerate(strategies, 1):
        print(f"{idx:2d}) {strat['symbol']} ({strat['timeframe']})")
    print("="*60)
    
    print("\nWähle Konfiguration(en) zum Anzeigen:")
    print("  Einzeln: z.B. '1' oder '5'")
    print("  Mehrfach: z.B. '1,3,5' oder '1 3 5'")
    print("  Alle: 'alle' oder 'all'")
    
    selection = input("\nAuswahl: ").strip()
    
    if selection.lower() in ['alle', 'all']:
        return strategies
    
    selected = []
    for part in selection.replace(',', ' ').split():
        try:
            idx = int(part)
            if 1 <= idx <= len(strategies):
                selected.append(strategies[idx - 1])
            else:
                print(f"⚠️ Index {idx} außerhalb des Bereichs")
        except ValueError:
            print(f"⚠️ Ungültige Eingabe: {part}")
    
    if not selected:
        print("❌ Keine gültigen Konfigurationen gewählt!")
        sys.exit(1)
    
    return selected


def make_plot(symbol: str, timeframe: str, config: dict, 
              start: str, end: str, start_capital: float) -> Tuple[Path, dict]:
    """Erstellt interaktiven Chart mit Candlesticks, Channel und Equity Curve"""
    
    print(f"   📊 Lade Daten für {symbol} ({timeframe})...")
    data = load_data(symbol, timeframe, start, end)
    
    if data.empty or len(data) < 50:
        raise RuntimeError(f"Zu wenige Daten für {symbol} ({timeframe}).")
    
    # Berechne Volume Channel Flow
    print(f"   🔄 Berechne Volume Channel Flow...")
    engine = VolumeChannelEngine(settings=config.get('strategy', {}))
    df = engine.process_dataframe(data.copy())
    
    # Führe Backtest durch
    print(f"   🔄 Führe Backtest durch...")
    result, equity_snapshots = run_backtest(df, config, start_capital=start_capital, verbose=False, return_equity=True)
    
    trades_list = result.get('trades', [])
    
    # === Erstelle Chart mit secondary_y für Equity ===
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # === Candlesticks ===
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='OHLC',
            increasing_line_color="#16a34a",
            decreasing_line_color="#dc2626"
        ),
        secondary_y=False
    )
    
    # === Channel Lines ===
    if 'channel_top' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_top'],
                name='Channel Top',
                line=dict(color='#f59e0b', width=1.5, dash='dash')
            ),
            secondary_y=False
        )
    
    if 'channel_bot' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_bot'],
                name='Channel Bot',
                line=dict(color='#ef4444', width=1.5, dash='dash')
            ),
            secondary_y=False
        )
    
    if 'channel_avg' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_avg'],
                name='Channel Mid',
                line=dict(color='#6366f1', width=1)
            ),
            secondary_y=False
        )
    
    # === Trade Markers ===
    entry_long_x, entry_long_y = [], []
    exit_long_x, exit_long_y = [], []
    entry_short_x, entry_short_y = [], []
    exit_short_x, exit_short_y = [], []
    
    for trade in trades_list:
        if 'entry_long' in trade:
            t = trade['entry_long']
            if t.get('time') and t.get('price'):
                entry_long_x.append(pd.to_datetime(t['time']))
                entry_long_y.append(t['price'])
        if 'exit_long' in trade:
            t = trade['exit_long']
            if t.get('time') and t.get('price'):
                exit_long_x.append(pd.to_datetime(t['time']))
                exit_long_y.append(t['price'])
        if 'entry_short' in trade:
            t = trade['entry_short']
            if t.get('time') and t.get('price'):
                entry_short_x.append(pd.to_datetime(t['time']))
                entry_short_y.append(t['price'])
        if 'exit_short' in trade:
            t = trade['exit_short']
            if t.get('time') and t.get('price'):
                exit_short_x.append(pd.to_datetime(t['time']))
                exit_short_y.append(t['price'])
    
    # Entry Long
    if entry_long_x:
        fig.add_trace(go.Scatter(
            x=entry_long_x, y=entry_long_y, mode="markers",
            marker=dict(color="#16a34a", symbol="triangle-up", size=14, line=dict(width=1.2, color="#0f5132")),
            name="Entry Long"
        ), secondary_y=False)
    
    # Exit Long
    if exit_long_x:
        fig.add_trace(go.Scatter(
            x=exit_long_x, y=exit_long_y, mode="markers",
            marker=dict(color="#22d3ee", symbol="circle", size=12, line=dict(width=1.1, color="#0e7490")),
            name="Exit Long"
        ), secondary_y=False)
    
    # Entry Short
    if entry_short_x:
        fig.add_trace(go.Scatter(
            x=entry_short_x, y=entry_short_y, mode="markers",
            marker=dict(color="#f59e0b", symbol="triangle-down", size=14, line=dict(width=1.2, color="#92400e")),
            name="Entry Short"
        ), secondary_y=False)
    
    # Exit Short
    if exit_short_x:
        fig.add_trace(go.Scatter(
            x=exit_short_x, y=exit_short_y, mode="markers",
            marker=dict(color="#ef4444", symbol="diamond", size=12, line=dict(width=1.1, color="#7f1d1d")),
            name="Exit Short"
        ), secondary_y=False)
    
    # === Equity Curve auf zweiter Y-Achse ===
    if equity_snapshots:
        equity_times = [pd.to_datetime(e['timestamp']) for e in equity_snapshots]
        equity_values = [e['equity'] for e in equity_snapshots]
        fig.add_trace(
            go.Scatter(
                x=equity_times,
                y=equity_values,
                name='Kontostand',
                line=dict(color='#2563eb', width=2),
                opacity=0.8
            ),
            secondary_y=True
        )
    
    # === Layout ===
    total_return = result['total_pnl_pct']
    max_dd = result['max_drawdown_pct']
    end_capital = result['end_capital']
    trades_count = result['trades_count']
    win_rate = result['win_rate']
    
    pnl_sign = '+' if total_return >= 0 else ''
    
    title_text = (
        f"{symbol} {timeframe} - KBot | "
        f"Start Capital: ${start_capital:.2f} | "
        f"End Capital: ${end_capital:.2f} | "
        f"PnL: {pnl_sign}{total_return:.2f}% | "
        f"Max DD: {max_dd:.2f}% | "
        f"Trades: {trades_count} | "
        f"Win Rate: {win_rate:.1f}%"
    )
    
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=12), x=0.5, xanchor='center'),
        xaxis=dict(rangeslider=dict(visible=True)),
        height=700,
        template="plotly_white",
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    fig.update_yaxes(title_text="Preis (USDT)", secondary_y=False)
    fig.update_yaxes(title_text="Kontostand (USDT)", secondary_y=True)
    
    # Speichere HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"vcf_{sanitize(symbol)}_{sanitize(timeframe)}.html"
    out_path = OUTPUT_DIR / fname
    fig.write_html(out_path, include_plotlyjs="cdn")
    
    print(f"   ✅ Chart gespeichert: {out_path}")
    
    stats = {
        'total_pnl_pct': total_return,
        'max_drawdown_pct': max_dd,
        'end_capital': end_capital,
        'trades_count': trades_count,
        'win_rate': win_rate
    }
    
    return out_path, stats


def main():
    """Hauptfunktion"""
    print("\n" + "="*60)
    print("   KBot Interactive Charts - Volume Channel Flow")
    print("="*60)
    
    # Lade Strategien
    config_dir = PROJECT_ROOT / "src" / "kbot" / "strategy" / "configs"
    strategies = load_config_strategies(config_dir)
    
    # Wähle Konfigurationen
    selected = select_configs(strategies)
    
    # Frage Zeitraum ab
    print("\n--- Chart-Parameter ---")
    start_date = input("Startdatum (YYYY-MM-DD) [Standard: 2025-01-01]: ").strip() or "2025-01-01"
    end_date = input("Enddatum (YYYY-MM-DD) [Standard: Heute]: ").strip() or datetime.now().strftime('%Y-%m-%d')
    
    try:
        start_capital = float(input("Startkapital (USDT) [Standard: 1000]: ").strip() or "1000")
    except ValueError:
        start_capital = 1000
    
    # Telegram-Option
    send_telegram = input("Telegram versenden? (j/n) [Standard: n]: ").strip().lower() in ['j', 'y', 'yes']
    
    # Lade Telegram-Konfiguration
    telegram_config = {}
    if send_telegram:
        try:
            with open(PROJECT_ROOT / "secret.json", "r", encoding="utf-8") as f:
                secrets = json.load(f)
            telegram_config = secrets.get('telegram', {})
            if not telegram_config.get('bot_token') or not telegram_config.get('chat_id'):
                print("⚠️  Telegram bot_token oder chat_id fehlt in secret.json")
                send_telegram = False
        except Exception as e:
            print(f"⚠️  Konnte secret.json nicht lesen: {e}")
            send_telegram = False
    
    # Erstelle Charts
    print(f"\n📊 Erstelle {len(selected)} Chart(s)...\n")
    
    outputs = []
    for strat in selected:
        symbol = strat['symbol']
        timeframe = strat['timeframe']
        config = strat['config']
        
        print(f"{'─'*60}")
        print(f"🔍 Erstelle Chart für {symbol} ({timeframe})")
        
        try:
            out_path, stats = make_plot(symbol, timeframe, config, start_date, end_date, start_capital)
            outputs.append((out_path, symbol, timeframe, stats))
        except Exception as e:
            print(f"   ❌ Fehler: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Zusammenfassung
    if outputs:
        print(f"\n{'='*60}")
        print("✅ Alle Charts wurden erstellt!")
        print(f"{'='*60}")
        print("\nGespeicherte Charts:")
        for p, sym, tf, stats in outputs:
            print(f"  📊 {p}")
        
        # Telegram versenden (HTML-Dokument)
        if send_telegram and telegram_config:
            print("\n📤 Sende Charts via Telegram...")
            try:
                from kbot.utils.telegram import send_document
                bot_token = telegram_config.get('bot_token')
                chat_id = telegram_config.get('chat_id')
                
                for p, sym, tf, stats in outputs:
                    try:
                        pnl = stats['total_pnl_pct']
                        pnl_sign = '+' if pnl >= 0 else ''
                        caption = (f"📊 KBot: {sym} ({tf})\n"
                                   f"PnL: {pnl_sign}{pnl:.2f}% | "
                                   f"Trades: {stats['trades_count']} | "
                                   f"Win Rate: {stats['win_rate']:.1f}%")
                        
                        send_document(bot_token, chat_id, str(p), caption=caption)
                        print(f"   ✅ Gesendet: {sym} ({tf})")
                    except Exception as e:
                        print(f"   ❌ Fehler beim Senden von {sym}: {e}")
            except Exception as e:
                print(f"❌ Telegram-Modul nicht verfügbar: {e}")
        
        print("\n💡 HTML im Browser öffnen für interaktive Zoom/Pan-Funktionen")
    else:
        print("\n❌ Keine Charts erzeugt.")


if __name__ == "__main__":
    main()
