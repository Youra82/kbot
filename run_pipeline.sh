#!/bin/bash
# run_pipeline.sh: KBot Interaktive Parameter-Optimierungs-Pipeline
# Findet optimale Parameter für die Kanal-Erkennungs-Strategie

# KEIN set -e oder trap ERR mehr!
# Pipeline-Fehler sollen nicht zum Abbruch führen

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
TRAINER="src/kbot/analysis/trainer.py"
FIND_BEST_THRESHOLD="src/kbot/analysis/find_best_threshold.py"
OPTIMIZER="src/kbot/analysis/optimizer.py"

# Virtuelle Umgebung aktivieren
if [ ! -f "$VENV_PATH" ]; then
    echo -e "${RED}❌ Virtual Environment nicht gefunden!${NC}"
    exit 1
fi

source "$VENV_PATH" || { echo -e "${RED}❌ Fehler beim Aktivieren der Virtual Environment${NC}"; exit 1; }
echo -e "${GREEN}✓ Virtual Environment aktiviert${NC}"

# CLEANUP-Assistent
echo -e "\n${YELLOW}Möchtest du alle alten, generierten Modelle & Konfigurationen löschen?${NC}"
read -p "Dies wird für einen kompletten Neustart empfohlen. (j/n) [Standard: n]: " CLEANUP_CHOICE
CLEANUP_CHOICE=${CLEANUP_CHOICE:-n}
CLEANUP_CHOICE=$(echo ${CLEANUP_CHOICE} | tr -d '[:space:]')

if [[ "${CLEANUP_CHOICE,,}" == "j" ]]; then
    echo -e "${YELLOW}Lösche alte Modelle und Konfigurationen...${NC}"
    rm -f src/kbot/strategy/configs/config_*.json
    rm -f artifacts/models/ann_*
    echo -e "${GREEN}✓ Aufräumen abgeschlossen${NC}"
else
    echo -e "${GREEN}✓ Alte Ergebnisse werden beibehalten${NC}"
fi

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

# Zusätzliche Optionen wie im JaegerBot
read -p "CPU-Kerne [Standard: -1 für alle]: " N_CORES
N_CORES=${N_CORES:--1}

echo -e "\n${YELLOW}Wähle einen Optimierungs-Modus:${NC}"
echo "  1) Strenger Modus"
echo "  2) 'Finde das Beste'-Modus"
read -p "Auswahl (1-2) [Standard: 1]: " OPTIM_MODE
OPTIM_MODE=${OPTIM_MODE:-1}

if [ "$OPTIM_MODE" == "1" ]; then
    MODE_ARG="strict"
    read -p "Max Drawdown % [Standard: 30]: " MAX_DD
    MAX_DD=${MAX_DD:-30}
    read -p "Min Win-Rate % [Standard: 55]: " MIN_WR
    MIN_WR=${MIN_WR:-55}
    read -p "Min PnL % [Standard: 0]: " MIN_PNL
    MIN_PNL=${MIN_PNL:-0}
else
    MODE_ARG="best_profit"
    read -p "Max Drawdown % [Standard: 30]: " MAX_DD
    MAX_DD=${MAX_DD:-30}
    MIN_WR=0
    MIN_PNL=-99999
fi

read -p "Mindest-Modell-Genauigkeit % [Standard: 50]: " MIN_ACCURACY
MIN_ACCURACY=${MIN_ACCURACY:-50}

echo -e "\n${YELLOW}--- 3-Stufen-Pipeline wird gestartet ---${NC}\n"

# Speichere optimale Konfigurationen
OPTIMAL_CONFIGS=()
SUCCESSFUL_COUNT=0
FAILED_COUNT=0

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

