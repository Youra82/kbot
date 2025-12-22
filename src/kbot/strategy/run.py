#!/usr/bin/env python3
# src/kbot/strategy/run.py
# KBot: Kanal-Trading-Bot (Basisstruktur)
import sys
import argparse

# --- Argument-Parser für Shell-Aufruf ---
def main():
    parser = argparse.ArgumentParser(description="KBot Backtest (Dummy-Ausgabe)")
    parser.add_argument('--symbol', type=str, required=True, help='Symbol(e), z.B. BTCUSDT')
    parser.add_argument('--timeframe', type=str, required=True, help='Timeframe(s), z.B. 4h')
    parser.add_argument('--start_date', type=str, required=True, help='Startdatum (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, required=True, help='Enddatum (YYYY-MM-DD)')
    args = parser.parse_args()

    print("\nKBot Backtest Dummy-Ausgabe")
    print("---------------------------")
    print(f"Symbol(e):   {args.symbol}")
    print(f"Timeframe(s): {args.timeframe}")
    if __name__ == "__main__":
        main()

