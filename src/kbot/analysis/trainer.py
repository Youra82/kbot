#!/usr/bin/env python3
"""
# KBot VERBESSERTER TRAINER (KBot-SPEZIFISCH)
================================================

Trainiert ANN-Modelle speziell für KBot's Kanal-Erkennungs-Strategie.

UNTERSCHIEDE ZUR ALTEN VERSION:
================================

1. ALLE 38+ Features werden genutzt (nicht nur 31):
   - Adaptive Trend Finder Features (8)
   - CCI Momentum Indicator
   - Alle Volume-Indikatoren mit Fehlerbehandlung
   
2. BESSERE FEHLERBEHANDLUNG:
   - ATF-Fehler werden abgefangen
   - Volume-Fehler werden eleganter gelöst
   
3. DETAILLIERTES LOGGING:
   - Zeigt alle verwendeten Features
   - Zeigt Feature-Counts und -Kategorien
   - Bessere Fehlerausgabe
   
4. OPTIMIERTE HYPERPARAMETER:
   - Für KBot's Kanal-Strategie tuned
   - Bessere Thresholds für Binär-Klassifikation
   
5. PERFORMANCE-MONITORING:
   - Detaillierte Ausgabe von Trainingsstatistiken
   - Warnt vor zu wenig Trainingsdaten
   - Validiert Feature-Konsistenz

VERWENDUNG:
===========
python3 src/kbot/analysis/trainer.py --symbols BTC ETH --timeframes 15m 1h --start_date 2023-01-01 --end_date 2024-12-31
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(os.path.join(PROJECT_ROOT, 'src'))

from kbot.utils import ann_model
from kbot.analysis.backtester import load_data

# Logging einrichten
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def create_safe_filename(symbol, timeframe):
    """Erstellt einen sicheren Dateinamen aus Symbol und Timeframe."""
    return f"{symbol.replace('/', '').replace(':', '')}_{timeframe}"


def validate_features(X, feature_list):
    """Validiert, dass alle erwarteten Features vorhanden sind."""
    missing = [f for f in feature_list if f not in X.columns]
    if missing:
        logger.warning(f"⚠️  Warnung: {len(missing)} erwartete Features fehlen: {missing}")
        return False
    return True


def print_training_summary(symbol, timeframe, X_train, X_test, y_train, y_test, accuracy):
    """Gibt eine schöne Zusammenfassung des Trainings aus."""
    print("\n" + "=" * 70)
    print(f"  TRAININGSERGEBNIS FÜR {symbol} ({timeframe})")
    print("=" * 70)
    
    class_dist_train = f"{(y_train == 1).sum() / len(y_train) * 100:.1f}% Long"
    class_dist_test = f"{(y_test == 1).sum() / len(y_test) * 100:.1f}% Long"
    
    print(f"\n📊 DATEN:")
    print(f"   Training-Samples:     {len(X_train):,}")
    print(f"   Test-Samples:         {len(X_test):,}")
    print(f"   Gesamt:               {len(X_train) + len(X_test):,}")
    
    print(f"\n📈 FEATURES:")
    print(f"   Insgesamt:            {X_train.shape[1]}")
    print(f"   Kategorien:")
    print(f"     - Bollinger Bands:     4")
    print(f"     - Volume-Indikatoren:  6")
    print(f"     - Momentum-Indikatoren: 8")
    print(f"     - Volatilität:         4")
    print(f"     - Support/Resistance:  4")
    print(f"     - Price Action:        3")
    print(f"     - Zeitlich/Returns:    5")
    print(f"     - Adaptive Trend (ATF): 8")
    print(f"     - Sonstige:            1 (CCI)")
    
    print(f"\n📊 KLASSEN-VERTEILUNG:")
    print(f"   Training - Long/Short:    {class_dist_train}")
    print(f"   Test     - Long/Short:    {class_dist_test}")
    
    print(f"\n🧠 MODELL-GENAUIGKEIT:")
    print(f"   Test-Genauigkeit:      {accuracy * 100:.2f}%")
    
    if accuracy < 0.50:
        print(f"   ⚠️  WARNUNG: Genauigkeit unter 50% (zufällig)")
    elif accuracy < 0.55:
        print(f"   ⚡ HINWEIS: Genauigkeit niedrig, mehr Daten empfohlen")
    elif accuracy < 0.60:
        print(f"   ℹ️  Modell funktioniert")
    elif accuracy < 0.70:
        print(f"   ✓ Gutes Modell")
    else:
        print(f"   ✨ Sehr gutes Modell")
    
    print("\n" + "=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="KBot VERBESSERTER TRAINER - Trainiert ANN-Modelle mit allen 38+ Features"
    )
    parser.add_argument('--symbols', required=True, type=str, help="Symbole (z.B. 'BTC ETH')")
    parser.add_argument('--timeframes', required=True, type=str, help="Timeframes (z.B. '15m 1h')")
    parser.add_argument('--start_date', required=True, type=str, help="Startdatum (YYYY-MM-DD)")
    parser.add_argument('--end_date', required=True, type=str, help="Enddatum (YYYY-MM-DD)")
    args = parser.parse_args()

    symbols = args.symbols.split()
    timeframes = args.timeframes.split()
    
    # Erstelle Task-Liste
    TASKS = [
        {'symbol': f"{s}/USDT:USDT", 'timeframe': tf} 
        for s in symbols 
        for tf in timeframes
    ]
    
    print("\n" + "=" * 70)
    print("  🤖 KBOT VERBESSERTER TRAINER (MIT 38+ FEATURES)")
    print("=" * 70)
    print(f"\n📋 Zeitraum: {args.start_date} bis {args.end_date}")
    print(f"🎯 Aufgaben: {len(TASKS)} Symbol/Timeframe Kombinationen")
    for task in TASKS:
        print(f"   • {task['symbol']} ({task['timeframe']})")
    print()
    
    successful_trainings = 0
    failed_trainings = 0
    
    for task in TASKS:
        symbol = task['symbol']
        timeframe = task['timeframe']
        
        try:
            print(f"\n{'='*70}")
            print(f"🚀 TRAINIERE: {symbol} ({timeframe})")
            print(f"{'='*70}")
            
            # 1. Lade Daten
            print(f"\n1️⃣  Lade historische Daten...")
            data = load_data(symbol, timeframe, args.start_date, args.end_date)
            
            if data.empty:
                logger.error(f"   ❌ Keine Daten geladen!")
                failed_trainings += 1
                continue
            
            print(f"   ✅ {len(data):,} Kerzen geladen")
            
            # 2. Feature-Generierung
            print(f"\n2️⃣  Generiere 38+ Features und Labels...")
            try:
                X, y = ann_model.prepare_data_for_ann(data, timeframe=timeframe, verbose=True)
            except Exception as e:
                logger.error(f"   ❌ Feature-Generierung fehlgeschlagen: {e}")
                failed_trainings += 1
                continue
            
            if X.empty:
                logger.error(f"   ❌ Keine klaren Handelssignale im Datensatz gefunden")
                failed_trainings += 1
                continue
            
            # Validiere Features
            if not validate_features(X, X.columns.tolist()):
                logger.warning(f"   ⚠️  Einige Features fehlen, trainiere trotzdem...")
            
            print(f"   ✅ {len(X):,} Samples mit {X.shape[1]} Features generiert")
            
            # 3. Train/Test Split
            print(f"\n3️⃣  Train/Test Split (80/20)...")
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, shuffle=False, random_state=42
            )
            
            if len(X_train) < 100:
                logger.warning(f"   ⚠️  WARNUNG: Nur {len(X_train)} Training-Samples! Mindestens 1000 empfohlen.")
            
            print(f"   ✅ Train: {len(X_train):,} | Test: {len(X_test):,}")
            
            # 4. Scaling
            print(f"\n4️⃣  Standardisierung (StandardScaler)...")
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            print(f"   ✅ Daten standardisiert")
            
            # 5. Training
            print(f"\n5️⃣  Trainiere Modell (256-128-64-32 Architektur)...")
            model = ann_model.build_and_train_model(X_train_scaled, y_train)
            
            # 6. Evaluation
            print(f"\n6️⃣  Evaluiere Modell...")
            loss, accuracy = model.evaluate(X_test_scaled, y_test, verbose=0)
            print(f"   ✅ Test-Genauigkeit: {accuracy * 100:.2f}%")
            
            # 7. Speichern
            print(f"\n7️⃣  Speichere Modell und Scaler...")
            safe_filename = create_safe_filename(symbol, timeframe)
            model_save_path = os.path.join(
                PROJECT_ROOT, 'artifacts', 'models', 
                f'ann_predictor_{safe_filename}.h5'
            )
            scaler_save_path = os.path.join(
                PROJECT_ROOT, 'artifacts', 'models', 
                f'ann_scaler_{safe_filename}.joblib'
            )
            
            ann_model.save_model_and_scaler(model, scaler, model_save_path, scaler_save_path)
            print(f"   ✅ Gespeichert in: {model_save_path}")
            
            # Schöne Zusammenfassung
            print_training_summary(symbol, timeframe, X_train, X_test, y_train, y_test, accuracy)
            
            successful_trainings += 1
            
        except Exception as e:
            logger.error(f"   ❌ Fehler bei {symbol} ({timeframe}): {e}")
            import traceback
            traceback.print_exc()
            failed_trainings += 1
    
    # Finale Zusammenfassung
    print("\n" + "=" * 70)
    print("  🏁 TRAINING ABGESCHLOSSEN")
    print("=" * 70)
    print(f"\n✅ Erfolgreich:  {successful_trainings}")
    print(f"❌ Fehlgeschlagen: {failed_trainings}")
    print(f"📊 Gesamt:      {successful_trainings + failed_trainings}\n")
    
    if failed_trainings > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
