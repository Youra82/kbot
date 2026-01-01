#!/bin/bash
# run_pipeline.sh: KBot Interaktive Parameter-Optimierungs-Pipeline
# Findet optimale Parameter für die Kanal-Erkennungs-Strategie

set -e

# Farben
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}======================================================="
echo "   KBot Interaktive Parameter-Optimierungs-Pipeline"
echo -e "=======================================================${NC}"

# Pfade definieren
VENV_PATH=".venv/bin/activate"
OPTIMIZER="src/kbot/analysis/optimizer.py"

# Virtuelle Umgebung aktivieren
if [ ! -f "$VENV_PATH" ]; then
    echo -e "${RED}❌ Virtual Environment nicht gefunden!${NC}"
    exit 1
fi

source "$VENV_PATH"
echo -e "${GREEN}✓ Virtual Environment aktiviert${NC}"

# Interaktive Eingabe
echo -e "\n${YELLOW}--- Konfiguration der Optimierung ---${NC}\n"

read -p "Symbol(e) (z.B. BTC ETH SOL): " SYMBOLS
if [ -z "$SYMBOLS" ]; then
    echo -e "${RED}Keine Symbole eingegeben!${NC}"
    exit 1
fi

read -p "Timeframe(s) (z.B. 1d 4h 1h): " TIMEFRAMES
if [ -z "$TIMEFRAMES" ]; then
    echo -e "${RED}Keine Timeframes eingegeben!${NC}"
    exit 1
fi

echo -e "\n${BLUE}Empfehlung für Optimierungs-Zeitraum:${NC}"
echo "  • 5m, 15m:     15 - 60 Tage"
echo "  • 30m, 1h:     60 - 180 Tage"
echo "  • 4h, 2h:      180 - 365 Tage"
echo "  • 1d:          365 - 730 Tage"

read -p "Startdatum (YYYY-MM-DD): " START_DATE
if [ -z "$START_DATE" ]; then
    echo -e "${RED}Keine Startdatum eingegeben!${NC}"
    exit 1
fi

read -p "Enddatum (YYYY-MM-DD, Enter = heute): " END_DATE
if [ -z "$END_DATE" ]; then
    END_DATE=$(date +%F)
fi

read -p "Startkapital (USD, Standard: 1000): " START_CAPITAL
START_CAPITAL=${START_CAPITAL:-1000}

echo -e "\n${YELLOW}--- Optimierung wird gestartet ---${NC}\n"

# Speichere optimale Konfigurationen
OPTIMAL_CONFIGS=()

# Starte Optimierung für jede Symbol/Timeframe-Kombination
for symbol in $SYMBOLS; do
    for timeframe in $TIMEFRAMES; do
        echo -e "\n${BLUE}>>> Optimiere $symbol ($timeframe)...${NC}"
        
        python3 "$OPTIMIZER" \
            --symbol "$symbol" \
            --timeframe "$timeframe" \
            --start-date "$START_DATE" \
            --end-date "$END_DATE" \
            --start-capital "$START_CAPITAL" \
            --save-config
        
        if [ $? -eq 0 ]; then
            OPTIMAL_CONFIGS+=("$symbol ($timeframe)")
            echo -e "${GREEN}✓ Optimierung für $symbol ($timeframe) abgeschlossen${NC}"
        else
            echo -e "${RED}✗ Fehler bei $symbol ($timeframe)${NC}"
        fi
    done
done

# Zusammenfassung
echo -e "\n${BLUE}======================================================="
echo "   Optimierung abgeschlossen!"
echo -e "=======================================================${NC}\n"

if [ ${#OPTIMAL_CONFIGS[@]} -gt 0 ]; then
    echo -e "${GREEN}✓ Optimierte Strategien:${NC}"
    for config in "${OPTIMAL_CONFIGS[@]}"; do
        echo -e "  • $config"
    done
    echo -e "\n${YELLOW}Die optimalen Konfigurationen wurden in 'artifacts/optimal_configs/' gespeichert.${NC}"
    echo -e "${YELLOW}Du kannst sie jetzt mit './show_results.sh' verwenden.${NC}"
else
    echo -e "${RED}❌ Keine erfolgreiche Optimierungen!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✓ Pipeline abgeschlossen!${NC}"
