"""End-to-end tests mirroring the three example scenarios from the case study PDF."""

from decimal import Decimal


def _create(client, payload, user="User1"):
    return client.post("/trades", json=payload, headers={"X-User-Id": user})


def _action(client, trade_id, action, user, body=None):
    return client.post(
        f"/trades/{trade_id}/{action}",
        json=body,
        headers={"X-User-Id": user},
    )


def test_scenario_1_submit_and_approve(client, sample_payload):
    # 1. Create + Submit (User1, Draft -> PendingApproval)
    r = _create(client, sample_payload, user="User1")
    assert r.status_code == 201
    trade_id = r.json()["id"]
    assert r.json()["state"] == "Draft"

    r = _action(client, trade_id, "submit", "User1")
    assert r.status_code == 200
    assert r.json()["state"] == "PendingApproval"

    # 2. Approve (User2, PendingApproval -> Approved)
    r = _action(client, trade_id, "approve", "User2")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "Approved"
    assert body["requester_id"] == "User1"
    assert body["approver_id"] == "User2"


def test_scenario_2_update_triggers_reapproval(client, sample_payload):
    r = _create(client, sample_payload, user="User1")
    trade_id = r.json()["id"]
    _action(client, trade_id, "submit", "User1")

    # Approver (User2) updates the notional amount
    r = client.patch(
        f"/trades/{trade_id}",
        json={"notional_amount": "1200000"},
        headers={"X-User-Id": "User2"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "NeedsReapproval"
    assert body["current_version"] == 2
    assert body["details"]["notional_amount"] == "1200000"

    # Requester reapproves
    r = _action(client, trade_id, "approve", "User1")
    assert r.status_code == 200
    assert r.json()["state"] == "Approved"


def test_scenario_3_execution(client, sample_payload):
    r = _create(client, sample_payload, user="User1")
    trade_id = r.json()["id"]
    _action(client, trade_id, "submit", "User1")
    _action(client, trade_id, "approve", "User2")

    r = _action(client, trade_id, "send-to-execute", "User2")
    assert r.status_code == 200
    assert r.json()["state"] == "SentToCounterparty"

    r = client.post(
        f"/trades/{trade_id}/book",
        json={"strike": "1.10"},
        headers={"X-User-Id": "User1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "Executed"
    assert body["details"]["strike"] == "1.10"


def test_scenario_4_history_and_diff(client, sample_payload):
    r = _create(client, sample_payload, user="User1")
    trade_id = r.json()["id"]
    _action(client, trade_id, "submit", "User1")

    # Update to create version 2
    client.patch(
        f"/trades/{trade_id}",
        json={"notional_amount": "1200000"},
        headers={"X-User-Id": "User2"},
    )

    # History is a tabular list of every action
    r = client.get(f"/trades/{trade_id}/history")
    assert r.status_code == 200
    history = r.json()["history"]
    actions = [e["action"] for e in history]
    assert actions == ["Create", "Submit", "Update"]
    assert all("timestamp" in e and "user_id" in e for e in history)

    # Trade details at version 1 (original)
    r = client.get(f"/trades/{trade_id}/versions/1")
    assert r.status_code == 200
    assert r.json()["notional_amount"] == "1000000"

    # Trade details at version 2 (after update)
    r = client.get(f"/trades/{trade_id}/versions/2")
    assert r.status_code == 200
    assert r.json()["notional_amount"] == "1200000"

    # Diff between versions
    r = client.get(f"/trades/{trade_id}/diff?from=1&to=2")
    assert r.status_code == 200
    body = r.json()
    # Tuple serialized as list by JSON
    assert body["changes"]["notional_amount"] == ["1000000", "1200000"]
    assert len(body["changes"]) == 1  # only notional changed
