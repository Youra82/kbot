# KBot — Wal-Einzahlungen auf Binance → Short auf Bitget

KBot liest live die Ethereum-Blockchain und erkennt, wenn ein Wal einen Altcoin in großer Menge
**auf Binance einzahlt**. Wer 500.000 $ eines Coins an eine Börse schickt, will ihn meist verkaufen.
KBot eröffnet dann einen **Short auf Bitget für 60 Minuten**.

> **Status: Dry-Run (Paper-Trading).** Es werden keine echten Orders platziert. Der Live-Modus ist
> gesperrt, bis der Vorwärtstest die Backtest-Ergebnisse bestätigt.

---

## Warum das funktionieren kann

```
Wal ──► eigene Binance-Einzahladresse ──► (Bestätigungen, ~1–5 min) ──► Binance schreibt gut ──► Verkauf
          │                                                                                  │
          └── on-chain sofort sichtbar  ◄── KBot liest hier mit                Bitget folgt Binance
```

- Die Einzahlung ist auf der Blockchain sichtbar, **bevor** Binance sie gutschreibt und der Wal verkaufen kann.
- Binance-Einzahladressen sind nicht beschriftet. KBot lernt sie selbst: Jede Adresse, die Coins an die
  Binance-Sammel-Wallet *Binance 14* (`0x28c6…1d60`) weiterleitet („Sweep“), ist eine Einzahladresse.
  Gezählt werden nur Einzahlungen an Adressen, die **vorher** schon bekannt waren, genau wie im Backtest.
- Bitget läuft Binance nachweislich hinterher (eigener Lead-Lag-Test, 41 Coins, 90 Tage).

## Belege: präregistrierter Backtest

Die Regel wurde **vor** dem Ansehen der Kurse festgelegt und eingefroren
([`research/cex/PRAEREGISTRIERUNG.md`](research/cex/PRAEREGISTRIERUNG.md), SHA-256 `504b4591…`).

**Daten:** 22 ERC-20-Altcoins, 10/2025 bis 10/2026, 16.547 Einzahlungen an bekannte Binance-Adressen,
davon 1.513 ≥ 500k $ (~3 Signale pro Tag).
**Regel:** Einzahlung ≥ 500k $ → Short, Einstieg 1–2 min nach dem Block, Ausstieg nach 60 min.

| | Entwicklung (11/2025–06/2026) | Test (06–10/2026) |
|---|---|---|
| Trades | 655 | 398 |
| Coin schlechter als normal | **+0,21 %** (t = 2,9) | **+0,18 %** (t = 2,3) |
| gegen BTC (marktneutral) | +0,23 % (t = 3,6) | +0,21 % (t = 3,0) |
| Short netto nach 0,12 % Taker-Gebühr | +0,10 % | +0,03 % |

**Ergebnis: bestanden**, alle vorab festgelegten Kriterien erfüllt. Weitere Prüfungen
([`robust.py`](research/cex/robust.py)): Der Effekt kommt nicht von einem einzelnen Coin, bleibt beim
Zusammenfassen gleichzeitiger Ereignisse signifikant und tritt **nur bei Wal-Absendern** auf.
Verschiebungen Börse → Binance (z. B. von Coinbase) zeigen keinen Effekt.

### Simulation 100 USDT, 01.05.–08.10.2026 (532 Signale, Margin ⅓ je Trade)

| Hebel | Market-Orders (0,12 %) | Limit-Orders (0,04 %)* |
|---|---|---|
| 1x | 124 USDT, Max-DD −9 % | 143 USDT, Max-DD −8 % |
| 3x | 183 USDT, Max-DD −26 % | 281 USDT, Max-DD −22 % |
| **5x** | 255 USDT, Max-DD −40 % | **517 USDT, Max-DD −34 %** ← Dry-Run-Einstellung |

\* *Limit-Orders unter der Annahme, dass jede Order gefüllt wird. Genau das misst der Dry-Run jetzt live.*

**Ehrliche Einordnung:** Der Effekt ist echt, aber klein (~0,2 % brutto pro Trade). Der größte Teil
des Simulationsgewinns entstand im Mai und Juni. Ab Juli lag die Market-Variante etwa bei null,
die Limit-Variante bei +33 %. **Die Gebühren entscheiden.** Ob Limit-Orders in der Praxis gefüllt
werden, kann nur der Live-Test zeigen.

## Was der Dry-Run macht

- Scannt jeden Ethereum-Block (Abfragen à max. 10 Blöcke, Alchemy Free Tier), lernt Sweeps und erkennt Einzahlungen.
- Bewertet jede Einzahlung mit dem Bitget-Kurs und wendet die Regel aus
  [`deposit_signal.py`](src/kbot/strategy/deposit_signal.py) an. Der Backtest nutzt **dieselbe Funktion**.
