#!/bin/bash
# show_results.sh: Backtest- und Ergebnis-Tool für KBot (ohne ML)

echo "KBot Backtest-Tool (ohne Machine Learning)"
echo "-----------------------------------------"
read -p "Symbol (z.B. BTCUSDT): " symbol
read -p "Timeframe (z.B. 4h): " timeframe
read -p "Startdatum (YYYY-MM-DD): " start_date
read -p "Enddatum (YYYY-MM-DD): " end_date

echo "(Backtest-Logik bitte in Python implementieren, z.B. src/kbot/strategy/backtest_channels.py)"
echo "Starte Backtest..."
# Hier wird das KBot-Backtest-Script aufgerufen (Dummy-Ausgabe, Implementierung folgt)
python3 src/kbot/strategy/run.py --symbol "$symbol" --timeframe "$timeframe" --start_date "$start_date" --end_date "$end_date"
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  SETTINGS AUTOMATISCH AKTUALISIEREN?${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    echo "Die optimierten Strategien können jetzt automatisch"
    echo "in die settings.json übernommen werden."
    echo ""
    echo -e "${RED}ACHTUNG:${NC} Dies ersetzt alle aktuellen Strategien!"
    echo "Es wird automatisch ein Backup erstellt (settings.json.backup)."
    echo ""
    read -p "Sollen die optimierten Strategien übernommen werden? (j/n): " APPLY_SETTINGS
    
    if [[ "$APPLY_SETTINGS" =~ ^[jJyY]$ ]]; then
        echo ""
        echo -e "${BLUE}Aktualisiere settings.json...${NC}"
        
        # Lese Config-Dateien aus Temp-Datei
        CONFIGS=$(cat "$OPTIMAL_CONFIGS_FILE")
        
        # Rufe Python-Script auf mit allen Config-Namen als Argumente
        python3 "$UPDATE_SCRIPT" $CONFIGS
        
        if [ $? -eq 0 ]; then
            echo ""
            echo -e "${GREEN}✅ Settings wurden erfolgreich aktualisiert!${NC}"
            echo -e "${GREEN}   Backup wurde erstellt: settings.json.backup${NC}"
        else
            echo ""
            echo -e "${RED}❌ Fehler beim Aktualisieren der Settings.${NC}"
        fi
        
        # Lösche Temp-Datei
        rm -f "$OPTIMAL_CONFIGS_FILE"
    else
        echo ""
        echo -e "${YELLOW}ℹ  Settings wurden NICHT aktualisiert.${NC}"
        echo "Du kannst die Strategien später manuell in settings.json eintragen."
        
        # Lösche Temp-Datei
        rm -f "$OPTIMAL_CONFIGS_FILE"
    fi
fi

deactivate
