# kbot v2 — Präregistrierung Stablecoin-Neuemission (2026-10-09, vor Sicht der Daten)

## Mechanismus
Tether/Circle geben neue Stablecoins nur gegen eingezahlte Fiat-Dollar aus (meist
OTC-Desks, Market Maker, Institutionelle). Neuemission = frisches Kapital mit
Kaufabsicht, im Gegensatz zum Bridging (Umschichtung, Nullsumme — v1 widerlegt).
Gegenargument: Emission folgt oft steigenden Kursen (Nachfrage endogen) und
Market Maker parken Liquidität ohne Kaufabsicht.

## H-M1 (täglich, DefiLlama, gesamte Stablecoin-Menge aller Chains, 2020–heute)
Signal Tag d: ΔSupply(d) ≥ 2 × Standardabweichung der Δ der 90 Tage davor
(und Δ > 0). Long BTC Close d → Close d+H, H ∈ {3, 7} Tage (primär H = 7).
Gemessen gegen unbedingte BTC-Rendite derselben Periode (Drift-Kontrolle).
IS = bis 2023-12-31, OOS = ab 2024-01-01.
Bestehen: Differenz > 0 mit t ≥ 2 IS UND gleiches Vorzeichen t ≥ 1,5 OOS,
≥ 20 nicht überlappende Events OOS.

## H-M2 (stündlich, Ethereum, 12 Monate)
Emission = USDC-Mint (Transfer von 0x0) + USDT-Auszahlung aus Tether Treasury
(0x5754…b949), Summe je Stunde. Event: ≥ 50 Mio $ in Stunde h.
Long BTC und ETH Open h+1 → H = 24 h (primär), 72 h. Gegen Zufallsstunden.
IS erste 8 Monate, OOS letzte 4. Gleiches Bestehenskriterium.

## Konsequenz
Besteht keine → kein Stablecoin-Flow-Edge; kbot bleibt Archiv/Monitor.
Besteht eine → Signal in kbot einbauen, Dry-Run als Vorwärtstest.

## Ergebnis (2026-10-09) — NICHT BESTANDEN
- H-M1 (DefiLlama täglich 2019–2026), primär k=2/H=7d: Diff vs Basis IS +2,28 % (t 1,30),
  OOS +0,81 % (t 0,78). Größte Emissionen (k=3) ≈ 0 — gegen den Mechanismus.
- H-M2 (Ethereum stündlich), primär 50M/24h: BTC IS −0,14 % (t −0,8), OOS +0,10 % (t 0,5).
  Messfehler erkannt: 1,18 Mio USDC-"Mints" sind überwiegend CCTP-Rückflüsse.
- Nachtrag (nicht präregistriert): nur Circle-Primäremission 0x55fe…44b8, brutto/netto/24h-netto,
  36 Varianten: keine besteht; größte Brutto-Mints IS signifikant NEGATIV (t −3), OOS positiv → Vorzeichen kippt.
