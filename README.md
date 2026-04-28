# Validus Trading Case Study - Achille Nicoletti

This is my submission for the Validus backend exercise. It's a Python
project that implements the trade approval workflow from the brief as
an importable library, with a thin FastAPI layer on top so it can be
exercised with curl rather than a REPL. The state machine, validation,
4-eyes authorization, audit log, version history and field-level diffs
are all there; on top of that I added a small risk and Monte Carlo
forecast layer, since the brief invited extras. Per the disclosure
requirement: I used Claude as a pair-programming assistant for the
mechanical parts (scaffolding parametrised tests, drafting the curl
examples, sense-checking the GBM maths) - the design decisions and
every line that landed were reviewed by me before commit.

# Trade Approval API

Implementation of the Validus trade-approval case study. A trade walks
through a state machine (Draft → PendingApproval → Approved →
SentToCounterparty → Executed) with a full audit log along the way. There's
also a small risk/forecast layer on top, since the brief invited extras.

Built with FastAPI, Pydantic v2, and uvicorn. Tested with pytest.

## Quick start

Requires Python 3.11+.

```bash
python -m pip install -e ".[dev]"
python -m pytest                    # run the test suite
python -m uvicorn trade_approval.api.app:app --reload
```

The server listens on http://127.0.0.1:8000. Swagger UI is at `/docs`.

## How it's organized

```
src/trade_approval/
├── domain/      states, TradeDetails, events, Trade aggregate, transitions, diff, errors
├── services/    TradeService — the public library entry point
├── repo/        InMemoryTradeRepository
├── analytics/   FX rates, MTM, VaR, Monte Carlo
└── api/         FastAPI app, routes, request/response models, DI wiring
```

The domain layer doesn't import FastAPI, so you can use the library
programmatically without an HTTP server. The API layer is mostly
translation: HTTP in, service call, domain exception out as a status code.

A trade is stored as an event log. State, current details, version,
requester, and approver are all derived by walking the events. `POST
/trades` writes a `Create` event in Draft; every subsequent action appends
one more.

## State machine

| From | Action | To | Who |
|---|---|---|---|
| Draft | Submit | PendingApproval | requester |
| PendingApproval | Approve | Approved | not the requester (4-eyes) |
| PendingApproval | Update | NeedsReapproval | not the requester |
| PendingApproval | Cancel | Cancelled | requester or approver |
| NeedsReapproval | Approve | Approved | original requester |
| NeedsReapproval | Cancel | Cancelled | requester or approver |
| Approved | SendToExecute | SentToCounterparty | approver |
| Approved | Cancel | Cancelled | requester or approver |
| SentToCounterparty | Book | Executed | requester or approver |
| SentToCounterparty | Cancel | Cancelled | requester or approver |
| Executed | (terminal) | | |
| Cancelled | (terminal) | | |

The table in `domain/workflow.py` is authoritative. Any `(state, action)`
not listed there raises `IllegalTransitionError` (HTTP 409).

### Who's who

- **Requester**: whoever created the trade.
- **Approver**: the first person other than the requester to act while the
  trade is in PendingApproval (by approving or by updating). Once that
  person is set, nobody else can take over the approver slot.
- **4-eyes**: the requester can never approve or update their own trade.

The caller identifies themselves with the `X-User-Id` header. Real auth was
out of scope.

## Validation rules

Most of these live on `TradeDetails`:

- `notional_currency` and both `underlying` codes must be ISO 4217. The
  bundled set in `domain/details.py` covers the common codes; extend it if
  you need more.
- `underlying[0] != underlying[1]`, and `notional_currency` has to be one
  of them.
- `trade_date <= value_date <= delivery_date`.
- `notional_amount > 0`. `strike > 0` when set.

`TradeDetails` is frozen. Any update produces a fresh snapshot via
`with_updates(...)`.

## Endpoints

```
POST   /trades                          create a Draft
POST   /trades/{id}/submit              Draft -> PendingApproval
POST   /trades/{id}/approve             context-dependent (see state table)
PATCH  /trades/{id}                     update details (-> NeedsReapproval)
POST   /trades/{id}/cancel              cancel from any non-terminal state
POST   /trades/{id}/send-to-execute     Approved -> SentToCounterparty
POST   /trades/{id}/book                SentToCounterparty -> Executed

GET    /trades                          list (filterable by ?state= and ?user_id=)
GET    /trades/{id}                     current view
GET    /trades/{id}/history             tabular audit log
GET    /trades/{id}/versions/{v}        details snapshot at a given version
GET    /trades/{id}/diff?from=X&to=Y    field-level diff between two versions

GET    /trades/{id}/risk                spot, MTM, 1-day VaR
GET    /trades/{id}/forecast            Monte Carlo P&L

GET    /health
```

Errors map to HTTP codes like this:

| Exception | Status |
|---|---|
| `TradeNotFoundError`, `VersionNotFoundError` | 404 |
| `UnauthorizedActionError` | 403 |
| `IllegalTransitionError` | 409 |
| Pydantic validation | 422 |
| Other `DomainError` | 400 |

## A full lifecycle in curl

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

# 2. Submit, take an update from the approver, reapprove, send, book
curl -X POST $BASE/trades/$TID/submit           -H "X-User-Id: alice"
curl -X PATCH $BASE/trades/$TID -H "X-User-Id: bob" \
     -H "Content-Type: application/json" -d '{"notional_amount": "1200000"}'
