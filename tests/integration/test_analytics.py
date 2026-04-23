"""Risk and forecast endpoints."""

from decimal import Decimal


HDR = {"X-User-Id": "alice"}


def _booked_trade(client, sample_payload, strike="1.10"):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    tid = r.json()["id"]
    client.post(f"/trades/{tid}/submit", headers=HDR)
    client.post(f"/trades/{tid}/approve", headers={"X-User-Id": "bob"})
    client.post(f"/trades/{tid}/send-to-execute", headers={"X-User-Id": "bob"})
    client.post(
        f"/trades/{tid}/book",
        json={"strike": strike},
        headers={"X-User-Id": "bob"},
    )
    return tid


def test_risk_snapshot_for_unbooked_trade(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    tid = r.json()["id"]
    r = client.get(f"/trades/{tid}/risk")
    assert r.status_code == 200
    body = r.json()
    assert body["base_currency"] == "EUR"
    assert body["quote_currency"] == "USD"
    assert body["mark_to_market"] is None
    assert Decimal(body["var_95_1day"]) > 0
    assert Decimal(body["var_99_1day"]) > Decimal(body["var_95_1day"])


def test_risk_includes_mtm_after_booking(client, sample_payload):
    tid = _booked_trade(client, sample_payload, strike="1.05")
    r = client.get(f"/trades/{tid}/risk")
    assert r.status_code == 200
    body = r.json()
    # Buy EUR at 1.05 when mocked spot is ~1.08 → positive MTM for Buy
    assert body["mark_to_market"] is not None
    assert Decimal(body["mark_to_market"]) > 0


def test_forecast_returns_simulation(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    tid = r.json()["id"]
    r = client.get(f"/trades/{tid}/forecast?num_simulations=200&seed=7")
    assert r.status_code == 200
    body = r.json()
    assert body["num_simulations"] == 200
    assert body["horizon_days"] > 0
    assert len(body["path"]) >= 1
    # P&L percentiles should bracket the mean
    assert Decimal(body["pnl_p05"]) <= Decimal(body["pnl_mean"]) <= Decimal(body["pnl_p95"])


def test_forecast_is_deterministic_with_seed(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    tid = r.json()["id"]
    a = client.get(f"/trades/{tid}/forecast?num_simulations=200&seed=42").json()
    b = client.get(f"/trades/{tid}/forecast?num_simulations=200&seed=42").json()
    assert a["pnl_mean"] == b["pnl_mean"]
    assert a["final_spot_mean"] == b["final_spot_mean"]
