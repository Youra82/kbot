"""
bridge_monitor.py — Ethereum On-Chain Bridge Flow Detection

Überwacht große Stablecoin-Transfers (USDC/USDT) zu bekannten
Bridge-Contracts auf Ethereum. Wenn ein Whale Kapital über eine
Bridge bewegt, ist das ein Frühwarnsignal für Kursbewegungen
auf der Ziel-Chain.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ERC-20 Transfer Event Topic (keccak256 von "Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class BridgeMonitor:
    """
    Überwacht Ethereum-Bridges auf große Stablecoin-Zuflüsse via
    Alchemy HTTP-API (Polling, kein WebSocket nötig).
    """

    def __init__(self, alchemy_api_key: str, settings: dict):
        self.api_key = alchemy_api_key
        self.rpc_url = f"https://eth-mainnet.g.alchemy.com/v2/{alchemy_api_key}"
        self.bridges = settings.get("bridges", {})
        self.stablecoins = settings.get("stablecoins", {})
        self.lookback_blocks = settings.get("lookback_blocks", 10)
        self._last_block = None

    def _rpc_call(self, method: str, params: list) -> Optional[dict]:
        """JSON-RPC Call an Alchemy."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        try:
            resp = requests.post(self.rpc_url, json=payload, timeout=10)
            data = resp.json()
            return data.get("result")
        except Exception as e:
            logger.error(f"Alchemy RPC Fehler: {e}")
            return None

    def get_latest_block(self) -> Optional[int]:
        """Aktuellen Block-Nummer abrufen."""
        result = self._rpc_call("eth_blockNumber", [])
        if result:
            return int(result, 16)
        return None

    def get_transfer_logs(self, token_address: str, from_block: int, to_block: int) -> list:
        """ERC-20 Transfer-Events für einen Token in einem Block-Bereich abrufen."""
        params = [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "address": token_address,
            "topics": [TRANSFER_TOPIC]
        }]
        result = self._rpc_call("eth_getLogs", params)
        return result or []

    def decode_transfer_log(self, log: dict, decimals: int = 6) -> dict:
        """Transfer-Log dekodieren → from, to, value."""
        topics = log.get("topics", [])
        to_addr = "0x" + topics[2][-40:] if len(topics) > 2 else None
        from_addr = "0x" + topics[1][-40:] if len(topics) > 1 else None
        value_hex = log.get("data", "0x0")
        value = int(value_hex, 16) / (10 ** decimals)
        return {
            "from": from_addr,
            "to": to_addr,
            "value_usd": value,
            "tx_hash": log.get("transactionHash"),
            "block": int(log.get("blockNumber", "0x0"), 16)
        }

    def scan_bridge_flows(self) -> list:
        """
        Scannt die letzten N Blöcke auf große Stablecoin-Transfers zu Bridge-Adressen.
        Gibt eine Liste von Signalen zurück: [{bridge_name, symbol, inflow_usd, tx_hash}]
        """
        latest = self.get_latest_block()
        if not latest:
            logger.warning("Konnte aktuellen Block nicht abrufen.")
            return []

        from_block = (self._last_block + 1) if self._last_block else (latest - self.lookback_blocks)
        to_block = latest

        if from_block > to_block:
            return []

        self._last_block = to_block

        signals = []
        bridge_addresses_lower = {addr.lower(): info for addr, info in self.bridges.items()}

        for coin_name, token_address in self.stablecoins.items():
            logs = self.get_transfer_logs(token_address, from_block, to_block)

            for log in logs:
                transfer = self.decode_transfer_log(log, decimals=6)
                to_addr = (transfer["to"] or "").lower()

                if to_addr in bridge_addresses_lower:
                    bridge_info = bridge_addresses_lower[to_addr]
                    min_inflow = bridge_info.get("min_inflow_usdt", 500000)

                    if transfer["value_usd"] >= min_inflow:
                        signal = {
                            "bridge_name": bridge_info["name"],
                            "symbol": bridge_info["symbol"],
                            "inflow_usd": transfer["value_usd"],
                            "stablecoin": coin_name,
                            "tx_hash": transfer["tx_hash"],
                            "block": transfer["block"],
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        signals.append(signal)
                        logger.info(
                            f"🚨 BRIDGE SIGNAL: {transfer['value_usd']:,.0f} {coin_name} "
                            f"→ {bridge_info['name']} | TX: {transfer['tx_hash']}"
                        )

        return signals
