#!/bin/bash
# Visualisiert den Adaptive Trend Finder für verschiedene Symbole

echo "================================"
echo "Adaptive Trend Finder Analyse"
echo "================================"
echo ""

# Python mit venv ausführen
source .venv/bin/activate 2>/dev/null || .venv/Scripts/activate 2>/dev/null

python visualize_adaptive_trend.py

echo ""
echo "Analyse abgeschlossen!"
