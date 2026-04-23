# Trade Approval API

A Python library + HTTP service that implements the trade-approval workflow
described in the Validus case study. Trades move through a strict state
machine, every action is auditable, and an analytics layer adds mark-to-market
and Monte Carlo P&L forecasts on top.

Built with **FastAPI**, **Pydantic v2**, **uvicorn**; tested with **pytest**.

## Quick start

```bash
# install (requires Python 3.11+)
python -m pip install -e ".[dev]"

# run the tests
python -m pytest

# run the service
python -m uvicorn trade_approval.api.app:app --reload
# → open http://127.0.0.1:8000/docs for interactive Swagger UI
```

## Architecture

```
src/trade_approval/
├── domain/       states, TradeDetails (with validators), events, Trade aggregate,
│                 transition table + auth rules, diff, domain exceptions
├── services/     TradeService — orchestrates actions; the public library surface
├── repo/         InMemoryTradeRepository (thread-safe via RLock)
├── analytics/    mock FX rates, risk metrics (MTM, VaR), Monte Carlo forecast
└── api/          FastAPI app, routes, request/response DTOs, DI wiring
```

The **domain** layer is pure Python and has no FastAPI dependency — the
library can be used programmatically. FastAPI is a thin shell that maps HTTP
calls to service methods and domain exceptions to HTTP status codes.

A **trade is an event log.** State, current details, version number, requester,
and approver are all derived by reducing the event list. `POST /trades`
creates a `Create` event (Draft state) and every action appends one more.

## State machine

| From state | Action | To state | Who |
|---|---|---|---|
| Draft | Submit | PendingApproval | requester |
| PendingApproval | Approve | Approved | ≠ requester *(4-eyes)* |
| PendingApproval | Update | NeedsReapproval | ≠ requester |
| PendingApproval | Cancel | Cancelled | requester or approver |
| NeedsReapproval | Approve | Approved | **original requester** |
| NeedsReapproval | Cancel | Cancelled | requester or approver |
| Approved | SendToExecute | SentToCounterparty | approver |
| Approved | Cancel | Cancelled | requester or approver |
| SentToCounterparty | Book | Executed | requester or approver |
| SentToCounterparty | Cancel | Cancelled | requester or approver |
| Executed / Cancelled | — | *(terminal)* | |

The table in `domain/workflow.py` is the single source of truth; any `(state,
action)` not present raises `IllegalTransitionError` (HTTP 409).

### Authorization model

- **Requester** = whoever created the trade.
- **Approver** = the first user (other than the requester) to act on the
  trade while it is in PendingApproval (via Approve or Update). Once set,
  no other user can take over the approver role.
- **4-eyes principle**: the requester cannot approve or update their own
  trade. Enforced strictly.

Callers identify themselves via the `X-User-Id` header (prototype auth).

## Validation rules (TradeDetails)

- `notional_currency` and both `underlying` entries must be ISO 4217 codes
  (a subset of common codes is bundled — see `domain/details.py`).
- `underlying[0] != underlying[1]` and `notional_currency ∈ underlying`.
- `trade_date ≤ value_date ≤ delivery_date`.
- `notional_amount > 0`, and `strike > 0` if provided.
- `TradeDetails` objects are **frozen** (immutable). Updates produce new
  snapshots via `with_updates(...)`.

## API surface

```
POST   /trades                         create a Draft
POST   /trades/{id}/submit             Draft → PendingApproval
POST   /trades/{id}/approve            context-sensitive approve
PATCH  /trades/{id}                    approver updates details → NeedsReapproval
POST   /trades/{id}/cancel             cancel from any non-terminal state
POST   /trades/{id}/send-to-execute    Approved → SentToCounterparty
POST   /trades/{id}/book               SentToCounterparty → Executed (sets strike)

GET    /trades                         list (optional ?state=, ?user_id=)
GET    /trades/{id}                    current view
GET    /trades/{id}/history            tabular audit log
GET    /trades/{id}/versions/{v}       trade details at a specific version
GET    /trades/{id}/diff?from=X&to=Y   field-level diff between two versions

GET    /trades/{id}/risk               spot, MTM, 1-day VaR (95% / 99%)
GET    /trades/{id}/forecast           Monte Carlo P&L path + distribution

GET    /health                         liveness probe
```

### HTTP error taxonomy

| Exception | Status |
|---|---|
| `TradeNotFoundError`, `VersionNotFoundError` | 404 |
| `UnauthorizedActionError` | 403 |
| `IllegalTransitionError` | 409 |
| Pydantic `ValidationError` (request or domain) | 422 |
| Other `DomainError` | 400 |

