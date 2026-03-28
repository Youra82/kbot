# KBot — Agentic Liquidity Pulse (ALP)

Trading-Bot der grosse Stablecoin-Zufluesse zu Ethereum-Bridges als Fruehsignal fuer Kursbewegungen nutzt.

## Strategie

Wenn ein Whale grosse Mengen USDC/USDT zu einer Ethereum-Bridge transferiert, bedeutet das: Kapital fliesst ins jeweilige Oekosystem. Der Bot erkennt dieses Signal und eroeffnet eine Long-Position auf dem entsprechenden Coin.

| Bridge | Signal | Trade |
|--------|--------|-------|
| Base   | USDC/USDT >= 500.000 $ | LONG ETH |
| Arbitrum | USDC/USDT >= 500.000 $ | LONG ARB |
| Optimism | USDC/USDT >= 300.000 $ | LONG OP |

Vor jedem Trade wird ein Sentiment-Check via CryptoPanic durchgefuehrt. Bei negativen News (Hack, Exploit) wird der Trade blockiert.

## Installation

```bash
git clone https://github.com/Youra82/kbot.git
cd kbot
chmod +x install.sh
./install.sh
```

## Konfiguration

`secret.json` anlegen (wird nicht von Git getrackt):

```json
{
    "alchemy_api_key": "dein-alchemy-key",
    "cryptopanic_api_key": "dein-cryptopanic-key",
    "telegram": {
        "bot_token": "...",
        "chat_id": "..."
    },
    "kbot": [
        {
            "name": "kbot",
            "apiKey": "bitget-api-key",
            "secret": "bitget-secret",
            "password": "bitget-passphrase"
        }
    ]
}
```

API Keys (beide kostenlos):
- **Alchemy**: https://www.alchemy.com — Free Tier reicht aus
- **CryptoPanic**: https://cryptopanic.com/developers/api

## Betrieb

```bash
# Simulation starten (Standard, kein echtes Geld)
cd /home/ubuntu/kbot && .venv/bin/python3 master_runner.py

# Fuer Live-Modus: simulation_mode auf false setzen in settings.json
```

## Logs

```bash
# Bot-Log
tail -f logs/kbot.log

# Trade-Log (CSV)
tail -f logs/trades.csv
```

---

## Coin & Timeframe Empfehlungen

KBot ist ein **Stablecoin-Bridge-Inflow-Monitor** — er überwacht in Echtzeit große USDC/USDT-Transfers auf Ethereum Layer-2-Bridges (Base, Arbitrum, Optimism) und interpretiert massive Kapitalzuflüsse als Kaufsignal. Das ist **kein Chart-basierter Bot** — er tradet ausschließlich die durch Bridge-Aktivität implizierte Nachfrage.

### Funktionsprinzip (kein Timeframe-basierter Bot)

| Komponente | Funktion | Schwellwert |
|---|---|---|
| **Base Bridge (USDC/USDT)** | Kapitalzufluss → LONG ETH | ≥ $500.000 |
| **Arbitrum Bridge (USDC/USDT)** | Kapitalzufluss → LONG ARB | ≥ $500.000 |
| **Optimism Bridge (USDC/USDT)** | Kapitalzufluss → LONG OP | ≥ $300.000 |
| **CryptoPanic Sentiment** | Blockiert bei Hack/Exploit-News | Negativ = kein Trade |

> KBot ist **kein Candlestick-Bot** — Timeframe-Auswahl entfällt. Er reagiert auf Echtzeit-Bridge-Events, nicht auf periodische Kerzen.

### Coin-Eignung (fest vorgegeben durch Bridge-Logik)

| Coin | Bridge | Signal-Quelle | Bewertung |
|---|---|---|---|
| **ETH** | Base + Arbitrum | Größte Stablecoin-Transfers aller L2s | ✅✅ Primär-Coin |
| **ARB** | Arbitrum | Natives L2-Token, direkt bridge-korreliert | ✅ Gut |
| **OP** | Optimism | Niedrigerer Schwellwert ($300k) — öfter getriggert | ✅ Gut |
| Andere Coins | — | Nicht unterstützt — keine Bridge-Inflow-Logik | ❌ |

### Stärken & Einschränkungen

| Aspekt | Bewertung |
|---|---|
| **Signaltyp** | On-Chain / Real-time (nicht technisch-analytisch) |
| **Marktphase** | Funktioniert am besten in frühen Bull-Phasen wenn Kapital auf L2s strömt |
| **Risiko** | Bridge-Inflows können auch Arbitrage sein — Sentiment-Filter (CryptoPanic) essentiell |
| **Frequenz** | Selten (hohe Schwellwerte) — wenige aber qualitativ hochwertige Signale |
| **Nicht geeignet für** | Bärenmärkte, stabile Seitwärtsphasen (kaum Bridge-Inflows) |

> **Hinweis:** KBot ergänzt andere technische Bots sinnvoll. Ein ETH Bridge-Inflow-Signal gleichzeitig mit einem FiBot/StBot Fibonacci-Bounce auf ETH 4h ist ein besonders starkes Confluence-Signal.


## Update

```bash
cd /home/ubuntu/kbot && ./update.sh
```
