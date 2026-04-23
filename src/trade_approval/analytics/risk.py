"""Risk metrics and Monte Carlo P&L forecast for a forward contract.

All P&L figures are expressed in the quote currency of the pair.
"""

import math
import random
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from ..domain.details import TradeDetails
from ..domain.trade import Trade
from . import fx_rates


class RiskMetrics(BaseModel):
    trade_id: str
    base_currency: str
    quote_currency: str
    notional_amount: Decimal
    strike: Optional[Decimal]
    spot_rate: float
    days_to_value: int
    days_to_delivery: int
    annualized_volatility: float
    mark_to_market: Optional[Decimal]    # quote ccy; None if not yet booked
    var_95_1day: Decimal                 # 1-day 95% VaR (loss amount)
    var_99_1day: Decimal


class ForecastPoint(BaseModel):
    days_ahead: int
    mean_pnl: Decimal
    p05_pnl: Decimal
    p95_pnl: Decimal


class Forecast(BaseModel):
    trade_id: str
    num_simulations: int
    horizon_days: int
    spot_rate_now: float
    final_spot_mean: float
    final_spot_p05: float
    final_spot_p95: float
    pnl_mean: Decimal
    pnl_p05: Decimal
    pnl_p95: Decimal
    pnl_var_95: Decimal   # size of the loss at the 5th percentile (positive number)
    path: list[ForecastPoint]


def _base_quote(details: TradeDetails) -> tuple[str, str]:
    """Return (base, quote) where base is the notional currency."""
    base = details.notional_currency
    quote = next(c for c in details.underlying if c != base)
    return base, quote


def _direction_sign(direction: str) -> int:
    """+1 for Buy (long base), -1 for Sell (short base)."""
    return 1 if direction == "Buy" else -1


def _dec(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def compute_risk(trade: Trade, as_of: Optional[date] = None) -> RiskMetrics:
    """One-shot risk snapshot: MTM (if booked) and 1-day VaR."""
    details = trade.current_details
    base, quote = _base_quote(details)
    spot = fx_rates.spot_rate(base, quote)
    vol = fx_rates.pair_volatility(base, quote)
    today = as_of or date.today()

    notional = float(details.notional_amount)
    sign = _direction_sign(details.direction)

    mtm: Optional[Decimal] = None
    if details.strike is not None:
        strike = float(details.strike)
        mtm = _dec(sign * notional * (spot - strike))

    # Parametric 1-day VaR: notional * spot is the USD-equivalent exposure,
    # daily vol = annual vol / sqrt(252). 1.645 = 95% z-score, 2.326 = 99%.
    daily_vol = vol / math.sqrt(252)
    one_day_shock = notional * spot * daily_vol
    var_95 = _dec(1.645 * one_day_shock)
    var_99 = _dec(2.326 * one_day_shock)

    return RiskMetrics(
        trade_id=trade.id,
        base_currency=base,
        quote_currency=quote,
        notional_amount=details.notional_amount,
        strike=details.strike,
        spot_rate=spot,
        days_to_value=(details.value_date - today).days,
        days_to_delivery=(details.delivery_date - today).days,
        annualized_volatility=vol,
        mark_to_market=mtm,
        var_95_1day=var_95,
        var_99_1day=var_99,
    )


def forecast(
    trade: Trade,
    num_simulations: int = 1000,
    num_steps: int = 10,
    seed: Optional[int] = None,
    as_of: Optional[date] = None,
) -> Forecast:
    """Monte Carlo GBM forecast of P&L to the delivery date.

    Simulates the spot rate under geometric Brownian motion with zero drift
    and the pair's annualized volatility. Returns distribution percentiles
    both at the horizon and along a sampled path.
    """
    details = trade.current_details
    base, quote = _base_quote(details)
    spot = fx_rates.spot_rate(base, quote)
    vol = fx_rates.pair_volatility(base, quote)
    today = as_of or date.today()
    horizon_days = max(1, (details.delivery_date - today).days)

    rng = random.Random(seed if seed is not None else 42)
    notional = float(details.notional_amount)
    sign = _direction_sign(details.direction)
    reference = float(details.strike) if details.strike is not None else spot

    dt = 1.0 / 252.0
    drift_per_step = -0.5 * vol * vol * dt
    diffusion_per_step = vol * math.sqrt(dt)

    # Build sampling days, evenly spaced, always including horizon.
    step_size = max(1, horizon_days // max(1, num_steps))
    sampled_days = list(range(step_size, horizon_days + 1, step_size))
    if not sampled_days or sampled_days[-1] != horizon_days:
        sampled_days.append(horizon_days)

    # Simulate: store P&L at each sampled day for every simulation.
    pnl_samples: list[list[float]] = [[] for _ in sampled_days]
    terminal_spots: list[float] = []

    for _ in range(num_simulations):
        s = spot
        next_idx = 0
        for day in range(1, horizon_days + 1):
            z = rng.gauss(0.0, 1.0)
            s *= math.exp(drift_per_step + diffusion_per_step * z)
            if next_idx < len(sampled_days) and day == sampled_days[next_idx]:
                pnl_samples[next_idx].append(sign * notional * (s - reference))
                next_idx += 1
        terminal_spots.append(s)

    def percentile(sorted_xs: list[float], p: float) -> float:
        idx = min(len(sorted_xs) - 1, max(0, int(round(p * (len(sorted_xs) - 1)))))
        return sorted_xs[idx]

    terminal_spots_sorted = sorted(terminal_spots)
    final_spot_mean = sum(terminal_spots) / len(terminal_spots)
    final_spot_p05 = percentile(terminal_spots_sorted, 0.05)
    final_spot_p95 = percentile(terminal_spots_sorted, 0.95)

    terminal_pnl_sorted = sorted(pnl_samples[-1])
    pnl_mean = sum(pnl_samples[-1]) / len(pnl_samples[-1])
    pnl_p05 = percentile(terminal_pnl_sorted, 0.05)
    pnl_p95 = percentile(terminal_pnl_sorted, 0.95)
    # VaR is the magnitude of loss at the 5th-percentile outcome.
    pnl_var_95 = max(0.0, -pnl_p05)

    path: list[ForecastPoint] = []
    for i, day in enumerate(sampled_days):
        samples = sorted(pnl_samples[i])
        path.append(ForecastPoint(
            days_ahead=day,
            mean_pnl=_dec(sum(samples) / len(samples)),
            p05_pnl=_dec(percentile(samples, 0.05)),
            p95_pnl=_dec(percentile(samples, 0.95)),
        ))

    return Forecast(
        trade_id=trade.id,
        num_simulations=num_simulations,
        horizon_days=horizon_days,
        spot_rate_now=spot,
        final_spot_mean=final_spot_mean,
        final_spot_p05=final_spot_p05,
        final_spot_p95=final_spot_p95,
        pnl_mean=_dec(pnl_mean),
        pnl_p05=_dec(pnl_p05),
        pnl_p95=_dec(pnl_p95),
        pnl_var_95=_dec(pnl_var_95),
        path=path,
    )
