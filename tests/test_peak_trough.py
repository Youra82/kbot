import pytest
from kbot.strategy.peak_trough import generate_signal

# helper to build ohlcv rows: timestamp, o, h, l, c, v

def bar(ts, o, h, l, c, v=1.0):
    return (ts, o, h, l, c, v)


def test_trough_to_long_signal():
    # create a trough pattern at index 5 then bullish reversal
    ohlcv = []
    # rising then trough
    ohlcv += [bar(i, 10, 11, 9, 10) for i in range(6)]
    # trough low
    ohlcv[3] = bar(3, 9, 10, 8, 8)
    # add subsequent bars, last one bullish
    ohlcv += [bar(6,8,9,7,8), bar(7,8,9,7,10.5)]  # last close higher -> reversal
    cfg = {'lookback_n':2,'reversal_threshold_pct':0.5,'atr_period':3,'atr_mult':1.0,'risk_reward_ratio':1.5}
    sig = generate_signal(ohlcv, cfg)
    assert sig is not None and sig['signal']=='long'


def test_peak_to_short_signal():
    ohlcv = []
    ohlcv += [bar(i, 10, 11, 9, 10) for i in range(6)]
    # create peak at idx 3
    ohlcv[3] = bar(3, 12, 13, 11, 13)
    ohlcv += [bar(6,13,13,12,12.5), bar(7,12.5,12.6,11,11.9)]  # bearish close
    cfg = {'lookback_n':2,'reversal_threshold_pct':0.5,'atr_period':3,'atr_mult':1.0,'risk_reward_ratio':1.5}
    sig = generate_signal(ohlcv, cfg)
    assert sig is not None and sig['signal']=='short'


def test_no_signal_when_flat():
    ohlcv = [bar(i,10,11,9,10) for i in range(10)]
    sig = generate_signal(ohlcv, {})
    assert sig is None
