"""
bridge_monitor.py — Ethereum -> L2/Alt-L1 Stablecoin-Bridge-Fluesse (Alchemy HTTP)

Live-Scan:
  - eth_getLogs in Abschnitten von max. 10 Bloecken (Alchemy Free Tier Limit),
    gefiltert auf Transfer(to = Bridge-Adresse) fuer USDC + USDT.
  - Cursor rueckt NUR nach erfolgreichem Abschnitt vor (frueher: Bloecke still verloren).
  - Ziel-Chain via Receipt (bridge_registry.decode_dest).

Backfill (Baseline fuer das Signal, auch von research/ genutzt):
  - alchemy_getAssetTransfers je Bridge-Adresse + Receipts (gebuendelt).
"""

import logging
import time
from datetime import datetime, timezone, timedelta

import requests

from kbot.utils.bridge_registry import (
    BRIDGES, SRC_BY_ADDR, STABLECOINS, TRANSFER_TOPIC, FIXED_DEST, decode_dest, token_of,
)

logger = logging.getLogger('kbot')

MAX_LOG_RANGE = 10        # Bloecke inkl. from/to (Free Tier)
BLOCKS_PER_HOUR = 300     # ~12 s Blockzeit


class RpcError(RuntimeError):
    pass


class AlchemyClient:
    def __init__(self, api_key: str):
        self.url = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"

    def call(self, method: str, params: list, retries: int = 4):
        last = None
        for i in range(retries):
            try:
                j = requests.post(self.url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                                  timeout=60).json()
                if 'error' in j:
                    raise RpcError(f"{method}: {j['error']}")
                return j['result']
            except Exception as e:
                last = e
                time.sleep(2 * (i + 1))
        raise RpcError(f"{method} fehlgeschlagen: {last}")

    def receipts(self, tx_hashes: list, batch: int = 10) -> dict:
        out = {}
        for i in range(0, len(tx_hashes), batch):
            chunk = tx_hashes[i:i + batch]
            body = [{"jsonrpc": "2.0", "id": j, "method": "eth_getTransactionReceipt", "params": [h]}
                    for j, h in enumerate(chunk)]
            for attempt in range(6):
                try:
                    resp = requests.post(self.url, json=body, timeout=120).json()
                    if isinstance(resp, dict) or any('error' in x for x in resp):
                        raise RpcError(str(resp)[:200])
                    break
                except Exception as e:
                    logger.debug(f"Receipt-Batch Retry {attempt + 1}: {e}")
                    time.sleep(3 * (attempt + 1))
            else:
                raise RpcError("Receipt-Batch endgueltig fehlgeschlagen")
            for x in resp:
                out[chunk[x['id']]] = x['result'] or {}
            time.sleep(0.5)
        return out


def _pad(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:].lower()


def resolve_flows(client: AlchemyClient, transfers: list) -> list:
    """transfers: [{tx, src, usd, ts, block}] -> gleiche dicts + dest + token (Receipt nur wo noetig)."""
    need = sorted({t['tx'] for t in transfers if t['src'] not in FIXED_DEST})
    rec = client.receipts(need) if need else {}
    out = []
    for t in transfers:
        dest = t['src'] if t['src'] in FIXED_DEST else decode_dest(t['src'], rec.get(t['tx']))
        out.append({**t, 'dest': dest, 'token': token_of(t['src'], dest)})
    return out


class BridgeMonitor:
    def __init__(self, alchemy_api_key: str, settings: dict, cursor: int = None):
        self.client = AlchemyClient(alchemy_api_key)
        sig = settings.get('signal', {})
        self.min_transfer = float(sig.get('min_transfer_usd', 100_000))
        self.max_catchup = int(settings.get('max_catchup_blocks', 2 * BLOCKS_PER_HOUR))
        self.cursor = cursor          # letzter vollstaendig gescannter Block
        self.lost_blocks = 0

    def poll(self) -> list:
        """Scannt alle neuen Bloecke. Gibt aufgeloeste Fluesse >= min_transfer zurueck."""
        latest = int(self.client.call("eth_blockNumber", []), 16)
        if self.cursor is None:
            self.cursor = latest - 1
        if latest - self.cursor > self.max_catchup:
            skipped = latest - self.max_catchup - self.cursor
            self.lost_blocks += skipped
            logger.warning(f"Scanner {latest - self.cursor} Bloecke im Rueckstand — ueberspringe {skipped} "
                           f"(gesamt verloren: {self.lost_blocks}).")
            self.cursor = latest - self.max_catchup

        raw = []
        topics = [TRANSFER_TOPIC, None, [_pad(a) for a in BRIDGES.values()]]
        while self.cursor < latest:
            frm = self.cursor + 1
            to = min(frm + MAX_LOG_RANGE - 1, latest)
            logs = self.client.call("eth_getLogs", [{
                "fromBlock": hex(frm), "toBlock": hex(to),
                "address": list(STABLECOINS.values()), "topics": topics}])
            for lg in logs:
                usd = int(lg['data'], 16) / 1e6          # USDC + USDT: 6 Dezimalen
                if usd < self.min_transfer:
                    continue
                to_addr = "0x" + lg['topics'][2][-40:].lower()
                raw.append({'tx': lg['transactionHash'], 'src': SRC_BY_ADDR[to_addr], 'usd': usd,
                            'block': int(lg['blockNumber'], 16),
                            'ts': datetime.now(timezone.utc).isoformat()})
            self.cursor = to       # erst NACH Erfolg vorruecken
        return resolve_flows(self.client, raw) if raw else []


def backfill(client: AlchemyClient, days: int, min_usd: float = 100_000, log=logger) -> list:
    """Historische Fluesse der letzten `days` Tage (gleiche Aufloesung wie live)."""
    latest = int(client.call("eth_blockNumber", []), 16)
    frm = latest - int(days * 24 * BLOCKS_PER_HOUR)
    raw = []
    for name, addr in BRIDGES.items():
        pk, pages = None, 0
        while True:
            p = {"fromBlock": hex(frm), "toBlock": hex(latest), "toAddress": addr,
                 "contractAddresses": list(STABLECOINS.values()), "category": ["erc20"],
                 "withMetadata": True, "maxCount": "0x3e8", "excludeZeroValue": True}
            if pk:
                p["pageKey"] = pk
            res = client.call("alchemy_getAssetTransfers", [p], retries=6)
            for t in res['transfers']:
                v = float(t.get('value') or 0)
                if v >= min_usd:
                    raw.append({'tx': t['hash'], 'src': name, 'usd': v, 'block': int(t['blockNum'], 16),
                                'ts': t['metadata']['blockTimestamp']})
            pk = res.get('pageKey'); pages += 1
            if not pk:
                break
        log.info(f"Backfill {name}: {pages} Seiten")
    log.info(f"Backfill: {len(raw)} Transfers >= {min_usd:,.0f} $, loese Ziel-Chains auf...")
    return resolve_flows(client, raw), latest
