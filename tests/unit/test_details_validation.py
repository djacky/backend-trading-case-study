"""Validation rules for TradeDetails."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trade_approval.domain.details import TradeDetails


def _base(**overrides):
    today = date.today()
    base = dict(
        trading_entity="ABC",
        counterparty="XYZ",
        direction="Buy",
        notional_currency="EUR",
        notional_amount=Decimal("1000000"),
        underlying=("EUR", "USD"),
        trade_date=today,
        value_date=today + timedelta(days=1),
        delivery_date=today + timedelta(days=2),
    )
    base.update(overrides)
    return base


def test_valid_trade_details_are_accepted():
    t = TradeDetails(**_base())
    assert t.direction == "Buy"
    assert t.style == "Forward"


def test_invalid_currency_rejected():
    with pytest.raises(ValidationError, match="Invalid ISO 4217"):
        TradeDetails(**_base(notional_currency="ZZZ"))


def test_underlying_must_be_distinct():
    with pytest.raises(ValidationError, match="distinct"):
        TradeDetails(**_base(underlying=("EUR", "EUR")))


def test_notional_must_be_in_underlying():
    with pytest.raises(ValidationError, match="one of the underlying"):
        TradeDetails(**_base(notional_currency="JPY", underlying=("EUR", "USD")))


def test_date_ordering_enforced():
    today = date.today()
    with pytest.raises(ValidationError, match="Date ordering"):
        TradeDetails(**_base(
            trade_date=today,
            value_date=today - timedelta(days=1),
            delivery_date=today + timedelta(days=1),
        ))


def test_value_before_delivery_enforced():
    today = date.today()
    with pytest.raises(ValidationError, match="Date ordering"):
        TradeDetails(**_base(
            trade_date=today,
            value_date=today + timedelta(days=5),
            delivery_date=today + timedelta(days=1),
        ))


def test_trade_date_equal_value_date_equal_delivery_date_is_allowed():
    today = date.today()
    t = TradeDetails(**_base(
        trade_date=today, value_date=today, delivery_date=today,
    ))
    assert t.trade_date == t.value_date == t.delivery_date


def test_non_positive_notional_rejected():
    with pytest.raises(ValidationError, match="positive"):
        TradeDetails(**_base(notional_amount=Decimal("0")))
    with pytest.raises(ValidationError, match="positive"):
        TradeDetails(**_base(notional_amount=Decimal("-1")))


def test_negative_strike_rejected():
    with pytest.raises(ValidationError, match="Strike"):
        TradeDetails(**_base(strike=Decimal("-0.5")))


def test_details_are_frozen():
    t = TradeDetails(**_base())
    with pytest.raises(ValidationError):
        t.direction = "Sell"  # type: ignore[misc]


def test_with_updates_produces_new_instance():
    t = TradeDetails(**_base())
    updated = t.with_updates({"notional_amount": Decimal("1200000")})
    assert t.notional_amount == Decimal("1000000")
    assert updated.notional_amount == Decimal("1200000")
    assert updated is not t
