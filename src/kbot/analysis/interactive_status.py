#!/usr/bin/env python3
"""
Erzeugt interaktive (Plotly) Charts für alle aktiven Strategien aus settings.json.
- Liest active_strategies aus settings.json
- Lädt OHLCV, erkennt Kanäle, führt Backtest aus (channel_backtest)
- Plottet Candles + Kanalbänder + Entry/Exit-Marker mit Zoom/Pan
- Speichert pro Strategie ein HTML unter artifacts/channel_plots/interactive_<symbol>_<tf>_<start>_<end>.html
"""
import argparse
import json
import os
from pathlib import Path
from typing import List, Dict

import pandas as pd
import plotly.graph_objects as go

from kbot.strategy.run import load_ohlcv, detect_channels, channel_backtest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "channel_plots"


def load_active_strategies(settings_path: Path) -> List[Dict]:
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
    live = settings.get("live_trading_settings", {})
    return live.get("active_strategies", [])


def sanitize(text: str) -> str:
    return "".join(c for c in text if c.isalnum() or c in ("-", "_", ":", "/"))


def make_plot(symbol: str, timeframe: str, start: str, end: str, start_capital: float, window: int) -> Path:
    df = load_ohlcv(symbol, start, end, timeframe)
    if df.empty or len(df) < window + 5:
        raise RuntimeError(f"Zu wenige Daten für {symbol} {timeframe}.")

    channels = detect_channels(df, window=window)
    final_capital, total_return, _, _, trades, max_dd = channel_backtest(
        df, channels, start_capital=start_capital
    )

    # Slice df auf Kanalindex, damit Längen übereinstimmen
    plot_df = df.loc[channels.index].copy()
    plot_df["channel_high"] = channels["high"].values
    plot_df["channel_low"] = channels["low"].values
    plot_df["channel_type"] = channels["type"].values

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df["open"], high=plot_df["high"], low=plot_df["low"], close=plot_df["close"],
        name="Candles",
        increasing_line_color="#16a34a",
        decreasing_line_color="#dc2626",
        showlegend=True
    ))

    type_colors = {
        "parallel": "#22c55e",
        "wedge": "#f97316",
        "triangle": "#8b5cf6",
        "none": "#6b7280"
    }
    for ctype, color in type_colors.items():
        mask = plot_df["channel_type"] == ctype
        if mask.any():
            fig.add_trace(go.Scatter(
                x=plot_df.index[mask], y=plot_df.loc[mask, "channel_high"],
                mode="lines", line=dict(color=color, width=1.2),
                name=f"High {ctype}", showlegend=True
            ))
            fig.add_trace(go.Scatter(
                x=plot_df.index[mask], y=plot_df.loc[mask, "channel_low"],
                mode="lines", line=dict(color=color, width=1.2, dash="dash"),
                name=f"Low {ctype}", showlegend=True
            ))

    # Trades
    entry_x, entry_y, exit_x, exit_y = [], [], [], []
    for t in trades:
        t_type = t.get("type", "")
        date = pd.to_datetime(t.get("date")) if t.get("date") is not None else None
        price = t.get("price")
        if date is None or price is None:
            continue
        if t_type.startswith("BUY"):
            entry_x.append(date)
            entry_y.append(price)
        elif t_type.startswith("SELL"):
            exit_x.append(date)
            exit_y.append(price)

    if entry_x:
        fig.add_trace(go.Scatter(
            x=entry_x, y=entry_y, mode="markers",
            marker=dict(color="#16a34a", symbol="triangle-up", size=9),
            name="Entry"
        ))
    if exit_x:
        fig.add_trace(go.Scatter(
            x=exit_x, y=exit_y, mode="markers",
            marker=dict(color="#dc2626", symbol="triangle-down", size=9),
            name="Exit"
        ))

    fig.update_layout(
        title=f"{symbol} {timeframe} | Return {total_return:.2f}% | Max DD {max_dd:.2f}% | Endkapital {final_capital:.2f}",
        xaxis_title="Zeit",
        yaxis_title="Preis",
        template="plotly_white",
        xaxis=dict(rangeslider=dict(visible=True)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"interactive_{sanitize(symbol)}_{sanitize(timeframe)}_{sanitize(start)}_{sanitize(end)}.html"
    out_path = OUTPUT_DIR / fname
    fig.write_html(out_path, include_plotlyjs="cdn")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Interaktive Kanal-Charts aus settings.json erzeugen")
    parser.add_argument("--start", required=True, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Enddatum YYYY-MM-DD")
    parser.add_argument("--start-capital", type=float, default=1000.0)
    parser.add_argument("--window", type=int, default=50)
    args = parser.parse_args()

    settings_path = PROJECT_ROOT / "settings.json"
    strategies = load_active_strategies(settings_path)
    if not strategies:
        print("Keine aktiven Strategien in settings.json gefunden.")
        return

    print(f"Gefundene Strategien: {len(strategies)} (aus settings.json)")
    outputs = []
    for strat in strategies:
        symbol = strat.get("symbol")
        timeframe = strat.get("timeframe")
        if not symbol or not timeframe:
            continue
        print(f"→ Rendere {symbol} {timeframe} ...")
        try:
            out = make_plot(symbol, timeframe, args.start, args.end, args.start_capital, args.window)
            outputs.append(out)
        except Exception as e:
            print(f"⚠️  Fehler bei {symbol} {timeframe}: {e}")

    if outputs:
        print("\nFertig. Interaktive Charts:")
        for p in outputs:
            print(f"  {p}")
        print("(HTML im Browser öffnen für Zoom/Pan)")
    else:
        print("Keine Charts erzeugt.")


if __name__ == "__main__":
    main()
