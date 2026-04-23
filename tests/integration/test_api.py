"""Broader API-level behaviour: errors, listing, validation mapping."""

from decimal import Decimal


HDR = {"X-User-Id": "alice"}


def test_missing_user_header_rejected(client, sample_payload):
    r = client.post("/trades", json=sample_payload)
    assert r.status_code == 422


def test_invalid_currency_returns_422(client, sample_payload):
    sample_payload["notional_currency"] = "ZZZ"
    r = client.post("/trades", json=sample_payload, headers=HDR)
    assert r.status_code == 422


def test_illegal_transition_returns_409(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    # Cannot approve a Draft
    r = client.post(f"/trades/{trade_id}/approve", headers={"X-User-Id": "bob"})
    assert r.status_code == 409


def test_unauthorized_returns_403(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    client.post(f"/trades/{trade_id}/submit", headers=HDR)
    # Alice can't approve her own trade
    r = client.post(f"/trades/{trade_id}/approve", headers=HDR)
    assert r.status_code == 403


def test_trade_not_found_returns_404(client):
    r = client.get("/trades/nonexistent-id")
    assert r.status_code == 404


def test_version_not_found_returns_404(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    r = client.get(f"/trades/{trade_id}/versions/99")
    assert r.status_code == 404


def test_list_trades_with_filters(client, sample_payload):
    # Create 2 trades under alice
    r1 = client.post("/trades", json=sample_payload, headers=HDR)
    r2 = client.post("/trades", json=sample_payload, headers=HDR)
    # Submit first
    client.post(f"/trades/{r1.json()['id']}/submit", headers=HDR)

    # Filter by state
    r = client.get("/trades?state=Draft")
    assert r.status_code == 200
    ids = [t["id"] for t in r.json()]
    assert r2.json()["id"] in ids
    assert r1.json()["id"] not in ids

    r = client.get("/trades?state=PendingApproval")
    ids = [t["id"] for t in r.json()]
    assert r1.json()["id"] in ids

    # Filter by user
    r = client.get("/trades?user_id=alice")
    assert len(r.json()) == 2

    r = client.get("/trades?user_id=someone-else")
    assert r.json() == []


def test_empty_update_is_rejected(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    client.post(f"/trades/{trade_id}/submit", headers=HDR)
    r = client.patch(
        f"/trades/{trade_id}",
        json={},
        headers={"X-User-Id": "bob"},
    )
    assert r.status_code == 400


def test_cancel_from_pending_approval(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    client.post(f"/trades/{trade_id}/submit", headers=HDR)
    r = client.post(f"/trades/{trade_id}/cancel", headers=HDR)
    assert r.status_code == 200
    assert r.json()["state"] == "Cancelled"
    assert r.json()["allowed_actions"] == []


def test_action_accepts_optional_note(client, sample_payload):
    r = client.post("/trades", json=sample_payload, headers=HDR)
    trade_id = r.json()["id"]
    r = client.post(
        f"/trades/{trade_id}/submit",
        json={"note": "urgent"},
        headers=HDR,
    )
    assert r.status_code == 200
    r = client.get(f"/trades/{trade_id}/history")
    submit_event = next(e for e in r.json()["history"] if e["action"] == "Submit")
    assert submit_event["note"] == "urgent"


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
