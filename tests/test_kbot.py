import os, sys
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from kbot.strategy.signal import flow_events, hourly_flows, baseline_at
from kbot.utils.bridge_monitor import BridgeMonitor, RpcError
from kbot.utils.bridge_registry import token_of, decode_dest, BRIDGES, CCTP_MESSENGER


def _series(n, val=1e5):
    idx = pd.date_range('2026-01-01', periods=n, freq='h', tz='UTC')
    return pd.Series(val, index=idx)


def test_no_event_before_min_baseline():
    F = _series(24 * 10); F.iloc[-1] = 1e8
    assert flow_events(F, 3, 1e6, 24) == []


def test_event_and_lockout():
    F = _series(24 * 20)
    F.iloc[-30] = 5e6; F.iloc[-20] = 5e6; F.iloc[-1] = 5e6
    ev = flow_events(F, 3, 1e6, 24)
    assert ev == [F.index[-30], F.index[-1]]        # -20 liegt in der 24h-Sperre


def test_absolute_minimum():
    F = _series(24 * 20, 1e4); F.iloc[-1] = 5e5      # 50x Baseline, aber < A
    assert flow_events(F, 3, 1e6, 24) == []


def test_baseline_excludes_current_hour():
    F = _series(24 * 20); F.iloc[-1] = 9e9
    assert baseline_at(F, F.index[-1]) == pytest.approx(1e5)


def test_hourly_flows_gapless():
    df = pd.DataFrame({'ts': pd.to_datetime(['2026-01-01T00:10Z', '2026-01-01T00:50Z', '2026-01-01T03:00Z'], utc=True),
                       'token': ['ARB'] * 3, 'usd': [1, 2, 4]})
    F = hourly_flows(df, 'ARB', '2026-01-01T00:00Z', '2026-01-01T04:00Z')
    assert list(F.values) == [3, 0, 0, 4, 0]


def test_token_mapping():
    assert token_of('cctp_v2', 'cctp:3') == 'ARB'
    assert token_of('usdt0', 'lz:30110') == 'ARB'
    assert token_of('op_std', 'op_std') == 'OP'
    assert token_of('cctp_v2', 'cctp:?') is None
    assert token_of('cctp_v2', 'cctp:999') is None


def test_decode_cctp_domain():
    data = '0x' + f'{5:064x}' + '0' * 64 + f'{6:064x}' + '0' * 64
    rec = {'logs': [{'address': CCTP_MESSENGER['cctp_v2'], 'topics': [], 'data': data}]}
    assert decode_dest('cctp_v2', rec) == 'cctp:6'


class FakeClient:
    def __init__(self, latest, fail_at=None):
        self.latest, self.fail_at, self.ranges = latest, fail_at, []

    def call(self, method, params, retries=4):
        if method == 'eth_blockNumber':
            return hex(self.latest)
        frm, to = int(params[0]['fromBlock'], 16), int(params[0]['toBlock'], 16)
        if self.fail_at is not None and frm <= self.fail_at <= to:
            raise RpcError('boom')
        self.ranges.append((frm, to))
        return []

    def receipts(self, h):
        return {}


def test_scanner_chunks_max_10_blocks():
    m = BridgeMonitor('x', {}, cursor=1000)
    m.client = FakeClient(1035)
    m.poll()
    assert all(to - frm + 1 <= 10 for frm, to in m.client.ranges)
    assert m.client.ranges[0][0] == 1001 and m.client.ranges[-1][1] == 1035
    assert m.cursor == 1035


def test_scanner_does_not_skip_blocks_on_error():
    m = BridgeMonitor('x', {}, cursor=1000)
    m.client = FakeClient(1035, fail_at=1015)
    with pytest.raises(RpcError):
        m.poll()
    assert m.cursor == 1010           # nur erfolgreiche Abschnitte gezaehlt
    m.client = FakeClient(1035)
    m.poll()
    assert m.client.ranges[0][0] == 1011
