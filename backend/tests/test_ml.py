import pytest


@pytest.mark.ml
def test_walk_forward_keeps_training_before_test_and_shows_baseline():
    pytest.importorskip('torch')
    from app.services.forecasting import train_evaluate
    from app.services.market import demo_payload
    result = train_evaluate(demo_payload('AAPL',True)['points'],epochs=1,demo=True)
    assert result['demo']
    assert len(result['evaluation']) == 3
    assert all(f['train_end'] < f['test_end'] for f in result['folds'])
    assert all('naive_mae' in v and v['n_origins'] == 3 for v in result['evaluation'])
    assert all(v['lstm'] is not None and v['naive'] for v in result['forecasts'])
