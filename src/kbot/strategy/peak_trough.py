"""Peak/Trough Reversal Strategy (Pullback / Reversal POC)

This module implements a simple reversal strategy that detects local peaks and
troughs over a configurable lookback period and places reversal trades when a
pullback/reversal candle appears.

Interface:
- generate_signal(ohlcv: list[tuple], config: dict) -> dict
  ohlcv is list of [timestamp, open, high, low, close, volume]
  returns None or a dict with keys: signal ('long' or 'short'), entry, stop, tp

This is a POC implementation (no exchange code) and is designed to be testable
and to integrate with the existing backtest/optimizer pipeline later.
"""
from __future__ import annotations
from typing import List, Tuple, Optional, Dict
import math

OHLCV = List[Tuple[int, float, float, float, float, float]]


def is_peak(ohlcv: OHLCV, idx: int, n: int) -> bool:
    """Return True if ohlcv[idx] high is greater than highs in window +/- n"""
    if idx - n < 0 or idx + n >= len(ohlcv):
        return False
    h = ohlcv[idx][2]
    for i in range(idx-n, idx+n+1):
        if i == idx:
            continue
        if ohlcv[i][2] >= h:
            return False
    return True


def is_trough(ohlcv: OHLCV, idx: int, n: int) -> bool:
    if idx - n < 0 or idx + n >= len(ohlcv):
        return False
    l = ohlcv[idx][3]
    for i in range(idx-n, idx+n+1):
        if i == idx:
            continue
        if ohlcv[i][3] <= l:
            return False
    return True


def atr(ohlcv: OHLCV, period: int=14) -> float:
    trs = []
    for i in range(1, len(ohlcv)):
        high = ohlcv[i][2]
        low = ohlcv[i][3]
        prev_close = ohlcv[i-1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs:
        return 0.0
    period = min(period, len(trs))
    return sum(trs[-period:]) / period


def generate_signal(ohlcv: OHLCV, config: Dict) -> Optional[Dict]:
    """Generate a single signal based on the most recent bars.

    Strategy logic (reversal/pullback):
    - Detect last peak or trough within lookback scan window.
    - If last significant point is a peak and latest close shows a bearish
      reversal candle (e.g., close < previous close by threshold), signal SHORT.
    - If last point is a trough and latest close shows bullish reversal, signal LONG.

    Returns a dict with signal details or None.
    """
    if len(ohlcv) < 5:
        return None
    n = int(config.get('lookback_n', 5))
    recent_idx = len(ohlcv) - 2  # use the candle before the last closed candle
    # scan for last peak/trough within last 3*n bars
    scan_from = max(1, len(ohlcv) - 3*n - 1)
    last_point = None
    last_idx = None
    for i in range(scan_from, len(ohlcv)-1):
        if is_peak(ohlcv, i, n):
            last_point = 'peak'
            last_idx = i
        elif is_trough(ohlcv, i, n):
            last_point = 'trough'
            last_idx = i
    if last_point is None:
        return None
    # determine reversal condition on latest candle
    prev_close = ohlcv[-2][4]
    last_close = ohlcv[-1][4]
    close_diff_pct = (last_close - prev_close) / (prev_close + 1e-9) * 100
    threshold_pct = float(config.get('reversal_threshold_pct', 0.2))

    if last_point == 'peak' and close_diff_pct < -threshold_pct:
        # short signal
        entry = last_close
        atr_val = atr(ohlcv, int(config.get('atr_period', 14)))
        stop = entry + atr_val * float(config.get('atr_mult', 1.5))
        tp = entry - (stop - entry) * float(config.get('risk_reward_ratio', 2.0))
        return {'signal':'short','entry':entry,'stop':stop,'tp':tp,'meta':{'last_idx':last_idx,'type':'peak','close_diff_pct':close_diff_pct}}

    if last_point == 'trough' and close_diff_pct > threshold_pct:
        entry = last_close
        atr_val = atr(ohlcv, int(config.get('atr_period', 14)))
        stop = entry - atr_val * float(config.get('atr_mult', 1.5))
        tp = entry + (entry - stop) * float(config.get('risk_reward_ratio', 2.0))
        return {'signal':'long','entry':entry,'stop':stop,'tp':tp,'meta':{'last_idx':last_idx,'type':'trough','close_diff_pct':close_diff_pct}}

    return None


# small helper for backtests
if __name__ == '__main__':
    print('Peak/Trough module loaded')
