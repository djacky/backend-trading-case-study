"""Authorization rules on each transition."""

from decimal import Decimal

import pytest

from trade_approval.domain.errors import UnauthorizedActionError


def test_only_requester_can_submit(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    with pytest.raises(UnauthorizedActionError):
        service.submit(trade.id, "bob")
    service.submit(trade.id, "alice")


def test_requester_cannot_approve_own_trade(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    with pytest.raises(UnauthorizedActionError, match="4-eyes"):
        service.approve(trade.id, "alice")


def test_requester_cannot_update_own_trade(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    with pytest.raises(UnauthorizedActionError, match="4-eyes"):
        service.update(trade.id, "alice", {"notional_amount": Decimal("1500000")})


def test_third_party_cannot_hijack_approver_role(service, sample_details):
    """Once Bob updates, Charlie cannot step in as a second approver."""
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    service.update(trade.id, "bob", {"notional_amount": Decimal("1200000")})
    service.approve(trade.id, "alice")  # Alice reapproves → Approved
    with pytest.raises(UnauthorizedActionError):
        service.send_to_execute(trade.id, "charlie")


def test_needs_reapproval_requires_original_requester(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    service.update(trade.id, "bob", {"notional_amount": Decimal("1200000")})
    # Bob can't self-approve even though he's the approver
    with pytest.raises(UnauthorizedActionError):
        service.approve(trade.id, "bob")
    # Outsider can't either
    with pytest.raises(UnauthorizedActionError):
        service.approve(trade.id, "charlie")
    # Only Alice can
    service.approve(trade.id, "alice")


def test_send_to_execute_requires_approver(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    service.approve(trade.id, "bob")
    with pytest.raises(UnauthorizedActionError):
        service.send_to_execute(trade.id, "alice")  # requester can't
    with pytest.raises(UnauthorizedActionError):
        service.send_to_execute(trade.id, "charlie")  # outsider can't
    service.send_to_execute(trade.id, "bob")


def test_book_allows_requester_or_approver(service, sample_details):
    # Approver books
    t1 = service.create_trade("alice", sample_details)
    service.submit(t1.id, "alice")
    service.approve(t1.id, "bob")
    service.send_to_execute(t1.id, "bob")
    service.book(t1.id, "bob", strike=Decimal("1.10"))

    # Requester books the next one
    t2 = service.create_trade("alice", sample_details)
    service.submit(t2.id, "alice")
    service.approve(t2.id, "bob")
    service.send_to_execute(t2.id, "bob")
    service.book(t2.id, "alice", strike=Decimal("1.10"))

    # Outsider cannot
    t3 = service.create_trade("alice", sample_details)
    service.submit(t3.id, "alice")
    service.approve(t3.id, "bob")
    service.send_to_execute(t3.id, "bob")
    with pytest.raises(UnauthorizedActionError):
        service.book(t3.id, "charlie", strike=Decimal("1.10"))


def test_cancel_allows_either_party(service, sample_details):
    trade = service.create_trade("alice", sample_details)
    service.submit(trade.id, "alice")
    service.approve(trade.id, "bob")
    # Outsider cannot
    with pytest.raises(UnauthorizedActionError):
        service.cancel(trade.id, "charlie")
    # Approver can
    service.cancel(trade.id, "bob")
