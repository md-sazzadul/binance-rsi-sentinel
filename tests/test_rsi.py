"""Tests for Wilder RSI calculations."""

import pytest

from app.rsi import WilderRSI


def test_requires_enough_history_to_seed_rsi():
    with pytest.raises(ValueError, match="At least 7 closes"):
        WilderRSI([10, 11, 12, 11, 12, 13], period=6)


def test_all_gains_produce_rsi_100():
    calculator = WilderRSI([1, 2, 3, 4, 5, 6, 7], period=6)
    assert calculator.value == 100.0


def test_all_losses_produce_rsi_zero():
    calculator = WilderRSI([7, 6, 5, 4, 3, 2, 1], period=6)
    assert calculator.value == 0.0


def test_flat_prices_produce_neutral_rsi():
    calculator = WilderRSI([10, 10, 10, 10, 10, 10, 10], period=6)
    assert calculator.value == 50.0


def test_preview_does_not_mutate_committed_state():
    calculator = WilderRSI([10, 11, 10, 12, 11, 13, 12], period=6)
    original_gain = calculator.average_gain
    original_loss = calculator.average_loss
    original_close = calculator.last_close

    first_preview = calculator.preview(8.0)
    second_preview = calculator.preview(9.0)

    assert first_preview < second_preview
    assert calculator.average_gain == original_gain
    assert calculator.average_loss == original_loss
    assert calculator.last_close == original_close


def test_commit_matches_preview_for_same_closed_price():
    calculator = WilderRSI([10, 11, 10, 12, 11, 13, 12], period=6)
    expected = calculator.preview(8.5)
    actual = calculator.commit(8.5)
    assert actual == pytest.approx(expected)
    assert calculator.last_close == 8.5


def test_preview_rejects_non_finite_and_negative_prices():
    calculator = WilderRSI([10, 11, 10, 12, 11, 13, 12], period=6)
    for invalid in (-1, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            calculator.preview(invalid)


def test_websocket_ticks_do_not_mutate_committed_state():
    calculator = WilderRSI([100, 101, 100, 102, 101, 103, 102], period=6)
    baseline = calculator.value
    calculator.preview(95)
    calculator.preview(98)
    calculator.preview(96)
    assert calculator.value == baseline
    assert calculator.last_close == 102
