from database.pgsql.models import Base


def test_strategy_storage_tables_are_registered_in_metadata():
    assert {
        "candles",
        "strategy_bindings",
        "strategy_states",
        "strategy_signals",
    }.issubset(Base.metadata.tables)


def test_candles_are_keyed_by_instrument_timeframe_and_time():
    candles = Base.metadata.tables["candles"]

    assert [column.name for column in candles.primary_key.columns] == [
        "instrument_id",
        "timeframe",
        "time",
    ]
    assert {"open", "high", "low", "close", "volume", "is_complete"}.issubset(
        set(candles.c.keys())
    )


def test_strategy_state_and_signal_tables_keep_json_payloads():
    state = Base.metadata.tables["strategy_states"]
    signals = Base.metadata.tables["strategy_signals"]
    bindings = Base.metadata.tables["strategy_bindings"]

    assert "state_json" in state.c
    assert "payload" in signals.c
    assert "params" in bindings.c
    assert {"strategy_code", "version", "instrument_id", "mode"}.issubset(
        set(bindings.c.keys())
    )
    assert {"strategy_code", "strategy_version", "kind", "price", "event_time"}.issubset(
        set(signals.c.keys())
    )
