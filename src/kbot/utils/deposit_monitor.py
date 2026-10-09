"""
deposit_monitor.py — Live-Erkennung von Einzahlungen auf Binance (Ethereum, Alchemy Free Tier).

Pro Poll: eth_getLogs (max. 10 Bloecke je Abfrage) aller Transfer-Events der ueberwachten Tokens.
  - Transfer an Binance 14            -> Sweep: Absender ist Einzahladresse (Adressbuch lernt).
  - Transfer an bekannte Einzahladresse -> Einzahlung (Kandidat fuer das Signal).
Cursor rueckt nur nach erfolgreichem Abschnitt vor (keine still verlorenen Bloecke).
"""
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta

from kbot.utils.bridge_monitor import AlchemyClient, RpcError, MAX_LOG_RANGE, BLOCKS_PER_HOUR
from kbot.utils.bridge_registry import TRANSFER_TOPIC
from kbot.utils.deposit_registry import BINANCE_HOT, TOKENS, TOKEN_BY_CONTRACT, sender_type

logger = logging.getLogger('kbot')


class AddressBook:
    """Binance-Einzahladressen -> Zeitpunkt des ersten beobachteten Sweeps (ISO, UTC)."""

    def __init__(self, path: str):
        self.path = path
        self.known = {}
        try:
            with open(path) as f:
                self.known = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    def __len__(self):
        return len(self.known)

    def known_since(self, addr: str):
        return self.known.get(addr.lower())

    def learn(self, addr: str, ts: str) -> bool:
        addr = addr.lower()
        if addr in self.known and self.known[addr] <= ts:
            return False
        self.known[addr] = ts
        return True

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.known, f)
        os.replace(tmp, self.path)

    def backfill(self, client: AlchemyClient, days: int, log=logger):
        """Sweeps der letzten `days` Tage an Binance 14 -> Adressbuch (einmalig beim ersten Start)."""
        latest = int(client.call("eth_blockNumber", []), 16)
        frm = latest - days * 24 * BLOCKS_PER_HOUR
        for tok, contract in TOKENS.items():
            pk, n = None, 0
            while True:
                q = {"fromBlock": hex(frm), "toBlock": hex(latest), "toAddress": BINANCE_HOT,
                     "contractAddresses": [contract], "category": ["erc20"], "withMetadata": True,
                     "maxCount": "0x3e8", "excludeZeroValue": True}
                if pk:
                    q["pageKey"] = pk
                r = client.call("alchemy_getAssetTransfers", [q], retries=8)
                for t in r['transfers']:
                    self.learn(t['from'], t['metadata']['blockTimestamp'])
                    n += 1
                pk = r.get('pageKey')
                if not pk:
                    break
            log.info(f"Adressbuch {tok}: {n} Sweeps | gesamt {len(self)} Adressen")
        self.save()
        return latest


def _block_ts(client: AlchemyClient, block: int, cache: dict) -> str:
    if block not in cache:
        b = client.call("eth_getBlockByNumber", [hex(block), False])
        cache[block] = datetime.fromtimestamp(int(b['timestamp'], 16), tz=timezone.utc).isoformat()
    return cache[block]


class DepositScanner:
    def __init__(self, client: AlchemyClient, book: AddressBook, cursor: int = None, max_catchup: int = 600):
        self.client = client
        self.book = book
        self.cursor = cursor
        self.max_catchup = max_catchup
        self.decimals = {}
        self.lost_blocks = 0

    def _decimals(self, contract: str) -> int:
        if contract not in self.decimals:
            r = self.client.call("eth_call", [{"to": contract, "data": "0x313ce567"}, "latest"])
            self.decimals[contract] = int(r, 16)
        return self.decimals[contract]

    def classify(self, logs: list, ts_of) -> list:
        """Logs -> Liste von Einzahlungen. Sweeps werden ins Adressbuch gelernt (Reihenfolge wie on-chain)."""
        out = []
        for lg in sorted(logs, key=lambda x: (int(x['blockNumber'], 16), int(x.get('logIndex', '0x0'), 16))):
            if len(lg.get('topics', [])) < 3:
                continue
            contract = lg['address'].lower()
            tok = TOKEN_BY_CONTRACT.get(contract)
            if tok is None:
                continue
            frm = "0x" + lg['topics'][1][-40:].lower()
            to = "0x" + lg['topics'][2][-40:].lower()
            block = int(lg['blockNumber'], 16)
            if to == BINANCE_HOT:
                self.book.learn(frm, ts_of(block))
                continue
            since = self.book.known_since(to)
            if since is None:
                continue
            amount = int(lg['data'], 16) / 10 ** self._decimals(contract) if lg['data'] not in ('0x', '') else 0.0
            out.append({'token': tok, 'amount': amount, 'dep_addr': to, 'sender': frm,
                        'sender_type': sender_type(frm), 'block': block, 'ts': ts_of(block),
                        'known_since': since, 'tx': lg['transactionHash']})
        return out

    def poll(self) -> list:
        latest = int(self.client.call("eth_blockNumber", []), 16)
        if self.cursor is None:
            self.cursor = latest - 1
        if latest - self.cursor > self.max_catchup:
            skipped = latest - self.max_catchup - self.cursor
            self.lost_blocks += skipped
            logger.warning(f"Scanner {latest - self.cursor} Bloecke im Rueckstand — ueberspringe {skipped}.")
            self.cursor = latest - self.max_catchup
        cache, found = {}, []
        contracts = list(TOKENS.values())
        while self.cursor < latest:
            frm = self.cursor + 1
            to = min(frm + MAX_LOG_RANGE - 1, latest)
            logs = self.client.call("eth_getLogs", [{"fromBlock": hex(frm), "toBlock": hex(to),
                                                     "address": contracts, "topics": [TRANSFER_TOPIC]}])
            found += self.classify(logs, lambda b: _block_ts(self.client, b, cache))
            self.cursor = to
        if found or cache:
            self.book.save()
        return found
