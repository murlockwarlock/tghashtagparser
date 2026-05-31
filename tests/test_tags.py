import pytest

from app.services.tags import normalize_tag


def test_normalize_tag_adds_hash() -> None:
    assert normalize_tag("BTC") == "#BTC"
    assert normalize_tag("#btcusdt") == "#BTCUSDT"


def test_normalize_tag_rejects_bad_value() -> None:
    with pytest.raises(ValueError):
        normalize_tag("#")
