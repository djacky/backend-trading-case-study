"""Trade details with Pydantic validation."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ISO 4217 currency codes. Subset of the most common codes — covers all
# typical FX pair combinations for the prototype.
ISO_4217_CODES = frozenset({
    "AED", "ARS", "AUD", "BGN", "BRL", "CAD", "CHF", "CLP", "CNY", "COP",
    "CZK", "DKK", "EGP", "EUR", "GBP", "HKD", "HUF", "IDR", "ILS", "INR",
    "ISK", "JPY", "KRW", "MXN", "MYR", "NOK", "NZD", "PEN", "PHP", "PLN",
    "RON", "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "USD", "VND",
    "ZAR",
})


CurrencyCode = str  # alias for readability; validated in model_validator


class TradeDetails(BaseModel):
    """Immutable snapshot of trade details at a given version."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    trading_entity: str = Field(min_length=1)
    counterparty: str = Field(min_length=1)
    direction: Literal["Buy", "Sell"]
    style: Literal["Forward"] = "Forward"
    notional_currency: CurrencyCode
    notional_amount: Decimal
    underlying: tuple[CurrencyCode, CurrencyCode]
    trade_date: date
    value_date: date
    delivery_date: date
    strike: Optional[Decimal] = None

    @model_validator(mode="after")
    def _validate(self) -> "TradeDetails":
        for code in (self.notional_currency, *self.underlying):
            if code not in ISO_4217_CODES:
                raise ValueError(f"Invalid ISO 4217 currency code: {code!r}")

        if self.underlying[0] == self.underlying[1]:
            raise ValueError("Underlying currencies must be distinct")

        if self.notional_currency not in self.underlying:
            raise ValueError(
                "Notional currency must be one of the underlying currencies"
            )

        if not (self.trade_date <= self.value_date <= self.delivery_date):
            raise ValueError(
                "Date ordering violated: Trade Date <= Value Date <= Delivery Date"
            )

        if self.notional_amount <= Decimal("0"):
            raise ValueError("Notional amount must be positive")

        if self.strike is not None and self.strike <= Decimal("0"):
            raise ValueError("Strike must be positive")

        return self

    def with_updates(self, updates: dict[str, Any]) -> "TradeDetails":
        """Return a new TradeDetails with the given fields replaced."""
        return self.model_copy(update=updates)
