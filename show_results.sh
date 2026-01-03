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
UPDATE_SETTINGS_SCRIPT="update_settings_from_optimizer.py"

# Aktiviere venv
if [ ! -f "$VENV_PATH" ]; then
	echo -e "${RED}❌ Virtual Environment nicht gefunden unter: $VENV_PATH${NC}"
	echo "Bitte zuerst 'python3 -m venv .venv' ausführen."
	exit 1
fi

source "$VENV_PATH"

# --- ERWEITERTES MODUS-MENÜ (wie JaegerBot) ---
echo -e "\n${BLUE}=======================================================${NC}"
echo -e "${BLUE}     KBot Backtest-Tool (Kanalstrategie)${NC}"
echo -e "${BLUE}=======================================================${NC}\n"

echo -e "${YELLOW}Wähle einen Analyse-Modus:${NC}"
echo "  1) Einzel-Analyse (jede Strategie wird isoliert getestet)"
echo "  2) Manuelle Portfolio-Simulation (du wählst die Strategien)"
echo "  3) Automatische Portfolio-Optimierung (mit Drawdown-Limit)"
read -p "Auswahl (1-3) [Standard: 1]: " MODE
MODE=${MODE:-1}

python3 "$RESULTS_SCRIPT" --mode "$MODE"

# --- NACH MODUS 3: SETTINGS-UPDATE ANGEBOT ---
if [ "$MODE" = "3" ] && [ -f ".optimal_configs.tmp" ]; then
	echo -e "\n${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
	echo -e "${YELLOW}Sollen die optimierten Strategien übernommen werden?${NC}"
	read -p "Antwort (j/n) [Standard: n]: " UPDATE_SETTINGS
	UPDATE_SETTINGS=${UPDATE_SETTINGS:-n}
	
	if [ "$UPDATE_SETTINGS" = "j" ] || [ "$UPDATE_SETTINGS" = "J" ]; then
		echo -e "\n${BLUE}Lese optimale Konfigurationen...${NC}"
		
		# Lese Config-Namen aus .optimal_configs.tmp (robust, mehrere Einträge)
		if [ ! -s .optimal_configs.tmp ]; then
			echo -e "${RED}❌ Keine Configs in .optimal_configs.tmp gefunden.${NC}"
			exit 1
		fi
		
		mapfile -t config_array < .optimal_configs.tmp
		
		# Rufe Update-Script auf
		if [ -f "$UPDATE_SETTINGS_SCRIPT" ]; then
			echo -e "${BLUE}Aktualisiere settings.json...${NC}"
			python3 "$UPDATE_SETTINGS_SCRIPT" "${config_array[@]}"
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
