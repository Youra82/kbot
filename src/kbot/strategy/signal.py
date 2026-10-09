"""
signal.py — Bridge-Inflow-Signal. EINE Funktion fuer Live-Bot und research/event_study.py.

F(h) = Summe aller Stablecoin-Bridge-Zufluesse zur Chain in Stunde h.
Event in Stunde h: F(h) >= k * Mittel(F der 30 Tage davor) UND F(h) >= A.
Sperre: nach einem Event H Stunden kein neues Event (keine Ueberlappung).
"""
import pandas as pd

BASELINE_HOURS = 24 * 30
MIN_BASELINE_HOURS = 24 * 14


def hourly_flows(flows: pd.DataFrame, token: str, start, end) -> pd.Series:
    """flows: Spalten ts (UTC), token, usd -> lueckenlose Stundenreihe [start, end]."""
    g = flows[flows['token'] == token]
    idx = pd.date_range(pd.Timestamp(start).floor('h'), pd.Timestamp(end).floor('h'), freq='h', tz='UTC')
    return g.groupby(g['ts'].dt.floor('h'))['usd'].sum().reindex(idx, fill_value=0.0)


def flow_events(F: pd.Series, k: float, A: float, H: int) -> list:
    """Liste der Event-Stunden (Stundenbeginn). Einstieg = Open der Folgestunde."""
    base = F.shift(1).rolling(BASELINE_HOURS, min_periods=MIN_BASELINE_HOURS).mean()
    cand = F[(F >= k * base) & (F >= A)].index
    ev, last = [], None
    for t in cand:
        if last is None or t >= last + pd.Timedelta(hours=H):
            ev.append(t)
            last = t
    return ev


def baseline_at(F: pd.Series, hour) -> float:
    """Baseline-Mittel, das flow_events fuer `hour` verwendet (fuer Logs/Telegram)."""
    prev = F[F.index < hour].tail(BASELINE_HOURS)
    return float(prev.mean()) if len(prev) >= MIN_BASELINE_HOURS else float('nan')
