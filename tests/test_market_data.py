"""Tests for splitting symbols into WebSocket-sized groups."""

from app.main import chunked


def test_chunked_splits_symbols_without_losing_order():
    assert chunked(["A", "B", "C", "D", "E"], 2) == [
        ["A", "B"], ["C", "D"], ["E"]
    ]


def test_chunked_empty_input_returns_no_groups():
    assert chunked([], 1024) == []
