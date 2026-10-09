# Präregistrierung: Wal-Einzahlungen auf Binance → Verkaufsdruck (2026-10-09, vor Sicht von Kursen/Ergebnissen)

## Mechanismus
Wer einen Altcoin in großer Menge auf Binance einzahlt, will ihn meist verkaufen (oder als
Sicherheit für Shorts nutzen). Die Einzahlung ist on-chain sichtbar, bevor Binance sie
gutschreibt (Bestätigungen) → Vorlauf. Bitget folgt Binance (Lead-Lag-Test 2026-10-09).
Gegenargument: Market Maker verschieben Inventar ohne Richtungsabsicht; Verkauf über TWAP
verteilt sich über Stunden; Profis lesen dieselben Daten.

## Daten (Ethereum, Alchemy)
- Binance-Sammel-Wallet: Binance 14 `0x28c6…1d60` (geprüft: Einzahladressen leiten 100 % dorthin,
  Median ~5 min nach Einzahlung).
- Tokens (ERC-20, Binance-USDT-M-Perp vorhanden): LINK UNI AAVE LDO ENA ONDO PENDLE CRV ETHFI PEPE SHIB
  FET COMP SNX GRT IMX SAND MANA APE ENS WLD 1INCH.
- Zeitraum 2025-10-09 .. 2026-10-09. Ereignisse erst ab 2025-11-09 (1 Monat Anlaufzeit für Adress-Lernen).
  IS < 2026-06-09, OOS ≥ 2026-06-09.
- Einzahladresse = Absender eines Transfers an Binance 14. **Live-gleich:** eine Adresse gilt erst ab
  ihrem ersten beobachteten Sweep als bekannt; nur Einzahlungen an bereits bekannte Adressen zählen.
- Einzahlung = Transfer des Tokens an eine bekannte Einzahladresse; USD = Menge × Binance-1m-Schluss.
- Kurse: Binance USDT-M 1m (Proxy für Bitget, das < 1 min nachläuft).

## Signal und Trade (primär)
Einzahlung ≥ 500k $ → Short. Einstieg = Schluss der Minute floor(Blockzeit) + 1 (≈ 60–120 s).
Ausstieg nach H = 60 min. Kosten 0,12 % Rundreise. Je Token keine überlappenden Trades (Sperre H).
Basis = mittlere Short-Rendite desselben Tokens über H zu allen Minuten derselben Periode (Drift-Kontrolle).

## Bestehen
IS: (Event − Basis) > 0, t ≥ 2. OOS: (Event − Basis) > 0, t ≥ 1,5, ≥ 30 Ereignisse,
und Netto-Short-Rendite (nach Kosten) > 0.

## Sensitivität (berichtet, entscheidet nicht)
A ∈ {250k, 500k, 2M $} × H ∈ {15, 60, 240 min} (9 Varianten).
Sekundär: Signal zur Sweep-Zeit statt Einzahlung (alle Adressen, auch neue).
Beschreibend: Absender ist Börsen-Hot-Wallet vs. sonstige; je Token; Größe.

## Konsequenz
Bestanden → Live-Wächter (Dry-Run, Bitget-Short), Vorwärtstest. Nicht bestanden → kein
Einzahlungs-Edge auf Ethereum-Alts; ggf. Stablecoin-Einzahlungen (H2) separat präregistrieren.