curl -X POST $BASE/trades/$TID/approve          -H "X-User-Id: alice"
curl -X POST $BASE/trades/$TID/send-to-execute  -H "X-User-Id: bob"
curl -X POST $BASE/trades/$TID/book             -H "X-User-Id: bob" \
     -H "Content-Type: application/json" -d '{"strike": "1.05"}'

# 3. Audit trail
curl $BASE/trades/$TID/history
curl $BASE/trades/$TID/versions/1
curl "$BASE/trades/$TID/diff?from=1&to=2"
# -> {"changes": {"notional_amount": ["1000000", "1200000"]}}

# 4. Risk and forecast
curl $BASE/trades/$TID/risk
curl "$BASE/trades/$TID/forecast?num_simulations=1000&seed=7"
```

## Analytics

Both endpoints read from a hardcoded mock FX provider
(`analytics/fx_rates.py`). For anything real you'd swap that for a
market-data feed.

`GET /trades/{id}/risk` returns:

- Mark-to-market once the trade is booked: `sign * notional * (spot - strike)`
  in the quote currency. `sign` is +1 for Buy, -1 for Sell.
- 1-day parametric VaR: `z * notional * spot * σ_daily`, where
  `σ_daily = σ_annual / sqrt(252)`. Reported at 95% (z=1.645) and 99%
  (z=2.326).
- Days remaining to the value and delivery dates.

`GET /trades/{id}/forecast` runs a Monte Carlo on the spot rate under
geometric Brownian motion (zero drift, pair volatility) from today to the
delivery date. You get the terminal spot mean and 5/95% percentiles, the
terminal P&L distribution, and a sampled path. Pass `seed=` for
reproducibility.

Query params: `num_simulations` (100-10000, default 1000), `num_steps`
(1-50, default 10), `seed` (optional).

## Tests

```
tests/
├── unit/
│   ├── test_details_validation.py     pydantic rules, positive and negative
│   ├── test_workflow_transitions.py   parametrized over every (state, action)
│   ├── test_authorization.py          4-eyes, approver-of-record, role combos
│   └── test_diff.py                   diff correctness, including dates and tuples
└── integration/
    ├── test_scenarios.py              the three PDF scenarios + history/diff
    ├── test_api.py                    error mappings, listing, filters
    └── test_analytics.py              risk, forecast, determinism
```

`python -m pytest` runs the lot. 94 tests at the time of writing, all
green.

## Design notes

A few decisions worth flagging:

- **Two-step creation.** `POST /trades` produces a Draft, and `/submit`
  moves it to PendingApproval. A single-step create-and-submit would be
  reasonable too, but you'd skip the Draft state entirely.
- **Strict 4-eyes.** The PDF's wording is looser; this implementation
  refuses to let a requester act as their own approver. If you want to
  relax it, change the relevant `AuthRule.NOT_REQUESTER` entries in
  `domain/workflow.py`.
- **Event-sourced, in memory.** A trade *is* its event list. The service
  layer talks to the repo via an interface, so swapping in something
  durable is mechanical.
- **Decimal for money.** Amounts and strikes are `Decimal`, serialized as
  strings in JSON to avoid float surprises.

## Running a test, end to end

A worked example, in case you want to verify the system is behaving the way
the brief describes.

### Run the whole suite

```bash
$ python -m pytest -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.x.x
collected 94 items

tests/unit/test_authorization.py::test_only_requester_can_submit          PASSED
tests/unit/test_authorization.py::test_requester_cannot_approve_own_trade PASSED
...
tests/integration/test_scenarios.py::test_scenario_1_submit_and_approve   PASSED
tests/integration/test_scenarios.py::test_scenario_2_update_triggers_reapproval PASSED
tests/integration/test_scenarios.py::test_scenario_3_execution            PASSED
tests/integration/test_scenarios.py::test_scenario_4_history_and_diff     PASSED
...

============================== 94 passed in 0.47s ==============================
```

### Run a single test

To run just scenario 2 (the update-then-reapprove flow):

```bash
python -m pytest tests/integration/test_scenarios.py::test_scenario_2_update_triggers_reapproval -v
```

### Test it manually against a running server

If you want to confirm the workflow with your own eyes, start the server in
one terminal and walk through scenario 2 by hand in another.

Terminal A:

```bash
python -m uvicorn trade_approval.api.app:app --reload
```

Terminal B:

```bash
BASE=http://127.0.0.1:8000

# Create the trade as alice
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

# Submit
curl -s -X POST $BASE/trades/$TID/submit -H "X-User-Id: alice" | jq .state
# -> "PendingApproval"

# Bob updates the notional -> NeedsReapproval
curl -s -X PATCH $BASE/trades/$TID \
  -H "X-User-Id: bob" -H "Content-Type: application/json" \
  -d '{"notional_amount": "1200000"}' | jq .state
# -> "NeedsReapproval"

# Alice (the original requester) reapproves
curl -s -X POST $BASE/trades/$TID/approve -H "X-User-Id: alice" | jq .state
# -> "Approved"

# Diff between v1 and v2 should only show the amount change
curl -s "$BASE/trades/$TID/diff?from=1&to=2" | jq .changes
# -> { "notional_amount": [ "1000000", "1200000" ] }
```

And if you try to make Alice approve her own trade without Bob's update in
between, you should get a 403:

```bash
curl -i -X POST $BASE/trades/$TID/approve -H "X-User-Id: alice"
# HTTP/1.1 403 Forbidden
# {"detail":"Requester cannot act as approver (4-eyes principle)"}
```

That's the 4-eyes rule.
