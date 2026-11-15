#!/bin/bash
set -e

echo "--- Sicheres Update wird ausgeführt (Robuste Version) ---"

# 1. Sichere die einzige Datei, die lokal wichtig ist
echo "1. Erstelle ein Backup von 'secret.json'..."
[ -f secret.json ] && cp secret.json secret.json.bak

# 2. Hole die neuesten Daten von GitHub
echo "2. Hole den neuesten Stand von GitHub..."
git fetch origin

# 3. Setze das lokale Verzeichnis hart auf den Stand von GitHub zurück
echo "3. Setze alle Dateien auf den neuesten Stand zurück und verwerfe lokale Änderungen..."
git reset --hard origin/main

# 4. Stelle die API-Schlüssel aus dem Backup wieder her
echo "4. Stelle den Inhalt von 'secret.json' aus dem Backup wieder her..."
if [ -f secret.json.bak ]; then cp secret.json.bak secret.json && rm secret.json.bak; fi

# 5. Lösche den Python-Cache, um alte Code-Versionen zu entfernen
echo "5. Lösche alten Python-Cache für einen sauberen Neustart..."
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type d -name "__pycache__" -delete 2>/dev/null || true

# 6. Setze die Ausführungsrechte für alle Skripte
echo "6. Setze Ausführungsrechte für alle .sh-Skripte..."
chmod +x *.sh

# 7. Laufenden Bot beenden -> der Cron-Waechter startet ihn binnen 5 Minuten mit dem neuen Code
if [ -f artifacts/state/kbot.pid ] && kill -0 "$(cat artifacts/state/kbot.pid)" 2>/dev/null; then
    kill "$(cat artifacts/state/kbot.pid)" && echo "7. Laufenden KBot beendet – der Cron-Waechter startet ihn binnen 5 Minuten neu."
fi

echo "✅ Update erfolgreich abgeschlossen. Dein Bot ist jetzt auf dem neuesten Stand."
