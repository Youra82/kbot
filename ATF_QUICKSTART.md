# Adaptive Trend Finder - Quick Start Guide

## 🚀 Sofort loslegen

### 1. Funktionstest (30 Sekunden)
```bash
# In PowerShell (Windows)
.\.venv\Scripts\python.exe test_adaptive_trend.py

# In Bash (Linux/Mac)
.venv/bin/python test_adaptive_trend.py
```

**Erwartetes Ergebnis:** 
```
✓ Aufwärtstrend: Pearson R = 0.86
✓ Abwärtstrend: Pearson R = 0.88
✓ Seitwärtstrend: Pearson R = 0.73
✓ ALLE TESTS ERFOLGREICH!
```

### 2. Marktanalyse mit Charts (2 Minuten)
```bash
# Windows
.\show_adaptive_trend.ps1

# Linux/Mac
./show_adaptive_trend.sh
```

**Was passiert:**
- Lädt aktuelle BTC, ETH, DOGE Daten
- Berechnet ATF-Features
- Erstellt 3 PNG-Dateien mit Analyse-Charts
- Gibt Trading-Interpretationen aus

### 3. Modelle neu trainieren (WICHTIG!)
```bash
# Alle Symbole und Timeframes
python train_improved.py --symbols BTC ETH DOGE ADA AAVE --timeframes 5m 15m 30m 1h 2h 4h 6h 1d --start_date 2023-01-01 --end_date 2025-12-31
```

**⚠️ ACHTUNG:** Dies dauert mehrere Stunden!

### 4. Backtesting mit neuen Features
```bash
# Nach dem Training
python run_backtest_direct.py
```

## 📊 Was wurde hinzugefügt?

**7 neue Features** für das ANN-Modell:

| Feature | Beschreibung | Range | Trading-Signal |
|---------|--------------|-------|----------------|
| `atf_pearson_r` | Trend-Korrelation | 0-1 | >0.9 = Ultra Strong |
| `atf_trend_strength` | Gewichtete Trendstärke | -1 bis +1 | Richtung + Stärke |
| `atf_slope` | Trend-Geschwindigkeit | real | Momentum-Indikator |
| `atf_std_dev` | Kanal-Volatilität | real | Risiko-Maß |
| `atf_upper_channel_dist` | Abstand oberer Kanal | real | Überkauft wenn <0 |
| `atf_lower_channel_dist` | Abstand unterer Kanal | real | Überverkauft wenn <0 |
| `atf_price_to_trend` | Abweichung von Trend | real | Mean-Reversion |

## 🎯 Einfache Trading-Regeln

### Starker Aufwärtstrend
```python
atf_trend_strength > 0.8 and atf_pearson_r > 0.85
→ LONG Signal
```

### Überkauft
```python
atf_upper_channel_dist < 0
→ EXIT / TAKE PROFIT
```

### Überverkauft
```python
atf_lower_channel_dist < 0 and atf_trend_strength > 0.7
→ BUY THE DIP
```

### Trendwende-Warnung
```python
atf_pearson_r < 0.6
→ VORSICHT - Unsicherer Trend
```

## 📖 Weitere Informationen

- **Vollständige Doku:** [ADAPTIVE_TREND_FINDER.md](ADAPTIVE_TREND_FINDER.md)
- **Änderungslog:** [ATF_CHANGES_LOG.md](ATF_CHANGES_LOG.md)
- **Original PineScript:** Siehe Kommentare in Code

## 🛠️ Troubleshooting

### "ModuleNotFoundError: tensorflow"
```bash
# Virtual Environment aktivieren
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate      # Linux/Mac
```

### "Keine Daten verfügbar"
- Überprüfe Datenbankverbindung in `secret.json`
- Stelle sicher, dass historische Daten vorhanden sind

### Features werden nicht benutzt
- **Lösung:** Modelle müssen NEU trainiert werden!
- Alte Modelle kennen die neuen Features nicht

## ✅ Checkliste

- [ ] Test erfolgreich ausgeführt
- [ ] Visualisierung funktioniert
- [ ] Modelle neu trainiert (WICHTIG!)
- [ ] Backtest durchgeführt
- [ ] Feature Importance analysiert

## 🎉 Fertig!

Der Adaptive Trend Finder ist jetzt aktiv und wird automatisch für alle neuen Predictions verwendet. Die 7 zusätzlichen Features helfen dem ANN-Modell, Trends besser zu erkennen und profitable Trading-Entscheidungen zu treffen.

**Viel Erfolg beim Trading! 🚀📈**
