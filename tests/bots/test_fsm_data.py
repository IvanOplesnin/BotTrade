from __future__ import annotations

import json
from types import SimpleNamespace

from bots.tg_bot.fsm_data import (
    favorite_instruments_from_state,
    favorite_instruments_to_state,
    instruments_from_state,
    instruments_to_state,
)


def test_favorite_instrument_fsm_data_is_json_serializable():
    state = favorite_instruments_to_state([
        SimpleNamespace(
            instrument_uid="UID1",
            ticker="SBER",
            name="Сбер Банк",
            instrument_type="share",
        )
    ])

    restored = favorite_instruments_from_state(json.loads(json.dumps(state)))

    assert state == [
        {
            "instrument_id": "UID1",
            "ticker": "SBER",
            "name": "Сбер Банк",
            "instrument_type": "share",
        }
    ]
    assert restored[0].to_candidate().instrument_id == "UID1"
    assert restored[0].to_candidate().ticker == "SBER"
    assert restored[0].to_candidate().instrument_type == "share"


def test_instrument_fsm_data_is_json_serializable():
    state = instruments_to_state([
        SimpleNamespace(
            instrument_id="UID2",
            ticker="YDEX",
            type="share",
        )
    ])

    restored = instruments_from_state(json.loads(json.dumps(state)))

    assert state == [
        {
            "instrument_id": "UID2",
            "ticker": "YDEX",
            "instrument_type": "share",
        }
    ]
    assert restored[0].instrument_id == "UID2"
    assert restored[0].ticker == "YDEX"
    assert restored[0].instrument_type == "share"

