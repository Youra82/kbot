-----


# KBot


Ein vollautomatischer Trading-Bot für Krypto-Futures auf der Bitget-Börse, der ausschließlich nach Chart-Kanälen (parallel, Dreieck, Keil) handelt. Es gibt keine Machine-Learning- oder Modell-Logik mehr.


Dieses System ist für den Betrieb auf einem Ubuntu-Server ausgelegt und benötigt keine Trainings- oder Optimierungs-Pipeline mehr.


## Strategie

KBot erkennt Chart-Kanäle automatisch (parallel, Dreieck, Keil), informiert per Telegram und handelt eigenständig von Kanalrand zu Kanalrand mit SL/TP. Es gibt keine KI- oder Trainingslogik mehr.


## Arbeitsweise

1. KBot erkennt automatisch Chart-Kanäle im Markt (parallel, Dreieck, Keil).
2. Bei jedem neuen Kanal wird eine Telegram-Nachricht mit Typ und Koordinaten gesendet.
3. Liegt der aktuelle Preis am Kanalrand, wird automatisch ein Trade mit SL/TP eröffnet (Long am unteren, Short am oberen Rand).
4. Es gibt keine Machine-Learning-Modelle, keine Trainings- oder Optimierungslogik mehr.

-----

## Installation 🚀

Führe die folgenden Schritte auf einem frischen Ubuntu-Server aus.

#### 1\. Projekt klonen

```bash
git clone https://github.com/Youra82/jaegerbot.git
```

#### 2\. Installations-Skript ausführen

```bash
cd jaegerbot
```
Installation aktivieren (einmalig):
```bash
chmod +x install.sh
```
Installation ausführen:
```bash
bash ./install.sh
```

#### 3\. API-Schlüssel eintragen

Erstelle eine Kopie der Vorlage und trage deine Schlüssel ein.

```bash
cp secret.json.example secret.json
nano secret.json
```

Speichere mit `Strg + X`, dann `Y`, dann `Enter`.

-----

## Konfiguration & Automatisierung

#### 1\. Strategien finden (Optional, rechenintensiv)

Führe die interaktive Pipeline aus, um neue Strategie-Konfigurationen für bestimmte Handelspaare zu finden.
Run_pipeline aktivieren (einmalig):
```bash
chmod +x run_pipeline.sh
```

```bash
bash ./run_pipeline.sh
```
Backtest aktivieren (einmalig):
```bash
chmod +x show_results.sh
```
Backtest ausführen:
```bash
bash show_results.sh
```
Ergebnisse (CSV) liegen hier:
```bash
ls -l *.csv
```
Ergebnisse (CSV) an Telegram zuschicken:
```bash
chmod +x send_report.sh
```
```bash
./send_report.sh optimal_portfolio_equity.csv
```

```bash
./send_report.sh manual_portfolio_equity.csv
```

```bash
./send_report.sh portfolio_equity_curve.csv
```
Ergebnisse Grafisch an Telegram zuschicken:
```bash
chmod +x show_chart.sh
```

```bash
./show_chart.sh optimal_portfolio_equity.csv
```

```bash
./show_chart.sh manual_portfolio_equity.csv
```


Alte Konfigurationen löschen:
```bash
rm -f src/jaegerbot/strategy/configs/config_*.json
```
Alte Modelle löschen:
```bash
rm -f artifacts/models/*
```
```bash
rm artifacts/db/optuna_studies.db
```

Kontrolle ob alles gelöscht wurde:
```bash
ls -l src/jaegerbot/strategy/configs/

```
Die gefundenen `config_...json`-Dateien werden in `src/jaegerbot/strategy/configs/` gespeichert.

#### 2\. Strategien für den Handel aktivieren

Bearbeite die zentrale Steuerungsdatei `settings.json`, um die Strategien zu definieren, die der `master_runner` überwachen soll.

```bash
nano settings.json
```

**Beispiel `settings.json` (ohne `budget_usdt`):**

```json
{
    "live_trading_settings": {
        "use_auto_optimizer_results": false,
        "active_strategies": [
            {
                "symbol": "AAVE/USDT:USDT",
                "timeframe": "1d"
            },
            {
                "symbol": "BIO/USDT:USDT",
                "timeframe": "4h"
            }
        ]
    },
    "optimization_settings": {
        "enabled": false
    }
}
```

#### 3\. Automatisierung per Cronjob einrichten

Richte den automatischen Prozess für den Live-Handel ein.

```bash
crontab -e
```

Füge die folgende **eine Zeile** am Ende der Datei ein. Passe den Pfad an, falls dein Bot nicht unter `/home/ubuntu/jaegerbot` liegt.

```
# Starte den JaegerBot Master-Runner alle 15 Minuten
*/15 * * * * /usr/bin/flock -n /home/ubuntu/jaegerbot/jaegerbot.lock /bin/sh -c "cd /home/ubuntu/jaegerbot && /home/ubuntu/jaegerbot/.venv/bin/python3 /home/ubuntu/jaegerbot/master_runner.py >> /home/ubuntu/jaegerbot/logs/cron.log 2>&1"
```

