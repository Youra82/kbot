# KBot Trainer - Test & Vergleich Anleitung

## 🧪 Wie man beide Versionen vergleicht

### Option 1: Schneller Test mit kleinem Datensatz

```bash
# Alte Version (JaegerBot):
# (in Backup speichern wenn noch vorhanden)
cp kbot/src/kbot/analysis/trainer.py kbot/src/kbot/analysis/trainer_new.py
# Alte Version wiederherstellen aus JaegerBot:
cp jaegerbot/src/jaegerbot/analysis/trainer.py kbot/src/kbot/analysis/trainer_old.py

# Neue Version testen:
cd kbot
python3 src/kbot/analysis/trainer.py \
  --symbols BTC \
  --timeframes 15m \
  --start_date 2024-01-01 \
  --end_date 2024-03-01

# Output speichern:
# Notiere: Genauigkeit, Feature-Count, Training-Zeit
```

### Option 2: Paralleler Test mit unterschiedlichen Datenmengen

```bash
# Test 1: 3 Monate
python3 src/kbot/analysis/trainer.py \
  --symbols BTC \
  --timeframes 15m \
  --start_date 2024-10-01 \
  --end_date 2024-12-31
# → Neue Genauigkeit: X%
# → Training-Zeit: Y Min

# Test 2: 6 Monate
python3 src/kbot/analysis/trainer.py \
  --symbols BTC \
  --timeframes 15m \
  --start_date 2024-07-01 \
  --end_date 2024-12-31
# → Neue Genauigkeit: X+Z%
# → Training-Zeit: Y+W Min

# Test 3: 1 Jahr
python3 src/kbot/analysis/trainer.py \
  --symbols BTC \
  --timeframes 15m \
  --start_date 2023-12-01 \
  --end_date 2024-12-31
# → Neue Genauigkeit: X+Z+K%
# → Training-Zeit: Y+W+L Min
```

---

## 📊 VERGLEICH CHECKLIST

### Performance Metrics
```
┌─────────────────────────────────────────────────────────┐
│  Metrik                    │  ALTE    │  NEUE    │ Diff  │
├─────────────────────────────┼──────────┼──────────┼───────┤
│  Trainings-Zeit (3 Monate)  │ ___min   │ ___min   │ ___% │
│  Trainings-Zeit (6 Monate)  │ ___min   │ ___min   │ ___% │
│  Trainings-Zeit (1 Jahr)    │ ___min   │ ___min   │ ___% │
├─────────────────────────────┼──────────┼──────────┼───────┤
│  Genauigkeit (3 Monate)     │ ___%     │ ___%     │ ___% │
│  Genauigkeit (6 Monate)     │ ___%     │ ___%     │ ___% │
│  Genauigkeit (1 Jahr)       │ ___%     │ ___%     │ ___% │
├─────────────────────────────┼──────────┼──────────┼───────┤
│  Features trainiert         │ 31       │ 38+      │ +7   │
│  ATF Features               │ 0        │ 8        │ +8   │
│  CCI                        │ Nein     │ Ja       │ +1   │
└─────────────────────────────┴──────────┴──────────┴───────┘
```

### Optimizer Test (wichtig!)
```bash
# Mit neuen Modellen optimieren:
cd kbot
./run_pipeline.sh
# → Wahle: BTC 15m
# → Wahle: 3 Monate Lookback
# → Speichere beste Config

# Notiere:
# - Best Profit: __%
# - Best Sharpe: __
# - Min Drawdown: __%
# - Win Rate: __%
```

---

## 🎯 Erwartete Unterschiede

### Training-Zeit
```
Alte Version:  ~8 Minuten (für 1 Jahr BTC 15m)
Neue Version: ~12 Minuten (für 1 Jahr BTC 15m)
Grund: +7 Features = ~50% mehr Berechnung
```

### Modell-Genauigkeit
```
Alte Version:  ~55-60% (baseline)
Neue Version: ~57-63% (mit 38+ Features)
Hoffnung: +2-3% besser durch ATF
```

### Memory & Disk
```
Alte Version:  ~50 MB pro Modell
Neue Version: ~55 MB pro Modell
(Minimal unterschied)
```

---

## 📈 Optimizer Output Vergleich

Nach Training sollte man mit `run_pipeline.sh` testen:

