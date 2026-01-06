"""
Circuit breaker DISABLED.

This module used to implement a drawdown-based circuit breaker.
Per user request the circuit breaker is disabled but left as a no-op
module to avoid import errors. Functions return neutral values.
"""

def is_trading_allowed():
    return True


def update_circuit_breaker(current_equity, peak_equity=None):
    return 'OK'


def reset_circuit_breaker():
    return None


def check_daily_loss_limit(*args, **kwargs):
    return False
