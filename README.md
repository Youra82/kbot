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

## Update

```bash
cd /home/ubuntu/kbot && ./update.sh
```
