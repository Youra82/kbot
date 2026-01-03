#!/usr/bin/env python3
"""
plot_channels.py

Erzeugt ein Chart mit Kursverlauf, erkannter Kanalober-/unterkante sowie Entry-/Exit-Marker
für eine einzelne Backtest-Ausführung der Kanalstrategie.

Beispiel:
  python plot_channels.py --symbol ETHUSDT --timeframe 6h --start 2025-01-01 --end 2026-01-03 --start-capital 50

Ausgabe:
  artifacts/channel_plots/<symbol>_<tf>_<start>_<end>.png
"""
import argparse
import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.kbot.strategy.run import load_ohlcv, detect_channels, channel_backtest


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(text: str) -> str:
    return ''.join(c for c in text if c.isalnum() or c in ('-', '_')).strip('_')


def plot_channels(symbol: str, timeframe: str, start: str, end: str, start_capital: float, window: int = 50):
    df = load_ohlcv(symbol, start, end, timeframe)
    if df.empty or len(df) < window + 5:
        raise RuntimeError("Nicht genügend Kursdaten für Plot.")

    channels = detect_channels(df, window=window)
    final_capital, total_return, _, _, trades, max_dd = channel_backtest(
        df, channels, start_capital=start_capital
    )

    # Auf die Zeitpunkte der Kanäle beschränken, damit Längen passen
    plot_df = df.loc[channels.index].copy()
    plot_df['channel_high'] = channels['high'].values
    plot_df['channel_low'] = channels['low'].values
    plot_df['channel_type'] = channels['type'].values

    # Prepare figure
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='white')
    ax.plot(plot_df.index, plot_df['close'], label='Close', color='#1f77b4', linewidth=1.3)

    # Kanalbänder je nach Typ einfärben
    type_colors = {
        'parallel': '#2ca02c',
        'wedge': '#ff7f0e',
        'triangle': '#9467bd',
        'none': '#7f7f7f'
    }
    for ctype, color in type_colors.items():
        mask = plot_df['channel_type'] == ctype
        if mask.any():
            ax.plot(plot_df.index[mask], plot_df.loc[mask, 'channel_high'], color=color, alpha=0.8, linewidth=1.1, label=f'Kanal High ({ctype})')
            ax.plot(plot_df.index[mask], plot_df.loc[mask, 'channel_low'], color=color, alpha=0.8, linewidth=1.1, linestyle='--', label=f'Kanal Low ({ctype})')

    # Trades markieren
    entry_y = []
    entry_x = []
    exit_y = []
    exit_x = []
    for t in trades:
        t_type = t.get('type', '')
        date = pd.to_datetime(t['date'])
        price = t.get('price')
        if price is None:
            continue
        if t_type.startswith('BUY'):
            entry_x.append(date)
            entry_y.append(price)
        elif t_type.startswith('SELL'):
            exit_x.append(date)
            exit_y.append(price)

    if entry_x:
        ax.scatter(entry_x, entry_y, marker='^', color='#16a34a', s=45, label='Entry')
    if exit_x:
        ax.scatter(exit_x, exit_y, marker='v', color='#dc2626', s=45, label='Exit')

    ax.set_title(
        f"Kanal-Backtest: {symbol} {timeframe}\nReturn: {total_return:.2f}% | Max DD: {max_dd:.2f}% | Endkapital: {final_capital:.2f}"
    )
    ax.set_xlabel('Zeit')
    ax.set_ylabel('Preis')
    ax.grid(True, linestyle='--', alpha=0.4)

    # Doppelte Labels vermeiden
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    uniq_handles = []
    uniq_labels = []
    for h, l in zip(handles, labels):
        if l not in seen:
            uniq_handles.append(h)
            uniq_labels.append(l)
            seen.add(l)
    ax.legend(uniq_handles, uniq_labels, loc='best')

    plt.tight_layout()

    out_dir = Path('artifacts') / 'channel_plots'
    ensure_dir(out_dir)
    fname = f"{sanitize_filename(symbol)}_{sanitize_filename(timeframe)}_{sanitize_filename(start)}_{sanitize_filename(end)}.png"
    out_path = out_dir / fname
    plt.savefig(out_path)
    plt.close(fig)
    print(f"Plot gespeichert unter: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot der Kanäle und Trades für einen Backtest")
    parser.add_argument('--symbol', required=True, help='z.B. BTCUSDT oder BTC/USDT:USDT')
    parser.add_argument('--timeframe', required=True, help='z.B. 6h')
    parser.add_argument('--start', required=True, help='Startdatum YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='Enddatum YYYY-MM-DD')
    parser.add_argument('--start-capital', type=float, default=1000.0)
    parser.add_argument('--window', type=int, default=50, help='Fenster für detect_channels')
    args = parser.parse_args()

    plot_channels(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=args.start,
        end=args.end,
        start_capital=args.start_capital,
        window=args.window,
    )


if __name__ == '__main__':
    main()
