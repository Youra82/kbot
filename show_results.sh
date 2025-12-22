#!/bin/bash
# show_results.sh: Backtest- und Ergebnis-Tool für KBot (ohne ML)

echo "KBot Backtest-Tool (ohne Machine Learning)"
echo "-----------------------------------------"
read -p "Symbol(e) (z.B. BTCUSDT ETHUSDT): " symbols
read -p "Timeframe(s) (z.B. 4h 1d): " timeframes
read -p "Startdatum (YYYY-MM-DD): " start_date

read -p "Enddatum (YYYY-MM-DD, Enter = heute): " end_date
if [ -z "$end_date" ]; then
	end_date=$(date +%F)
fi

read -p "Startkapital (USD, z.B. 1000): " start_capital


for symbol in $symbols; do
	for timeframe in $timeframes; do
		echo "\n-----------------------------------------"
		echo "Starte Backtest für $symbol ($timeframe) ..."
		python3 src/kbot/strategy/run.py --symbol "$symbol" --timeframe "$timeframe" --start_date "$start_date" --end_date "$end_date" --start_capital "$start_capital"
	done
done


