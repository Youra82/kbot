#!/usr/bin/env python3
# =============================================================================
# KBot: Interactive Charts für Volume Channel Flow
# =============================================================================
# Zeigt Candlestick-Chart mit Trade-Signalen (Entry/Exit Long/Short)
# und Volume Channel Flow Visualisierung
# =============================================================================

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict

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
              start: str, end: str, start_capital: float) -> Path:
    """Erstellt interaktiven Chart mit Candlesticks und Volume Channel"""
    
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
    result = run_backtest(df, config, start_capital=start_capital, verbose=False)
    
    # === Erstelle Chart ===
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.75, 0.25],
        subplot_titles=[f'{symbol} ({timeframe}) - Volume Channel Flow', 'Volume']
    )
    
    # === Row 1: Candlesticks + Channel ===
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
        row=1, col=1
    )
    
    # Channel Top
    if 'channel_top' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_top'],
                name='Channel Top',
                line=dict(color='#f59e0b', width=1.5, dash='dash'),
                hovertemplate='<b>Channel Top</b><br>%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # Channel Bottom
    if 'channel_bot' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_bot'],
                name='Channel Bottom',
                line=dict(color='#ef4444', width=1.5, dash='dash'),
                hovertemplate='<b>Channel Bottom</b><br>%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # Channel Mid
    if 'channel_avg' in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['channel_avg'],
                name='Channel Mid',
                line=dict(color='#6366f1', width=1),
                hovertemplate='<b>Channel Mid</b><br>%{y:.2f}<extra></extra>'
            ),
            row=1, col=1
        )
    
    # === Row 2: Volume ===
    colors = ['#16a34a' if df['close'].iloc[i] >= df['open'].iloc[i] 
              else '#dc2626' for i in range(len(df))]
    
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df['volume'],
            name='Volume',
            marker_color=colors,
            showlegend=False,
            hovertemplate='<b>Volume</b><br>%{y:.0f}<extra></extra>'
        ),
        row=2, col=1
    )
    
    # === Layout ===
    total_return = result['total_pnl_pct']
    max_dd = result['max_drawdown_pct']
    end_capital = result['end_capital']
    trades = result['trades_count']
    win_rate = result['win_rate']
    
    fig.update_layout(
        title=dict(
            text=f"<b>{symbol} ({timeframe})</b> | Return: {total_return:.2f}% | "
                 f"Win-Rate: {win_rate:.1f}% | Max DD: {max_dd:.2f}% | "
                 f"Trades: {trades} | Endkapital: ${end_capital:.2f}",
            font=dict(size=14)
        ),
        xaxis=dict(rangeslider=dict(visible=False)),
        xaxis2=dict(title="Datum/Zeit"),
        yaxis=dict(title="Preis (USDT)"),
        yaxis2=dict(title="Volume"),
        template="plotly_dark",
        height=800,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='x unified'
    )
    
    # Speichere HTML
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"vcf_{sanitize(symbol)}_{sanitize(timeframe)}_{sanitize(start)}_{sanitize(end)}.html"
    out_path = OUTPUT_DIR / fname
    fig.write_html(out_path, include_plotlyjs="cdn")
    
    print(f"   ✅ Chart gespeichert: {out_path}")
    return out_path


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
            out = make_plot(symbol, timeframe, config, start_date, end_date, start_capital)
            outputs.append((out, symbol, timeframe))
        except Exception as e:
            print(f"   ❌ Fehler: {e}")
            continue
    
    # Zusammenfassung
    if outputs:
        print(f"\n{'='*60}")
        print("✅ Alle Charts wurden erstellt!")
        print(f"{'='*60}")
        print("\nGespeicherte Charts:")
        for p, sym, tf in outputs:
            print(f"  📊 {p}")
        
        # Telegram versenden
        if send_telegram and telegram_config:
            print("\n📤 Sende Charts via Telegram...")
            try:
                from kbot.utils.telegram import send_document
                bot_token = telegram_config.get('bot_token')
                chat_id = telegram_config.get('chat_id')
                
                for p, sym, tf in outputs:
                    try:
                        send_document(bot_token, chat_id, str(p), caption=f"📊 KBot Chart: {sym} ({tf})")
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
