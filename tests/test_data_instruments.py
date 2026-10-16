import pytest

from mmlab.data.instruments import parse_symbol_filters

PAYLOAD = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
            ],
        },
        {"symbol": "BROKEN", "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.01"}]},
    ]
}


def test_parse_symbol_filters():
    filters = parse_symbol_filters(PAYLOAD, "BTCUSDT")
    assert filters.tick_size == 0.1
    assert filters.lot_size == 0.001


def test_unknown_symbol_raises():
    with pytest.raises(ValueError, match="not found"):
        parse_symbol_filters(PAYLOAD, "NOPE")


def test_missing_filter_raises():
    with pytest.raises(ValueError, match="missing filter"):
        parse_symbol_filters(PAYLOAD, "BROKEN")