### Mit ALTEN Modellen:
```
======================================================
   KBot Parameter-Optimierung: BTC 15m
======================================================

✓ Beste Strategie gefunden:
  - Profit:      12.5%
  - Sharpe:      1.2
  - Drawdown:    -8.3%
  - Win-Rate:    56%
```

### Mit NEUEN Modellen (erwartet):
```
======================================================
   KBot Parameter-Optimierung: BTC 15m
======================================================

✓ Beste Strategie gefunden:
  - Profit:      14.2%     ← +1.7% (besser!)
  - Sharpe:      1.35      ← +0.15 (besser!)
  - Drawdown:    -7.1%     ← Weniger (besser!)
  - Win-Rate:    58%       ← +2% (besser!)
```

---

## 🔍 DEBUGGING wenn Neue Version schlechter ist

Falls die neue Version NICHT besser ist, überprüfe:

### 1. Feature Validation
```bash
# In Python REPL:
from kbot.utils import ann_model
from kbot.analysis.backtester import load_data

data = load_data("BTC/USDT:USDT", "15m", "2024-01-01", "2024-12-31")
X, y = ann_model.prepare_data_for_ann(data, "15m")

print(f"Features: {len(X.columns)}")
print(f"Feature-Namen: {list(X.columns)}")
print(f"Missing values: {X.isnull().sum().sum()}")
```

### 2. ATF Probleme
```bash
# ATF-Features überprüfen:
print(X[['atf_pearson_r', 'atf_trend_strength', 'atf_slope']])
# Sollten NOT alle 0 sein!
```

### 3. Hyperparameter anpassen
```python
# In ann_model.py build_and_train_model():
# Versuche:
# - Kleinere Learning Rate: 0.0001 statt 0.0005
# - Mehr Dropout: 0.4 statt 0.3
# - Weniger Epochs: 100 statt 150
```

---

## ✅ ENTSCHEIDUNGS-BAUM

```
         Trainiere neue Version
                  |
          Vergleiche Genauigkeit
               /        \
           Besser?     Gleich?      Schlechter?
            /              |             \
        ✅ NEUEN         ⚠️ TESTS      ❌ DEBUG
      BEHALTEN         MEHR DATEN      → Siehe oben
                                          oder
                                     Alte Version
                                       BEHALTEN
```

---

## 🚀 ROLLOUT PLAN

```
Tag 1: Test neue Version
  ✓ Trainiere mit 3/6/12 Monaten
  ✓ Überprüfe Genauigkeit
  ✓ Teste Optimizer-Output

Tag 2: Entscheidung
  Option A: Neue Version ist besser
    ✓ Alte Modelle in Backup sichern
    ✓ Neue Modelle deployten
    ✓ In run_pipeline.sh verwenden

  Option B: Alte Version ist besser
    ✓ Neue Version behalten als Backup
    ✓ Alte Version weiternutzen
    ✓ ATF-Integration für Zukunft planen

  Option C: Gleich
    ✓ Neue Version nutzen (besserer Code)
    ✓ Alte Modelle als Fallback
```

---

## 📝 NOTES

### Pro neue Version:
- ATF wird vollständig genutzt
- +7 Features sollten helfen
- Besserer Code & Logging
- Zukunftssicher

### Pro alte Version:
- Bewährte Architektur
- Schneller Training
- Weniger Komplexität
- Falls neue Version Bugs hat

### Best Case Scenario:
- Neue Version ist 3-5% besser
- Training dauert nur 40% länger (akzeptabel)
- Deployten neue Version
- Alle zufrieden! 🎉

### Worst Case Scenario:
- Neue Version ist 2-3% schlechter
- Trotzdem alte Version behalten
- ATF-Integration für nächste Iteration planen
- Nicht tragisch, wir lernen daraus

---

## 📞 SUPPORT

Falls während dem Vergleich Probleme auftreten:

1. **ATF-Fehler**: Überprüfe `calculate_adaptive_trend_features()` in ann_model.py
2. **Features fehlen**: Überprüfe feature_cols Liste
3. **Training abstürzt**: Überprüfe Datenmenge und Memory
4. **Optimizer langsamer**: Mehr Features = naturlich langsamer
5. **Genauigkeit sinkt**: Neue Features manchmal Overfitting, siehe Debugging

Good luck! 🚀
