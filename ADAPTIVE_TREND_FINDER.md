# Adaptive Trend Finder - Feature Dokumentation

## Übersicht

Der **Adaptive Trend Finder** wurde aus dem PineScript-Indikator von Julien Eche (GPL-3.0 License) nach Python übersetzt und in das KBot ANN-Feature-Set integriert.

## Funktionsweise

Der Indikator verwendet **logarithmische lineare Regression** auf verschiedenen Zeitperioden (20-200 Bars für Short-Term, 300-1200 für Long-Term) und wählt automatisch die Periode mit der höchsten Pearson-Korrelation aus.

### Algorithmus

1. **Log-Transformation**: Preise werden logarithmiert für bessere Trend-Erkennung
2. **Multiple Perioden testen**: 19 verschiedene Perioden werden parallel evaluiert
3. **Lineare Regression**: Für jede Periode wird eine Log-Regression durchgeführt
4. **Pearson-Korrelation**: Misst die Stärke des linearen Zusammenhangs
5. **Beste Periode wählen**: Die Periode mit höchster Korrelation wird ausgewählt
6. **Features ableiten**: Trend-Metriken, Channels und Distanzen werden berechnet

## Neue Features

Die folgenden 7 Features wurden zum ANN-Modell hinzugefügt:

### 1. `atf_pearson_r`
- **Beschreibung**: Pearson-Korrelationskoeffizient (0-1)
- **Interpretation**: 
  - > 0.9: Ultra/Exceptionally Strong
  - 0.8-0.9: Strong/Moderately Strong
  - 0.7-0.8: Moderate
  - < 0.7: Weak
- **Verwendung**: Misst die Verlässlichkeit des erkannten Trends

### 2. `atf_trend_strength`
- **Beschreibung**: Gewichtete Trendstärke mit Richtung (-1 bis +1)
- **Interpretation**:
  - Positive Werte: Aufwärtstrend
  - Negative Werte: Abwärtstrend
  - Betrag: Stärke des Trends
- **Verwendung**: Hauptindikator für Trendrichtung und -intensität

### 3. `atf_detected_period`
- **Beschreibung**: Automatisch gewählte optimale Periode (Anzahl Bars)
- **Interpretation**: Zeigt den Zeithorizont des stärksten Trends
- **Verwendung**: Kontext für andere ATF-Metriken

### 4. `atf_slope`
- **Beschreibung**: Steigung der Log-Regression
- **Interpretation**:
  - Positiv: Exponentielles Wachstum
  - Negativ: Exponentieller Rückgang
  - Größe: Geschwindigkeit der Preisänderung
- **Verwendung**: Direktes Maß für Trend-Momentum

### 5. `atf_std_dev`
- **Beschreibung**: Standardabweichung der Residuen (Log-Skala)
- **Interpretation**: Misst die Volatilität um die Trendlinie
- **Verwendung**: Risiko-Assessment, Channel-Breite

### 6. `atf_upper_channel_dist`
- **Beschreibung**: Relative Distanz zum oberen Channel (2σ)
- **Interpretation**:
  - Negativ: Preis über dem Kanal (überkauft)
  - Positiv: Preis unter dem Kanal
  - Nahe 0: Preis am oberen Rand
- **Verwendung**: Überkauft-Signale, Mean-Reversion

### 7. `atf_lower_channel_dist`
- **Beschreibung**: Relative Distanz zum unteren Channel (2σ)
- **Interpretation**:
  - Positiv: Preis über dem unteren Kanal
  - Negativ: Preis unter dem Kanal (überverkauft)
  - Nahe 0: Preis am unteren Rand
- **Verwendung**: Überverkauft-Signale, Mean-Reversion

### 8. `atf_price_to_trend`
- **Beschreibung**: Relative Abweichung von der Trendlinie
- **Interpretation**:
  - Positiv: Preis über Trend
  - Negativ: Preis unter Trend
- **Verwendung**: Mean-Reversion-Potential

## Trading-Signale

### Trend-Following
```python
# Starker Aufwärtstrend mit Preis nahe der Trendlinie
atf_trend_strength > 0.8 and abs(atf_price_to_trend) < 0.05
```

### Mean-Reversion Long
```python
# Starker Trend, aber Preis am unteren Channel
atf_trend_strength > 0.7 and atf_lower_channel_dist < 0.05
```

### Mean-Reversion Short
```python
# Starker Trend, aber Preis am oberen Channel
atf_trend_strength > 0.7 and atf_upper_channel_dist < 0.05
```

### Trendwende-Warnung
```python
# Niedrige Korrelation = unsicherer Trend
atf_pearson_r < 0.6
```

## Implementierungs-Details

### Funktion: `calculate_adaptive_trend_features(df, use_long_term=False)`

**Parameter:**
- `df`: DataFrame mit OHLCV-Daten
- `use_long_term`: Boolean für Long-Term Mode (300-1200 Bars) oder Short-Term (20-200 Bars)

**Returns:** Dictionary mit 8 Features

**Performance:**
- Berechnung erfolgt nur auf den letzten Bars (rollierend)
- O(n*p) Komplexität (n = Bars, p = Perioden)
- Typische Laufzeit: ~50ms für 500 Bars

### Integration

Die Features werden automatisch in `create_ann_features()` berechnet und dem Feature-Set hinzugefügt:

```python
# In ann_model.py
atf_features = calculate_adaptive_trend_features(df, use_long_term=False)
for key, value in atf_features.items():
    df[key] = value
```

## Unterschiede zum Original PineScript

1. **Python NumPy statt PineScript**: Vektorisierte Operationen für bessere Performance
2. **Keine Visualisierung**: Nur Feature-Extraktion, keine Chart-Darstellung
3. **Fokus auf Short-Term**: Standard ist Short-Term Mode (20-200 Bars)
4. **Batch-Processing**: Berechnung für gesamten DataFrame statt Bar-by-Bar

## Credits

Original PineScript "Adaptive Trend Finder" by Julien Eche
- Copyright (c) 2023-present, Julien Eche
- License: GPL-3.0
- Created: December 2023

Python Implementation for KBot by [Your Name]
- Date: Januar 2026
- Integration: ANN Feature Engineering

## Nächste Schritte

1. **Modell neu trainieren** mit erweiterten Features
2. **Feature Importance analysieren** nach Training
3. **Hyperparameter tunen** für ATF (z.B. dev_multiplier)
4. **Long-Term Mode testen** für längerfristige Strategien

## Test-Ergebnisse

Siehe `test_adaptive_trend.py` für Validierungs-Tests mit synthetischen Daten:
- Aufwärtstrend: Pearson R = 0.86 ✓
- Abwärtstrend: Pearson R = 0.88 ✓
- Seitwärtstrend: Pearson R = 0.73 ✓
