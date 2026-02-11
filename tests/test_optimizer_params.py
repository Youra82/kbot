from kbot.analysis.optimizer import parse_param_spec


def test_parse_int_range():
    r = parse_param_spec('lookback_n:3:10:1')
    assert r[0] == 'lookback_n' and r[1] == 'int_range' and r[2] == (3,10,1)


def test_parse_float_range():
    r = parse_param_spec('atr_mult:1.0:2.0:0.1')
    assert r[0] == 'atr_mult' and r[1] == 'float_range' and r[2] == (1.0,2.0,0.1)


def test_parse_categorical():
    r = parse_param_spec('use_volume_confirmation:0,1')
    assert r[0] == 'use_volume_confirmation' and r[1] == 'categorical'
    assert r[2] == [0,1] or r[2] == ['0','1']
