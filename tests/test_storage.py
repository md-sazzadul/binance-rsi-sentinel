"""Tests for persistent alert state and SQLite email outbox."""

from app.storage import AlertStore


def make_store(tmp_path):
    return AlertStore(tmp_path / "alerts.sqlite3")


def observe(store, symbol="BTCUSDT", rsi=19.5, candle_closed=False):
    return store.observe_rsi(
        symbol=symbol,
        rsi=rsi,
        period=6,
        interval="1h",
        threshold=20.0,
        candle_close="65000.5",
        candle_close_time="2026-11-05T18:00:00+00:00",
        candle_closed=candle_closed,
    )


def test_initial_below_threshold_does_not_alert_for_new_symbol(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=False)

    assert observe(store, rsi=18.0) is None
    assert store.get_pending_alerts() == []


def test_crossing_below_threshold_creates_one_pending_alert(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)

    alert_id = observe(store, rsi=19.5)

    assert alert_id is not None
    pending = store.get_pending_alerts()
    assert len(pending) == 1
    assert pending[0].id == alert_id
    assert pending[0].symbol == "BTCUSDT"
    assert store.get_symbol_state("BTCUSDT") is False


def test_repeated_low_values_do_not_create_duplicate_alerts(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)

    first = observe(store, rsi=19.5)
    second = observe(store, rsi=17.0)

    assert first is not None
    assert second is None
    assert len(store.get_pending_alerts()) == 1


def test_recovery_rearms_then_next_crossing_creates_alert(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)

    assert observe(store, rsi=19.5) is not None
    # An intrabar recovery must not re-arm the symbol.
    assert observe(store, rsi=22.0, candle_closed=False) is None
    assert observe(store, rsi=19.0) is None

    # A recovery confirmed by a closed candle re-arms the symbol.
    assert observe(store, rsi=22.0, candle_closed=True) is None
    next_alert = observe(store, rsi=19.0)

    assert next_alert is not None
    assert len(store.get_pending_alerts()) == 2


def test_symbol_state_survives_store_recreation(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)
    assert observe(store, rsi=19.5) is not None

    restarted_store = make_store(tmp_path)
    restarted_store.initialize_symbol("BTCUSDT", armed=True)

    assert restarted_store.get_symbol_state("BTCUSDT") is False
    assert len(restarted_store.get_pending_alerts()) == 1


def test_sent_alerts_are_removed_from_pending_queue(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("ETHUSDT", armed=True)
    alert_id = observe(store, symbol="ETHUSDT", rsi=18.0)

    store.mark_alert_sent(alert_id)

    assert store.get_pending_alerts() == []


def test_delivery_failure_keeps_alert_pending_and_increments_attempts(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("SOLUSDT", armed=True)
    alert_id = observe(store, symbol="SOLUSDT", rsi=16.0)

    store.record_delivery_failure(alert_id, "temporary SMTP error")
    pending = store.get_pending_alerts()

    assert len(pending) == 1
    assert pending[0].attempts == 1



def test_intrabar_recovery_does_not_rearm_alert(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)

    assert observe(store, rsi=19.5) is not None
    assert observe(store, rsi=21.0, candle_closed=False) is None
    assert observe(store, rsi=19.0) is None
    assert len(store.get_pending_alerts()) == 1
    assert store.get_symbol_state("BTCUSDT") is False


def test_closed_candle_recovery_rearms_alert(tmp_path):
    store = make_store(tmp_path)
    store.initialize_symbol("BTCUSDT", armed=True)

    assert observe(store, rsi=19.5) is not None
    assert observe(store, rsi=21.0, candle_closed=True) is None
    assert store.get_symbol_state("BTCUSDT") is True
    assert observe(store, rsi=19.0) is not None
    assert len(store.get_pending_alerts()) == 2
