#!/bin/bash
# show_results.sh: Interaktives Backtest-Tool für KBot (Kanalstrategie)

# Farben für Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Virtual Environment Pfad
VENV_PATH=".venv/bin/activate"

# Python-Script Pfad
RESULTS_SCRIPT="src/kbot/analysis/show_results.py"

# Aktiviere venv
if [ ! -f "$VENV_PATH" ]; then
	echo -e "${RED}❌ Virtual Environment nicht gefunden unter: $VENV_PATH${NC}"
	echo "Bitte zuerst 'python3 -m venv .venv' ausführen."
	exit 1
fi

source "$VENV_PATH"

# Starte das interaktive Backtest-Tool
echo -e "\n${YELLOW}KBot Backtest-Tool (Kanalstrategie)${NC}"
echo -e "${YELLOW}=====================================${NC}\n"

python3 "$RESULTS_SCRIPT"

echo -e "\n${GREEN}✓ Backtest abgeschlossen.${NC}"


