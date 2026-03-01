"""
sentiment.py — News & Sentiment Safety Check

Prüft via CryptoPanic API ob ein Bridge-Signal durch negative
Nachrichten (Hacks, Exploits) konterkariert wird.
Schützt den Bot davor, in einen Hack hineinzukaufen.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CRYPTOPANIC_URL = "https://cryptopanic.com/api/v1/posts/"


class SentimentGuard:
    """
    Safety-Check: Blockiert Trades wenn negative News vorhanden sind.
    """

    def __init__(self, api_key: str, settings: dict):
        self.api_key = api_key
        self.enabled = settings.get("enabled", True)
        self.block_keywords = [kw.lower() for kw in settings.get("block_keywords", [
            "hack", "exploit", "drain", "vulnerability", "attack", "rugpull", "stolen", "breach"
        ])]
        self.require_positive = settings.get("require_positive", False)

    def _fetch_news(self, query: str = "") -> list:
        """Aktuelle Krypto-News von CryptoPanic abrufen."""
        if not self.api_key:
            logger.warning("Kein CryptoPanic API-Key — Sentiment-Check übersprungen.")
            return []

        params = {
            "auth_token": self.api_key,
            "kind": "news",
            "filter": "hot",
        }
        if query:
            params["currencies"] = query

        try:
            resp = requests.get(CRYPTOPANIC_URL, params=params, timeout=8)
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            logger.error(f"CryptoPanic Fehler: {e}")
            return []

    def is_safe_to_trade(self, bridge_name: str, symbol: str) -> bool:
        """
        Gibt True zurück wenn kein Hack/Exploit in den News erkannt wurde.

        bridge_name: z.B. "BASE", "ARBITRUM"
        symbol: z.B. "ETH/USDT:USDT"
        """
        if not self.enabled:
            logger.info("Sentiment-Check deaktiviert — Trade erlaubt.")
            return True

        # Suchbegriff aus Symbol ableiten (z.B. "ETH" aus "ETH/USDT:USDT")
        coin = symbol.split("/")[0] if "/" in symbol else symbol

        news = self._fetch_news(query=coin)

        if not news:
            # Kein API-Key oder keine News → vorsichtig erlauben
            logger.info(f"Sentiment: Keine News gefunden → Trade erlaubt.")
            return True

        headlines = [post.get("title", "").lower() for post in news]

        # Negativ-Check: Blockieren bei Hack/Exploit-Keywords
        for headline in headlines:
            for keyword in self.block_keywords:
                if keyword in headline and (bridge_name.lower() in headline or coin.lower() in headline):
                    logger.warning(
                        f"🛑 SENTIMENT BLOCKIERT: '{keyword}' in News gefunden → Trade abgebrochen."
                    )
                    logger.warning(f"   Schlagzeile: {headline[:100]}")
                    return False

        logger.info(f"✅ Sentiment OK: Keine negativen Meldungen für {bridge_name}/{coin}.")
        return True
