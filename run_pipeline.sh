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

# Zeitraum-Empfehlungen anzeigen
echo -e "\n${BLUE}--- Empfehlung: Optimaler Rückblick-Zeitraum ---${NC}"
printf "+-------------+--------------------------------+\n"
printf "| Timeframe   | Empfohlener Rückblick (Tage)   |\n"
printf "+-------------+--------------------------------+\n"
printf "| 5m, 15m     | 15 - 60 Tage                   |\n"
printf "| 30m, 1h     | 60 - 180 Tage                  |\n"
printf "| 2h, 4h      | 180 - 365 Tage                 |\n"
printf "| 6h, 1d      | 365 - 730 Tage                 |\n"
printf "+-------------+--------------------------------+\n"

read -p "Startdatum (YYYY-MM-DD) oder 'a' für Automatik [Standard: a]: " START_DATE_INPUT
START_DATE_INPUT=${START_DATE_INPUT:-a}

read -p "Enddatum (YYYY-MM-DD, Enter = heute): " END_DATE
if [ -z "$END_DATE" ]; then
    END_DATE=$(date +%F)
fi

read -p "Startkapital (USD, Standard: 1000): " START_CAPITAL
START_CAPITAL=${START_CAPITAL:-1000}

echo -e "\n${YELLOW}--- Optimierung wird gestartet ---${NC}\n"

# Speichere optimale Konfigurationen
OPTIMAL_CONFIGS=()

# Hilfsfunktion: Bestimme lookback_days basierend auf Timeframe
get_lookback_days() {
    local timeframe=$1
    case "$timeframe" in
        5m|15m)
            echo 60
            ;;
        30m|1h)
            echo 180
            ;;
        2h|4h)
            echo 365
            ;;
        6h|1d)
            echo 730
            ;;
        *)
            echo 365  # Default
            ;;
    esac
}

# Starte Optimierung für jede Symbol/Timeframe-Kombination
for symbol in $SYMBOLS; do
    for timeframe in $TIMEFRAMES; do
        echo -e "\n${BLUE}======================================================="
        echo "   Optimiere: $symbol ($timeframe)"
        echo -e "=======================================================${NC}"
        
        # Bestimme Start- und End-Datum
        if [ "$START_DATE_INPUT" == "a" ]; then
            # Automatischer Modus: Zeitraum basierend auf Timeframe
            lookback_days=$(get_lookback_days "$timeframe")
            
            # Berechne Datumsgrenzen
            CURRENT_START_DATE=$(date -d "$lookback_days days ago" +%F)
            CURRENT_END_DATE="$END_DATE"
            
            echo -e "${GREEN}ℹ Automatischer Modus aktiviert${NC}"
            echo -e "${YELLOW}  Timeframe: $timeframe → Lookback: $lookback_days Tage${NC}"
        else
            # Manueller Modus: Verwende eingegebene Daten
            CURRENT_START_DATE="$START_DATE_INPUT"
            CURRENT_END_DATE="$END_DATE"
            echo -e "${YELLOW}ℹ Manueller Zeitraum gewählt${NC}"
        fi
        
        echo -e "${BLUE}  Datenzeitraum: $CURRENT_START_DATE bis $CURRENT_END_DATE${NC}"
        
        echo -e "\n${BLUE}>>> Optimiere $symbol ($timeframe)...${NC}"
        
        if python3 "$OPTIMIZER" \
            --symbol "$symbol" \
            --timeframe "$timeframe" \
            --start-date "$CURRENT_START_DATE" \
            --end-date "$CURRENT_END_DATE" \
            --start-capital "$START_CAPITAL" \
            --save-config; then
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
