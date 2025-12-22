#!/bin/bash
# show_results.sh: Backtest- und Ergebnis-Tool für KBot (ohne ML)

echo "KBot Backtest-Tool (ohne Machine Learning)"
echo "-----------------------------------------"
read -p "Symbol (z.B. BTCUSDT): " symbol
read -p "Timeframe (z.B. 4h): " timeframe
read -p "Startdatum (YYYY-MM-DD): " start_date

read -p "Enddatum (YYYY-MM-DD, Enter = heute): " end_date
if [ -z "$end_date" ]; then
	end_date=$(date +%F)
fi

read -p "Startkapital (USD, z.B. 1000): " start_capital

echo "(Backtest-Logik bitte in Python implementieren, z.B. src/kbot/strategy/backtest_channels.py)"
echo "Starte Backtest..."
# Hier wird das KBot-Backtest-Script aufgerufen (Dummy-Ausgabe, Implementierung folgt)
python3 src/kbot/strategy/run.py --symbol "$symbol" --timeframe "$timeframe" --start_date "$start_date" --end_date "$end_date" --start_capital "$start_capital"


