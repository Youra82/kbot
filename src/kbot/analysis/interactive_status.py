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
import sys
from pathlib import Path
from typing import List, Dict

import pandas as pd
import plotly.graph_objects as go
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kbot.strategy.run import load_ohlcv, fibonacci_bollinger_bands, fib_backtest
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "fib_plots"


def load_config_strategies(config_dir: Path) -> List[Dict]:
    strategies: List[Dict] = []
    for cfg in sorted(config_dir.glob("config_*.json")):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            market = data.get("market", {})
            symbol = market.get("symbol")
            timeframe = market.get("timeframe")
            if symbol and timeframe:
                strategies.append({"symbol": symbol, "timeframe": timeframe})
        except Exception as e:
            print(f"⚠️  Konnte {cfg.name} nicht laden: {e}")
    return strategies


def sanitize(text: str) -> str:
    # Entferne/ersetze problematische Pfadzeichen, damit Dateinamen flach bleiben
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text)


def make_plot(symbol: str, timeframe: str, start: str, end: str, start_capital: float, window: int) -> Path:
    df = load_ohlcv(symbol, start, end, timeframe)
    if df.empty or len(df) < window + 5:
        raise RuntimeError(f"Zu wenige Daten für {symbol} {timeframe}.")

    bands = fibonacci_bollinger_bands(df, length=window, mult=3.0)
    final_capital, total_return, _, _, trades, max_dd = fib_backtest(
        df, bands, start_capital=start_capital
    )

    # Slice df auf Bands-Index, damit Längen übereinstimmen
    plot_df = df.loc[bands.index].copy()
    plot_df["upper_6"] = bands["upper_6"].values
    plot_df["upper_1"] = bands["upper_1"].values
    plot_df["lower_6"] = bands["lower_6"].values
    plot_df["lower_1"] = bands["lower_1"].values
    plot_df["basis"] = bands["basis"].values

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df["open"], high=plot_df["high"], low=plot_df["low"], close=plot_df["close"],
        name="Candles",
        increasing_line_color="#16a34a",
        decreasing_line_color="#dc2626",
        showlegend=True
    ))

    # Fibonacci Bollinger Bands Plotting
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df["basis"],
        mode="lines", line=dict(color="#0ea5e9", width=1.2),
        name="VWMA Basis", showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df["upper_1"],
        mode="lines", line=dict(color="#facc15", width=1.0, dash="dash"),
        name="Upper Fib 1", showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df["lower_1"],
        mode="lines", line=dict(color="#facc15", width=1.0, dash="dash"),
        name="Lower Fib 1", showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df["upper_6"],
        mode="lines", line=dict(color="#ef4444", width=1.2),
        name="Upper Fib 6", showlegend=True
    ))
    fig.add_trace(go.Scatter(
        x=plot_df.index, y=plot_df["lower_6"],
        mode="lines", line=dict(color="#22c55e", width=1.2),
        name="Lower Fib 6", showlegend=True
    ))

    # Trades
    entry_long_x, entry_long_y, entry_short_x, entry_short_y = [], [], [], []
    exit_long_x, exit_long_y, exit_short_x, exit_short_y = [], [], [], []
    for t in trades:
        t_type = t.get("type", "")
        date = pd.to_datetime(t.get("date")) if t.get("date") is not None else None
        price = t.get("price")
        if date is None or price is None:
            continue
        side = t.get("side", "").lower()
        # Fallback: ableiten aus type falls side fehlt
        if not side:
            if "long" in t_type.lower():
                side = "long"
            elif "short" in t_type.lower():
                side = "short"
        if t_type.startswith("BUY"):
            if side == "short":
                entry_short_x.append(date); entry_short_y.append(price)
            else:
                entry_long_x.append(date); entry_long_y.append(price)
        elif t_type.startswith("SELL"):
            if side == "short":
                exit_short_x.append(date); exit_short_y.append(price)
            else:
                exit_long_x.append(date); exit_long_y.append(price)

    # Entry Long
    if entry_long_x:
        fig.add_trace(go.Scatter(
            x=entry_long_x, y=entry_long_y, mode="markers",
            marker=dict(color="#16a34a", symbol="triangle-up", size=14, line=dict(width=1.2, color="#0f5132")),
            name="Entry Long"
        ))
    # Entry Short
    if entry_short_x:
        fig.add_trace(go.Scatter(
            x=entry_short_x, y=entry_short_y, mode="markers",
            marker=dict(color="#f59e0b", symbol="triangle-down", size=14, line=dict(width=1.2, color="#92400e")),
            name="Entry Short"
        ))
    # Exit Long
    if exit_long_x:
        fig.add_trace(go.Scatter(
            x=exit_long_x, y=exit_long_y, mode="markers",
            marker=dict(color="#22d3ee", symbol="circle", size=12, line=dict(width=1.1, color="#0e7490")),
            name="Exit Long"
        ))
    # Exit Short
    if exit_short_x:
        fig.add_trace(go.Scatter(
            x=exit_short_x, y=exit_short_y, mode="markers",
            marker=dict(color="#ef4444", symbol="diamond", size=12, line=dict(width=1.1, color="#7f1d1d")),
            name="Exit Short"
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


def send_document(bot_token: str, chat_id: str, file_path: Path, caption: str = "") -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": (file_path.name, f)}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, data=data, files=files, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Telegram Upload fehlgeschlagen ({resp.status_code}): {resp.text}")
        return False
    j = resp.json()
    if not j.get("ok"):
        print(f"❌ Telegram API-Fehler: {j}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Interaktive Kanal-Charts aus settings.json erzeugen")
    parser.add_argument("--start", required=True, help="Startdatum YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Enddatum YYYY-MM-DD")
    parser.add_argument("--start-capital", type=float, default=1000.0)
    parser.add_argument("--window", type=int, default=50)
    parser.add_argument("--send-telegram", action="store_true", help="Ergebnis-HTML an Telegram senden (secret.json notwendig)")
    parser.add_argument("--caption-prefix", default="KBot Kanal-Chart", help="Caption-Prefix für Telegram")
    args = parser.parse_args()

    config_dir = PROJECT_ROOT / "src" / "kbot" / "strategy" / "configs"
    strategies = load_config_strategies(config_dir)
    if not strategies:
        print("Keine Strategien gefunden (keine config_*.json im configs-Ordner).")
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

        if args.send_telegram:
            try:
                secrets = json.load(open(PROJECT_ROOT / "secret.json", "r", encoding="utf-8"))
                telegram = secrets.get("telegram", {})
                bot_token = telegram.get("bot_token")
                chat_id = telegram.get("chat_id")
            except Exception as e:
                print(f"❌ Konnte secret.json nicht lesen: {e}")
                return

            if not bot_token or not chat_id:
                print("❌ Telegram bot_token oder chat_id fehlt in secret.json")
                return

            print("\nSende Charts an Telegram...")
            for p in outputs:
                caption = f"{args.caption_prefix}: {p.name}"
                ok = send_document(bot_token, chat_id, p, caption)
                if ok:
                    print(f"✔ Gesendet: {p.name}")
                else:
                    print(f"❌ Fehlgeschlagen: {p.name}")
    else:
        print("Keine Charts erzeugt.")


if __name__ == "__main__":
    main()