## Example: full lifecycle

```bash
BASE=http://127.0.0.1:8000

# 1. Create a Draft
TID=$(curl -s -X POST $BASE/trades \
    -H "X-User-Id: alice" -H "Content-Type: application/json" \
    -d '{
      "trading_entity": "Acme Ltd",
      "counterparty": "Big Bank",
      "direction": "Buy",
      "notional_currency": "EUR",
      "notional_amount": "1000000",
      "underlying": ["EUR", "USD"],
      "trade_date": "2026-04-23",
      "value_date":  "2026-05-23",
      "delivery_date": "2026-05-25"
    }' | jq -r .id)

# 2. Submit, update (reapproval), reapprove, send to counterparty, book
curl -X POST $BASE/trades/$TID/submit           -H "X-User-Id: alice"
curl -X PATCH $BASE/trades/$TID -H "X-User-Id: bob" \
     -H "Content-Type: application/json" -d '{"notional_amount": "1200000"}'
curl -X POST $BASE/trades/$TID/approve          -H "X-User-Id: alice"
curl -X POST $BASE/trades/$TID/send-to-execute  -H "X-User-Id: bob"
curl -X POST $BASE/trades/$TID/book             -H "X-User-Id: bob" \
     -H "Content-Type: application/json" -d '{"strike": "1.05"}'

# 3. Audit: history, a prior version, and a diff
curl $BASE/trades/$TID/history
curl $BASE/trades/$TID/versions/1
curl "$BASE/trades/$TID/diff?from=1&to=2"
# → {"changes": {"notional_amount": ["1000000", "1200000"]}}

# 4. Analytics
curl $BASE/trades/$TID/risk
curl "$BASE/trades/$TID/forecast?num_simulations=1000&seed=7"
```

## Analytics

Both endpoints use a deterministic mock FX rate provider (see
`analytics/fx_rates.py`) — swap it for a real market-data feed to productionize.

### `GET /trades/{id}/risk`

- **Mark-to-market** (if the trade is booked): `sign × notional × (spot −
  strike)`, in quote currency, where `sign = +1` for Buy and `−1` for Sell.
- **1-day VaR** (parametric, normal): `z × notional × spot × σ_daily`, with
  `σ_daily = σ_annual / √252`. Reported at 95% (z = 1.645) and 99% (z = 2.326).
- Days remaining to value and delivery dates.

### `GET /trades/{id}/forecast`

Monte Carlo simulation of the spot rate under geometric Brownian motion
(zero drift, pair volatility) from today to the delivery date. Returns:

- Terminal spot rate — mean and 5% / 95% percentiles.
- Terminal P&L — mean, 5% / 95% percentiles, and `pnl_var_95` (the loss
  size at the 5th-percentile outcome).
- A `path` of `(days_ahead, mean_pnl, p05_pnl, p95_pnl)` points.

Query parameters: `num_simulations` (100–10,000, default 1,000), `num_steps`
(1–50, default 10), `seed` (optional — pass one for reproducible output).

## Tests

```
tests/
├── unit/
│   ├── test_details_validation.py     every Pydantic rule, positive + negative
│   ├── test_workflow_transitions.py   parametrized over every (state, action)
│   ├── test_authorization.py          4-eyes, approver-of-record, role combos
│   └── test_diff.py                   diff correctness incl. dates + tuples
└── integration/
    ├── test_scenarios.py              the 3 PDF scenarios + history/diff
    ├── test_api.py                    error mappings, listing, filters
    └── test_analytics.py              risk, forecast, determinism
```

Run everything with `python -m pytest`. As of last run: **94 tests, all
passing**.

## Design notes / tradeoffs

- **Two-step creation** (`POST /trades` then `/submit`) matches the state
  table literally. A single-step `POST` creating a PendingApproval trade
  would also be reasonable but would not visit the Draft state.
- **Strict 4-eyes**: requester cannot act as approver. The PDF's wording is
  looser; this can be relaxed by changing `AuthRule.NOT_REQUESTER` usage in
  `domain/workflow.py`.
- **Event-sourced, in-memory**: the trade is the list of events; persistence
  can be added by swapping `InMemoryTradeRepository` — the service layer
  depends only on its interface.
- **Decimal for money**: amounts and strikes are `Decimal`, serialized as
  strings in JSON to avoid float precision loss.
```
