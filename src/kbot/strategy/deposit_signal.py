"""
deposit_signal.py — Signalregel Wal-Einzahlung -> Short. EINE Regel fuer Live und research/cex/test.py.

Praeregistriert (research/cex/PRAEREGISTRIERUNG.md, primaer bestanden 2026-10-09):
  Einzahlung >= A USD an eine BEREITS BEKANNTE Binance-Einzahladresse
  -> Short, Einstieg Minute floor(Blockzeit)+1, Haltedauer H Minuten,
  je Token keine ueberlappenden Trades.
"""
import pandas as pd


def entry_minute(block_ts) -> pd.Timestamp:
    """Einstiegsminute wie im Backtest: Schluss der Minute floor(Blockzeit) + 1."""
    return pd.Timestamp(block_ts).floor('min') + pd.Timedelta(minutes=1)


class DepositRule:
    def __init__(self, min_usd: float = 500_000, hold_minutes: int = 60):
        self.min_usd = float(min_usd)
        self.hold = pd.Timedelta(minutes=int(hold_minutes))
        self.last_entry = {}          # token -> letzte Einstiegsminute

    def accept(self, token: str, block_ts, usd: float, known_since=None) -> bool:
        """True = handeln. Merkt sich die Einstiegszeit (Sperre H je Token)."""
        if usd is None or usd < self.min_usd:
            return False
        ts = pd.Timestamp(block_ts)
        if known_since is None or not (ts > pd.Timestamp(known_since)):
            return False              # live-gleich: Adresse muss vorher schon bekannt sein
        t0 = entry_minute(ts)
        last = self.last_entry.get(token)
        if last is not None and t0 < last + self.hold:
            return False
        self.last_entry[token] = t0
        return True
