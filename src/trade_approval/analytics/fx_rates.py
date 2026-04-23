"""Deterministic mock FX rate source for the prototype.

Spot rates are derived from a hardcoded USD table; volatilities are rough
annualized figures. This is purely illustrative — a real system would wire
this to a market-data feed.
"""

import hashlib
import math

# Approximate spot rates quoted as USD per 1 unit of currency.
_MOCK_USD_PER_CCY: dict[str, float] = {
    "USD": 1.00,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0066,
    "CHF": 1.12,
    "CAD": 0.73,
    "AUD": 0.66,
    "NZD": 0.60,
    "CNY": 0.14,
    "HKD": 0.13,
    "SGD": 0.74,
    "INR": 0.012,
    "BRL": 0.20,
    "MXN": 0.058,
    "NOK": 0.094,
    "SEK": 0.095,
    "DKK": 0.145,
    "PLN": 0.25,
    "TRY": 0.031,
    "ZAR": 0.054,
}

# Annualized volatilities (roughly realistic — not calibrated).
_MOCK_VOL: dict[str, float] = {
    "USD": 0.00, "EUR": 0.08, "GBP": 0.10, "JPY": 0.10, "CHF": 0.09,
    "CAD": 0.08, "AUD": 0.11, "NZD": 0.12, "CNY": 0.05, "HKD": 0.02,
    "SGD": 0.06, "INR": 0.07, "BRL": 0.15, "MXN": 0.13, "NOK": 0.11,
    "SEK": 0.11, "DKK": 0.08, "PLN": 0.10, "TRY": 0.20, "ZAR": 0.14,
}


def _usd_rate(ccy: str) -> float:
    if ccy in _MOCK_USD_PER_CCY:
        return _MOCK_USD_PER_CCY[ccy]
    # Deterministic fallback for currencies not in the table.
    digest = int(hashlib.md5(ccy.encode()).hexdigest(), 16)
    return 0.1 + (digest % 10_000) / 10_000.0


def _vol(ccy: str) -> float:
    return _MOCK_VOL.get(ccy, 0.10)


def spot_rate(base: str, quote: str) -> float:
    """Spot rate expressed as QUOTE per 1 BASE.

    e.g. spot_rate("EUR", "USD") ≈ 1.08 means 1 EUR = 1.08 USD.
    """
    if base == quote:
        return 1.0
    return _usd_rate(base) / _usd_rate(quote)


def pair_volatility(base: str, quote: str) -> float:
    """Annualized volatility of the BASE/QUOTE pair.

    Uses a simple zero-correlation approximation: sqrt(var(base) + var(quote)).
    """
    v1 = _vol(base)
    v2 = _vol(quote)
    return math.sqrt(v1 * v1 + v2 * v2)