# Starte 3-Stufen-Pipeline für jede Symbol/Timeframe-Kombination
for symbol in $SYMBOLS; do
    for timeframe in $TIMEFRAMES; do
        echo -e "\n${BLUE}======================================================="
        echo "   Pipeline: $symbol ($timeframe)"
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
        
        # ========== STUFE 1: TRAINING ==========
        echo -e "\n${GREEN}>>> STUFE 1/3: Trainiere Modell für $symbol ($timeframe)...${NC}"
        if ! TRAINER_OUTPUT=$(python3 "$TRAINER" --symbols "$symbol" --timeframes "$timeframe" --start_date "$CURRENT_START_DATE" --end_date "$CURRENT_END_DATE" 2>&1); then
            echo -e "${RED}✗ Training-Fehler für $symbol ($timeframe)${NC}"
            ((FAILED_COUNT++))
            continue
        fi
        echo "$TRAINER_OUTPUT"
        
        # Extrahiere Modell-Genauigkeit
        MODEL_ACCURACY=$(echo "$TRAINER_OUTPUT" | grep -oP 'Test-Genauigkeit:\s*\K[0-9.]+' | head -1)
        
        if [[ -z "$MODEL_ACCURACY" ]] || ! (( $(echo "$MODEL_ACCURACY >= $MIN_ACCURACY" | bc -l 2>/dev/null) )); then
            echo -e "${RED}✗ Genauigkeit unzureichend (${MODEL_ACCURACY}% < ${MIN_ACCURACY}%)${NC}"
            ((FAILED_COUNT++))
            continue
        fi
        echo -e "${GREEN}✓ Training erfolgreich (Genauigkeit: ${MODEL_ACCURACY}%)${NC}"
        
        # ========== STUFE 2: THRESHOLD FINDER ==========
        if [ -f "$FIND_BEST_THRESHOLD" ]; then
            echo -e "\n${GREEN}>>> STUFE 2/3: Suche besten Threshold...${NC}"
            if THRESHOLD_OUTPUT=$(python3 "$FIND_BEST_THRESHOLD" --symbol "$symbol" --timeframe "$timeframe" --start_date "$CURRENT_START_DATE" --end_date "$CURRENT_END_DATE" 2>&1); then
                BEST_THRESHOLD=$(echo "$THRESHOLD_OUTPUT" | tail -n 1)
                
                if [[ "$BEST_THRESHOLD" =~ ^[0-9]+\.[0-9]+$ ]]; then
                    echo -e "${GREEN}✓ Bester Threshold gefunden: $BEST_THRESHOLD${NC}"
                else
                    echo -e "${YELLOW}⚠ Kein Threshold gefunden, verwende Default${NC}"
                    BEST_THRESHOLD="0.5"
                fi
            else
                echo -e "${YELLOW}⚠ Threshold Finder Fehler, verwende Default${NC}"
                BEST_THRESHOLD="0.5"
            fi
        else
            echo -e "${YELLOW}⚠ Threshold Finder nicht vorhanden, überspringe Stufe 2${NC}"
            BEST_THRESHOLD="0.5"
        fi
        
        # ========== STUFE 3: OPTIMIZER ==========
        echo -e "\n${GREEN}>>> STUFE 3/3: Optimiere Parameter für $symbol ($timeframe)...${NC}"
        
        if python3 "$OPTIMIZER" \
            --symbol "$symbol" \
            --timeframe "$timeframe" \
            --start-date "$CURRENT_START_DATE" \
            --end-date "$CURRENT_END_DATE" \
            --start-capital "$START_CAPITAL" \
            --mode "$MODE_ARG" \
            --max-dd "$MAX_DD" \
            --min-win-rate "$MIN_WR" \
            --min-return "$MIN_PNL" \
            --jobs "$N_CORES" \
            --save-config 2>&1; then
            OPTIMAL_CONFIGS+=("$symbol ($timeframe) - Genauigkeit: ${MODEL_ACCURACY}%")
            echo -e "${GREEN}✓ Pipeline für $symbol ($timeframe) erfolgreich${NC}"
            ((SUCCESSFUL_COUNT++))
        else
            echo -e "${YELLOW}⚠ Optimizer für $symbol ($timeframe) abgeschlossen (eventuell keine guten Konfigurationen)${NC}"
            ((FAILED_COUNT++))
        fi
    done
done

# Zusammenfassung
echo -e "\n${BLUE}======================================================="
echo "   🏁 KBot 3-Stufen-Pipeline abgeschlossen!"
echo -e "=======================================================${NC}\n"

echo -e "${BLUE}Zusammenfassung:${NC}"
echo -e "  ✓ Erfolgreich:    ${SUCCESSFUL_COUNT}"
echo -e "  ✗ Fehlgeschlagen: ${FAILED_COUNT}"
echo -e "  📊 Gesamt:        $((SUCCESSFUL_COUNT + FAILED_COUNT))"

if [ ${#OPTIMAL_CONFIGS[@]} -gt 0 ]; then
    echo -e "\n${GREEN}✓ Optimierte Strategien:${NC}"
    for config in "${OPTIMAL_CONFIGS[@]}"; do
        echo -e "  • $config"
    done
    echo -e "\n${YELLOW}Die optimalen Konfigurationen wurden in 'src/kbot/strategy/configs/' gespeichert.${NC}"
    echo -e "${YELLOW}Du kannst sie jetzt mit './show_results.sh' verwenden.${NC}"
else
    echo -e "${RED}❌ Keine erfolgreiche Pipelines!${NC}"
    exit 1
fi

echo -e "\n${GREEN}✓ Alle Stufen abgeschlossen (Training → Threshold → Optimizer)!${NC}\n"
