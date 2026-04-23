"""Field-level diff between trade-detail versions."""

from datetime import date, timedelta
from decimal import Decimal

from trade_approval.domain.diff import diff_details


def test_diff_reports_only_changed_fields(sample_details):
    updated = sample_details.with_updates({"notional_amount": Decimal("1200000")})
    changes = diff_details(sample_details, updated)
    assert changes == {"notional_amount": ("1000000", "1200000")}


def test_diff_is_empty_for_identical_details(sample_details):
    assert diff_details(sample_details, sample_details) == {}


def test_diff_handles_dates(sample_details):
    new_delivery = sample_details.delivery_date + timedelta(days=5)
    updated = sample_details.with_updates({"delivery_date": new_delivery})
    changes = diff_details(sample_details, updated)
    assert "delivery_date" in changes
    before, after = changes["delivery_date"]
    assert before == sample_details.delivery_date.isoformat()
    assert after == new_delivery.isoformat()


def test_diff_handles_multiple_fields(sample_details):
    updated = sample_details.with_updates({
        "notional_amount": Decimal("2000000"),
        "counterparty": "New Bank",
    })
    changes = diff_details(sample_details, updated)
    assert set(changes.keys()) == {"notional_amount", "counterparty"}


def test_diff_normalizes_tuples_to_lists(sample_details):
    # Change underlying (still must contain notional currency EUR)
    updated = sample_details.with_updates({"underlying": ("EUR", "GBP")})
    changes = diff_details(sample_details, updated)
    before, after = changes["underlying"]
    assert before == ["EUR", "USD"]
    assert after == ["EUR", "GBP"]
