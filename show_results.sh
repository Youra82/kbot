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
UPDATE_SETTINGS_SCRIPT="update_settings_from_optimizer.py"
RUN_SCRIPT="src/kbot/strategy/run.py"

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

# --- ERWEITERTES MODUS-MENÜ (Fib BB + Volume Profile) ---
echo -e "\n${BLUE}=======================================================${NC}"
echo -e "${BLUE}     KBot Backtest-Tool (Fib BB + Volume Profile)${NC}"
echo -e "${BLUE}=======================================================${NC}\n"

echo -e "${YELLOW}Wähle einen Analyse-Modus:${NC}"
echo -e "  ${CYAN}1)${NC} Einzel-Analyse (jede Strategie wird isoliert getestet)"
echo -e "  ${CYAN}2)${NC} Manuelle Portfolio-Simulation (du wählst die Strategien)"
echo -e "  ${CYAN}3)${NC} Automatische Portfolio-Optimierung (mit Drawdown-Limit)"
echo -e "  ${CYAN}4)${NC} Fib BB + Volume Profile Backtest (direkter Test)"
read -p "Auswahl (1-4) [Standard: 1]: " MODE
MODE=${MODE:-1}

# --- MODUS 4: Direkter Fib BB + VP Backtest ---
if [ "$MODE" = "4" ]; then
	echo -e "\n${BLUE}--- Fibonacci BB + Volume Profile Backtest ---${NC}\n"
	
	read -p "Symbol (z.B. BTC, ETH, SOL): " SYMBOL
	SYMBOL=${SYMBOL:-BTC}
	
	read -p "Timeframe (z.B. 1d, 4h, 1h): " TIMEFRAME
	TIMEFRAME=${TIMEFRAME:-1d}
	
	read -p "Startdatum (JJJJ-MM-TT) [Standard: 2023-01-01]: " START_DATE
	START_DATE=${START_DATE:-2023-01-01}
	
	read -p "Enddatum (JJJJ-MM-TT) [Standard: heute]: " END_DATE
	END_DATE=${END_DATE:-$(date +%F)}
	
	read -p "Startkapital (USDT) [Standard: 1000]: " CAPITAL
	CAPITAL=${CAPITAL:-1000}
	
	echo -e "\n${YELLOW}Volume Profile Konfluenz:${NC}"
	echo "  Bei aktivierter Konfluenz werden nur Trades ausgeführt,"
	echo "  wenn Fib-Band UND Volume Profile Level übereinstimmen."
	read -p "Konfluenz erforderlich? (j/n) [Standard: j]: " CONFLUENCE
	CONFLUENCE=${CONFLUENCE:-j}
	
	# Konvertiere zu bool
	if [ "$CONFLUENCE" = "j" ] || [ "$CONFLUENCE" = "J" ]; then
		CONFLUENCE_ARG="True"
	else
		CONFLUENCE_ARG="False"
	fi
	
	read -p "Fib BB Länge [Standard: 200]: " FIB_LENGTH
	FIB_LENGTH=${FIB_LENGTH:-200}
	
	read -p "Fib BB Multiplikator [Standard: 3.0]: " FIB_MULT
	FIB_MULT=${FIB_MULT:-3.0}
	
	echo -e "\n${BLUE}Starte Backtest...${NC}\n"
	
	"$PYTHON_BIN" "$RUN_SCRIPT" \
		--symbol "$SYMBOL" \
		--timeframe "$TIMEFRAME" \
		--start_date "$START_DATE" \
		--end_date "$END_DATE" \
		--start_capital "$CAPITAL" \
		--use_volume_profile True \
		--require_confluence "$CONFLUENCE_ARG" \
		--fib_length "$FIB_LENGTH" \
		--fib_mult "$FIB_MULT"
	
	echo -e "\n${GREEN}✓ Backtest abgeschlossen.${NC}"
	deactivate
	exit 0
fi

# --- MODI 1-3: Bestehendes ANN-basiertes System ---
"$PYTHON_BIN" "$RESULTS_SCRIPT" --mode "$MODE"

# --- NACH MODUS 3: SETTINGS-UPDATE ANGEBOT ---
if [ "$MODE" = "3" ] && [ -f ".optimal_configs.tmp" ]; then
	echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo -e "${YELLOW}Sollen die optimierten Strategien übernommen werden?${NC}"
	read -p "Antwort (j/n) [Standard: n]: " UPDATE_SETTINGS
	UPDATE_SETTINGS=${UPDATE_SETTINGS:-n}
	
	if [ "$UPDATE_SETTINGS" = "j" ] || [ "$UPDATE_SETTINGS" = "J" ]; then
		echo -e "\n${BLUE}Lese optimale Konfigurationen...${NC}"
		
		# Lese Config-Namen aus .optimal_configs.tmp
		configs_array=()
		while IFS= read -r config_name; do
			# Entferne Carriage-Returns und überspringe leere Zeilen
			config_name=$(echo "$config_name" | tr -d '\r')
			[ -z "$config_name" ] && continue
			configs_array+=("$config_name")
		done < .optimal_configs.tmp
		
		# Rufe Update-Script auf
		if [ -f "$UPDATE_SETTINGS_SCRIPT" ]; then
			echo -e "${BLUE}Aktualisiere settings.json...${NC}"
			"$PYTHON_BIN" "$UPDATE_SETTINGS_SCRIPT" "${configs_array[@]}"
			UPDATE_EXIT=$?
			
			if [ $UPDATE_EXIT -eq 0 ]; then
				echo -e "\n${GREEN}✓ Settings erfolgreich aktualisiert!${NC}"
				echo -e "${GREEN}  Die optimierten Strategien sind jetzt aktiv.${NC}"
			else
				echo -e "\n${RED}❌ Fehler beim Aktualisieren der Settings.${NC}"
				echo -e "${YELLOW}Backup vorhanden unter: settings.json.backup${NC}"
			fi
		else
			echo -e "${RED}❌ Script nicht gefunden: $UPDATE_SETTINGS_SCRIPT${NC}"
		fi
		
		# Lösche temporäre Datei
		rm -f .optimal_configs.tmp
	else
		echo -e "${YELLOW}✓ Keine Änderungen durchgeführt.${NC}"
		rm -f .optimal_configs.tmp
	fi
	echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
fi

echo -e "\n${GREEN}✓ Backtest abgeschlossen.${NC}"

deactivate
