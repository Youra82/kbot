# kbot — Präregistrierung Bridge-Inflow-Test (2026-10-09, vor Sicht der Ergebnisse)

## Mechanismus (These des Bots)
Großes Stablecoin-Kapital, das von Ethereum auf Chain X gebrückt wird, ist Nachfrage
für das Ökosystem X → der native Token von X steigt danach überdurchschnittlich.

Gegenargument (a priori): Große Bridge-Transfers sind oft Market-Maker-/Arbitrage-
Rebalancing oder CEX-Hot-Wallet-Bewegungen ohne Richtungsinformation.

## Daten
- Ethereum → Bridge: USDC/USDT-Transfers ≥ 100k $ an CCTP v1/v2, USDT0 (OFT),
  Stargate USDC/USDT, Across, OP-/Base-Standard-Bridge, Arbitrum-Custom-Gateway,
  letzte 365 Tage. Ziel-Chain aus Receipt-Event (CCTP destinationDomain,
  LayerZero dstEid, Across destinationChainId).
- Kurse: Binance-USDT-M 1h.
- Nur sicher zugeordnete Chains → Token: Arbitrum→ARB, Optimism→OP, Base→ETH,
  Solana→SOL, Avalanche→AVAX, Polygon→POL, Aptos→APT, Sui→SUI, Sei→SEI,
  Sonic→S, Unichain→UNI, Linea→LINEA, World Chain→WLD, HyperEVM→HYPE,
  BSC→BNB, Berachain→BERA, Plasma→XPL. Unklare IDs werden nicht verwendet.

## Signal
F_c(h) = Summe der Zuflüsse zur Chain c in Stunde h.
Event: F_c(h) ≥ k × Mittelwert F_c der vorangehenden 30 Tage (ohne h) UND ≥ A $.
Einstieg: Open der Stunde h+1 (Bot erkennt Transfer in Sekunden; konservativ).
Ausstieg: nach H Stunden. Kosten: 0,12 % pro Round-Trip.
Pro Chain max. 1 Event je H Stunden (keine überlappenden Positionen).

## Primärhypothese H1
Excess-Return (Token minus BTC, gleiche Haltedauer) nach Event > 0.
Primärvariante (fix): k = 3, A = 1 Mio $, H = 24h, gepoolt über alle Chains.

## Bestehen
- IS = erste 8 Monate, OOS = letzte 4 Monate.
- IS: mittlerer Netto-Excess-Return > 0, t ≥ 2 (Events, nicht überlappend je Chain).
- OOS: gleiches Vorzeichen, t ≥ 1,5, ≥ 30 Events.
- Zusätzlich Rohrendite (ohne BTC-Abzug) > 0 im OOS.

## Sensitivität (nur berichtet, entscheidet nicht allein)
k ∈ {2, 3, 5}, A ∈ {0,3; 1; 3 Mio $}, H ∈ {4, 24, 72}. 27 Varianten →
bei Zufall erwartet ~1–2 „Treffer“ mit t ≥ 2; erst ein deutliches Übermaß zählt.
Gegenrichtung (Short nach Inflow) wird mitberichtet, ist aber keine neue Hypothese.

## Konsequenz
- H1 bestanden → Bot auf neue Datenquellen + Aggregat-Signal umbauen, Dry-Run.
- H1 nicht bestanden → Bridge-Inflow ist kein Handelssignal; Bot nur noch als
  Dry-Run-Datensammler/Monitor (Vorwärtstest), kein Live-Geld.
