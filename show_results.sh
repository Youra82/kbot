#!/usr/bin/env bash
# show_results.sh: Interaktives Backtest-Tool für KBot (Fib BB + Volume Profile)

# Farben für Output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Virtual Environment Pfad (Linux/Mac) mit Windows-Fallback
VENV_PATH=".venv/bin/activate"
[ -f "$VENV_PATH" ] || VENV_PATH=".venv/Scripts/activate"

# Python-Script Pfad
RESULTS_SCRIPT="src/kbot/analysis/show_results.py"

# Aktiviere venv
if [ ! -f "$VENV_PATH" ]; then
	echo -e "${RED}❌ Virtual Environment nicht gefunden unter: $VENV_PATH${NC}"
	echo "Bitte zuerst 'python3 -m venv .venv' ausführen."
	exit 1
fi

source "$VENV_PATH"

# Python-Binary finden
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
	PYTHON_BIN="python"
fi

# --- MODUS-MENÜ (Fib BB + Volume Profile) ---
echo -e "\n${BLUE}=======================================================${NC}"
echo -e "${BLUE}     KBot Backtest-Tool (Fib BB + Volume Profile)${NC}"
echo -e "${BLUE}=======================================================${NC}\n"

echo -e "${YELLOW}Wähle einen Analyse-Modus:${NC}"
echo -e "  ${CYAN}1)${NC} Einzel-Analyse (jede Strategie wird isoliert getestet)"
echo -e "  ${CYAN}2)${NC} Portfolio-Simulation (alle Strategien zusammen)"
echo -e "  ${CYAN}3)${NC} Portfolio-Optimierung (beste Kombination finden)"
echo -e "  ${CYAN}4)${NC} Interaktive Charts"
read -p "Auswahl (1-4) [Standard: 1]: " MODE
MODE=${MODE:-1}

# --- Datum und Kapital abfragen ---
echo ""
read -p "Startdatum (JJJJ-MM-TT) [Standard: 2024-01-01]: " START_DATE
START_DATE=${START_DATE:-2024-01-01}

read -p "Enddatum (JJJJ-MM-TT) [Standard: heute]: " END_DATE
END_DATE=${END_DATE:-$(date +%F)}

read -p "Startkapital (USDT) [Standard: 1000]: " CAPITAL
CAPITAL=${CAPITAL:-1000}

echo -e "\n${BLUE}Starte Analyse...${NC}\n"

# --- Führe Python-Script aus ---
"$PYTHON_BIN" "$RESULTS_SCRIPT" --mode "$MODE" --start "$START_DATE" --end "$END_DATE" --capital "$CAPITAL"

# --- MODUS 4: Interaktive Charts ---
if [ "$MODE" = "4" ]; then
	if [ -f "src/kbot/analysis/interactive_status.py" ]; then
		echo -e "\n${YELLOW}Generiere interaktive Charts...${NC}"
		"$PYTHON_BIN" src/kbot/analysis/interactive_status.py
		
		if [ $? -eq 0 ]; then
			echo -e "${GREEN}✅ Charts wurden generiert!${NC}"
		else
			echo -e "${RED}❌ Fehler beim Generieren der Charts.${NC}"
		fi
	else
		echo -e "${YELLOW}ℹ  Interaktive Charts nicht verfügbar.${NC}"
	fi
fi

echo -e "\n${GREEN}✓ Analyse abgeschlossen.${NC}"

deactivate