- Führt **zwei Paper-Konten** parallel, Start je 100 USDT, 5x Hebel, Margin ⅓:
  - **Limit:** Sell-Limit am Ask. Gefüllt nur, wenn der Kurs ihn innerhalb von 2 min erreicht, sonst „verpasst“.
    Ausstieg per Buy-Limit am Bid, falls nicht gefüllt per Market. Maker 0,02 % je Seite.
  - **Market:** Einstieg am Bid, Ausstieg am Ask, Taker 0,06 % je Seite. Dient als Vergleich.
  - Liquidation wird geprüft: Höchstkurs im Trade ≥ Einstieg × (1 + 0,9 / Hebel).
- **Telegram:** Meldung bei jedem Short und Ausstieg (beide Konten) sowie ein Tagesbericht um 07:00 UTC,
  jeweils mit aktuellem Kontostand beider Paper-Konten und Zahl der offenen Shorts.

Geprüft: Der Live-Scanner findet dieselben Einzahlungen wie die Backtest-Daten (9/9, identische Mengen).

## Installation

```bash
git clone https://github.com/Youra82/kbot.git
cd kbot
chmod +x install.sh && ./install.sh
```

`secret.json` anlegen (wird nicht von Git getrackt):

```json
{
    "alchemy_api_key": "dein-alchemy-key",
    "telegram": { "bot_token": "...", "chat_id": "..." },
    "kbot": [ { "name": "kbot", "apiKey": "", "secret": "", "password": "" } ]
}
```

- **Alchemy** (kostenlos): https://www.alchemy.com. Der Free Tier reicht.
- **Bitget-Keys** sind für den Dry-Run nicht nötig, KBot nutzt nur öffentliche Kurse.
- Beim **ersten Start** baut KBot das Adressbuch aus 60 Tagen Sweeps auf. Das dauert einmalig ca. 20–40 min.

## Starten

```bash
cd ~/kbot && nohup /usr/bin/flock -n kbot.lock .venv/bin/python3 master_runner.py >> logs/stdout.log 2>&1 &
```

Stoppen: `pkill -f master_runner.py`. Nach `./update.sh` muss der Bot neu gestartet werden.

## Einstellungen (`settings.json` → `deposit_watch`)

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `min_usd` | 500000 | Mindestgröße der Einzahlung in $ |
| `hold_minutes` | 60 | Haltedauer des Shorts |
| `start_equity_usdt` | 100 | Paper-Startkapital je Konto |
| `leverage` | 5 | Hebel |
| `margin_fraction` | 0.3333 | Anteil des Kapitals als Margin je Trade (bis zu 3 gleichzeitig) |
| `limit_fill_minutes` | 2 | Zeitfenster, in dem eine Limit-Order gefüllt sein muss |
| `backfill_days` | 60 | Sweep-Historie für das Adressbuch beim ersten Start |
| `tokens` | 22 Coins | LINK UNI AAVE LDO ENA ONDO PENDLE CRV ETHFI PEPE SHIB FET COMP SNX GRT IMX SAND MANA APE ENS WLD 1INCH |

`mode`: `deposits` (Standard) oder `bridge` (alter Bridge-Ansatz, widerlegt, siehe unten).
Die Standardwerte entsprechen der präregistrierten Primärvariante. Werden sie geändert, gilt der Backtest nicht mehr.

## Dateien

| Datei | Inhalt |
|---|---|
| `logs/kbot.log` | Bot-Log |
| `logs/paper_shorts.csv` | jeder Paper-Trade (beide Konten), Einstieg, Ausstieg, Status, PnL, Kontostand |
| `logs/deposits.csv` | alle Einzahlungen ≥ 100k $ an Binance mit Signal-Status |
| `artifacts/state/` | Adressbuch, Scanner-Position, offene Positionen (übersteht Neustarts) |

## Tests

```bash
.venv/bin/python3 -m pytest -q tests/
```

15 Offline-Tests: Signalregel, Adressbuch-Lernen, Sweep- und Einzahlungs-Erkennung, Limit-Füllung,
verpasster Einstieg, Liquidation, Bridge-Scanner.

## Forschung (reproduzierbar)

| Ordner | Hypothese | Ergebnis |
|---|---|---|
| [`research/cex/`](research/cex/) | Wal-Einzahlung auf Binance → Coin fällt | **bestanden** (siehe oben) |
| [`research/`](research/) (`PREREG.md`) | Stablecoin-Bridge-Zufluss → Ziel-Coin steigt (ursprüngliche KBot-Idee) | widerlegt (0/27 Varianten) |
| [`research/`](research/) (`PREREG_MINTS.md`) | Neu gedruckte Stablecoins → BTC/ETH steigen | widerlegt |

Die ursprüngliche Bridge-Version hatte falsche Bridge-Adressen, eine tote News-API (CryptoPanic v1) und
eine Simulation ohne Ausstiege. Sie ist als `mode: bridge` nur noch als Archiv enthalten.

Daten neu erzeugen: `python research/cex/collect.py` (~2 h, Alchemy Free Tier), danach `python research/cex/test.py`.

---

### ⚠️ Disclaimer

Dieses Projekt dient ausschließlich zu Bildungs- und Forschungszwecken und ist keine Finanzberatung.
Backtests garantieren keine zukünftigen Ergebnisse. Trading mit gehebelten Krypto-Futures kann zum
Totalverlust führen.
