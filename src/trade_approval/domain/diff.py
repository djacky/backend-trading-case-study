"""Field-level diff between two trade-detail snapshots."""

from datetime import date
from decimal import Decimal
from typing import Any

from .details import TradeDetails


def _normalize(value: Any) -> Any:
    """Serialize values to a form suitable for JSON diff output."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def diff_details(
    before: TradeDetails, after: TradeDetails
) -> dict[str, tuple[Any, Any]]:
    """Return {field: (before, after)} for every field that differs.

    Example: diffing a notional change yields {"notional_amount": ("1000000", "1200000")}.
    """
    a = before.model_dump()
    b = after.model_dump()
    changes: dict[str, tuple[Any, Any]] = {}
    for field in a:
        if a[field] != b[field]:
            changes[field] = (_normalize(a[field]), _normalize(b[field]))
    return changes
