import pytest

from mmlab.strategies.naive import quote_sides, quote_ticks

POSITION_LIMIT = 0.01
ORDER_QTY = 0.001


@pytest.mark.parametrize(
    ("best_bid", "best_ask", "half_spread", "expected"),
    [
        (1000, 1001, 0, (1000, 1001)),
        (1000, 1001, 5, (995, 1006)),
        (1000, 1001, 0.5, (1000, 1001)),
        (1000, 1001, 2.5, (998, 1003)),
        (1000, 1010, 2, (1000, 1010)),
        (1000, 1010, 8, (997, 1013)),
    ],
)
def test_quotes_sit_half_spread_from_mid_but_never_inside_the_touch(
    best_bid, best_ask, half_spread, expected
):
    assert quote_ticks(best_bid, best_ask, half_spread) == expected


def test_compiled_and_plain_python_agree():
    for best_bid in (999, 1000, 1007):
        for width in (1, 2, 3, 10):
            for half_spread in (0, 0.5, 1, 2.5, 7):
                compiled = quote_ticks(best_bid, best_bid + width, half_spread)
                plain = quote_ticks.py_func(best_bid, best_bid + width, half_spread)
                assert compiled == plain


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (0.0, (True, True)),
        (0.008, (True, True)),
        (0.009, (True, True)),
        (0.0095, (False, True)),
        (0.01, (False, True)),
        (-0.0095, (True, False)),
        (-0.01, (True, False)),
    ],
)
def test_a_side_stops_when_one_more_fill_would_pass_the_limit(position, expected):
    assert quote_sides(position, ORDER_QTY, POSITION_LIMIT) == expected


def test_zero_limit_stops_both_sides():
    assert quote_sides(0.0, ORDER_QTY, 0.0) == (False, False)