*(Hinweis: `flock` ist eine gute Ergänzung, um Überlappungen zu verhindern, aber für den Start nicht zwingend notwendig.)*

Logverzeichnis anlegen:

```
mkdir -p /home/ubuntu/jaegerbot/logs
```
-----

## Tägliche Verwaltung & Wichtige Befehle ⚙️

#### Logs ansehen

Die zentrale `cron.log`-Datei enthält **alle** wichtigen Informationen, sowohl vom Scheduler als auch von den Handels-Entscheidungen.

  * **Logs live mitverfolgen (der wichtigste Befehl):**

    ```bash
    tail -f logs/cron.log
    ```

    *(Mit `Strg + C` beenden)*

  * **Die letzten 200 Zeilen der zentralen Log-Datei anzeigen:**

    ```bash
    tail -n 200 logs/cron.log
    ```

  * **Zentrale Log-Datei nach Fehlern durchsuchen:**

    ```bash
    grep -i "ERROR" logs/cron.log
    ```

  * **Logs einer individuellen Strategie ansehen (für Detail-Analyse):**

    ```bash
    tail -n 100 logs/jaegerbot_BIOUSDTUSDT_4h.log
    ```

#### Cronjob manuell testen

Um den `master_runner` sofort auszuführen, ohne auf den nächsten 15-Minuten-Takt zu warten:

```bash
cd /home/ubuntu/jaegerbot && /home/ubuntu/jaegerbot/.venv/bin/python3 /home/ubuntu/jaegerbot/master_runner.py
```

#### Bot aktualisieren

Um die neueste Version des Codes von deinem Git-Repository zu holen:
Update aktivieren (einmalig)
```bash
chmod +x update.sh
```

```bash
bash ./update.sh
```
Absolut. Das ist eine hervorragende Ergänzung für deine Dokumentation. Das Test-System ist ein zentraler Bestandteil der Qualitätssicherung, und jeder Nutzer sollte wissen, wie man es verwendet.

Ich habe einen neuen Abschnitt "Qualitätssicherung & Tests" erstellt und ihn an der passenden Stelle in deine `README.md`-Datei eingefügt. Er erklärt, *warum* es die Tests gibt und wie man sie ausführt.

-----
Projekt hochladen:

```bash
git add .
```

```bash
git commit -m "Rollback auf stabile Server-Version vom 12.10."
```

```bash
git push --force origin main
```

Komplette Projektstruktur anzeigen:

```bash
chmod +x show_status.sh
```

```bash
bash ./show_status.sh
```

## Qualitätssicherung & Tests 🛡️

Um sicherzustellen, dass alle Kernfunktionen des Bots nach jeder Code-Änderung wie erwartet funktionieren und keine alten Fehler ("Regressionen") wieder auftreten, verfügt das Projekt über ein automatisiertes Test-System.

Dieses "Sicherheitsnetz" prüft zwei Ebenen:

1.  **Struktur-Tests:** Überprüfen, ob alle kritischen Funktionen und Code-Teile vorhanden sind.
2.  **Workflow-Tests:** Führen einen kompletten Live-Zyklus auf der Bitget-API durch (Aufräumen, Order platzieren mit korrekten Einstellungen, SL/TP setzen, Position schließen), um die korrekte Interaktion mit der Börse zu verifizieren.

#### Das Test-System ausführen

Der einfachste Weg, alle Tests zu starten, ist das dafür vorgesehene Skript. Dieser Befehl sollte **nach jeder Code-Änderung** (z.B. nach einem `bash ./update.sh`) ausgeführt werden, um die Stabilität und korrekte Funktion des Bots zu garantieren.

```bash
bash ./run_tests.sh
```

  * **Erfolgreiches Ergebnis:** Alle Tests werden als `PASSED` (grün) markiert. Das bedeutet, alle geprüften Kernfunktionen arbeiten wie erwartet.
  * **Fehlerhaftes Ergebnis:** Mindestens ein Test wird als `FAILED` (rot) markiert. Die Ausgabe gibt einen detaillierten Hinweis darauf, welche Funktion nicht mehr wie erwartet funktioniert. In diesem Fall sollte der Bot nicht im Live-Betrieb eingesetzt werden, bis der Fehler behoben ist.

-----

Ich habe den Text so formuliert, dass er sich nahtlos in den Stil deiner bestehenden Dokumentation einfügt.
-----

### ⚠️ Disclaimer

Dieses Material dient ausschließlich zu Bildungs- und Unterhaltungszwecken. Es handelt sich nicht um eine Finanzberatung. Der Nutzer trägt die alleinige Verantwortung für alle Handlungen. Der Autor haftet nicht für etwaige Verluste.
