#!/bin/bash

# Farben für eine schönere Ausgabe definieren
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Hauptverzeichnis des Projekts bestimmen
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Funktion, um den Inhalt einer Datei formatiert auszugeben
show_file_content() {
    FILE_PATH=$1
    
    # Bestimme eine beschreibende Überschrift basierend auf dem Dateinamen/Pfad
    DESCRIPTION=$(basename "$FILE_PATH")

    if [ -f "${FILE_PATH}" ]; then
        echo -e "\n${BLUE}======================================================================${NC}"
        echo -e "${YELLOW}DATEI: ${DESCRIPTION}${NC}"
        echo -e "${CYAN}Pfad: ${PROJECT_ROOT}/${FILE_PATH#./}${NC}"
        echo -e "${BLUE}----------------------------------------------------------------------${NC}"
        
        # Spezielle Zensur-Logik nur für secret.json
        if [[ "$DESCRIPTION" == "secret.json" ]]; then
            echo -e "${YELLOW}HINWEIS: Sensible Daten in secret.json wurden zensiert.${NC}"
            sed -E 's/("apiKey"|"secret"|"password"|"bot_token"|"chat_id"|"sender_password"): ".*"/"\1": "[ZENSIERT]"/g' "${FILE_PATH}" | cat -n
        else
            cat -n "${FILE_PATH}"
        fi
        
        echo -e "${BLUE}======================================================================${NC}"
    else
        echo -e "\n${RED}WARNUNG: Datei nicht gefunden unter ${FILE_PATH}${NC}"
    fi
}

# --- MENÜ ---
echo -e "${BLUE}======================================================================${NC}"
echo "           KBot Status & Visualisierung"
echo -e "${BLUE}======================================================================${NC}"
echo "  1) Vollständige Code-Dokumentation anzeigen"
echo "  4) Interaktive Kanal-Charts (aktive Strategien aus settings.json)"
read -p "Auswahl [Standard: 1]: " MODE
MODE=${MODE:-1}

# --- OPTION 1: Bestehende Code-Übersicht ---
if [ "$MODE" = "1" ]; then
    echo -e "${BLUE}======================================================================${NC}"
    echo "           Vollständige Code-Dokumentation des KBot"
    echo -e "${BLUE}======================================================================${NC}"

    mapfile -t FILE_LIST < <(find . -path './.venv' -prune -o -path './secret.json' -prune -o \( -name "*.py" -o -name "*.sh" -o -name "*.json" -o -name "*.txt" -o -name ".gitignore" \) -print)

    for filepath in "${FILE_LIST[@]}"; do
        show_file_content "$filepath"
    done

    show_file_content "secret.json"

    echo -e "\n\n${BLUE}======================================================="
    echo "            Aktuelle Projektstruktur"
    echo -e "=======================================================${NC}"
    list_structure() {
        find . -path '*/.venv' -prune -o \
               -path '*/__pycache__' -prune -o \
               -path './.git' -prune -o \
               -path './artifacts/db' -prune -o \
               -path './artifacts/models' -prune -o \
               -path './logs' -prune -o \
               -maxdepth 4 -print | sed -e 's;[^/]*/;|____;g;s;____|; |;g'
    }
    list_structure
    echo -e "${BLUE}=======================================================${NC}"
    exit 0
fi

# --- OPTION 4: Interaktive Kanal-Charts ---
if [ "$MODE" = "4" ]; then
    TODAY=$(date +%F)
    read -p "Startdatum (YYYY-MM-DD) [Standard: 2023-01-01]: " START_DATE
    START_DATE=${START_DATE:-2023-01-01}
    read -p "Enddatum   (YYYY-MM-DD) [Standard: $TODAY]: " END_DATE
    END_DATE=${END_DATE:-$TODAY}
    read -p "Startkapital (USD) [Standard: 1000]: " START_CAP
    START_CAP=${START_CAP:-1000}
    read -p "Fenster für Kanäle (window) [Standard: 50]: " WINDOW
    WINDOW=${WINDOW:-50}

    echo -e "\n${CYAN}Erzeuge interaktive Charts aus settings.json (aktive Strategien)...${NC}"
    python3 src/kbot/analysis/interactive_status.py \
        --start "$START_DATE" \
        --end "$END_DATE" \
        --start-capital "$START_CAP" \
        --window "$WINDOW"

    echo -e "${CYAN}Fertig. Öffne die ausgegebene HTML-Datei im Browser oder VS Code für Zoom/Pane.${NC}"
    exit 0
fi

echo -e "${RED}Ungültige Auswahl.${NC}"
exit 1
