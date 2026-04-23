"""Exhaustive check of the state-machine transition table."""

from decimal import Decimal
from itertools import product

import pytest

from trade_approval.domain.details import TradeDetails
from trade_approval.domain.errors import IllegalTransitionError
from trade_approval.domain.states import Action, State
from trade_approval.domain.workflow import TRANSITIONS, allowed_actions
from trade_approval.services.trade_service import TradeService


USER_ACTIONS = [a for a in Action if a != Action.CREATE]
ALL_STATES = list(State)


def _drive(service: TradeService, details: TradeDetails, path: list[tuple[str, str, dict]]):
    """Apply a sequence of (user, action_name, kwargs) to reach a given state."""
    trade = service.create_trade("requester", details)
    for user, action_name, kwargs in path:
        getattr(service, action_name)(trade.id, user, **kwargs)
    return service.get_trade(trade.id)


# Map each reachable state to a sequence that gets there.
STATE_PATHS: dict[State, list[tuple[str, str, dict]]] = {
    State.DRAFT: [],
    State.PENDING_APPROVAL: [
        ("requester", "submit", {}),
    ],
    State.NEEDS_REAPPROVAL: [
        ("requester", "submit", {}),
        ("approver", "update", {"updates": {"notional_amount": Decimal("2000000")}}),
    ],
    State.APPROVED: [
        ("requester", "submit", {}),
        ("approver", "approve", {}),
    ],
    State.SENT_TO_COUNTERPARTY: [
        ("requester", "submit", {}),
        ("approver", "approve", {}),
        ("approver", "send_to_execute", {}),
    ],
    State.EXECUTED: [
        ("requester", "submit", {}),
        ("approver", "approve", {}),
        ("approver", "send_to_execute", {}),
        ("requester", "book", {"strike": Decimal("1.10")}),
    ],
    State.CANCELLED: [
        ("requester", "submit", {}),
        ("requester", "cancel", {}),
    ],
}


@pytest.mark.parametrize("state", ALL_STATES)
def test_reach_every_state(service, sample_details, state):
    trade = _drive(service, sample_details, STATE_PATHS[state])
    assert trade.state == state


@pytest.mark.parametrize("state,action", list(product(ALL_STATES, USER_ACTIONS)))
def test_transition_table_is_authoritative(service, sample_details, state, action):
    """Every (state, action) not in TRANSITIONS must raise IllegalTransition."""
    trade = _drive(service, sample_details, STATE_PATHS[state])

    # Pick a user with max privilege so auth doesn't mask the transition check.
    requester = trade.requester_id
    approver = trade.approver_id or "approver"

    def call(user):
        if action == Action.SUBMIT:
            service.submit(trade.id, user)
        elif action == Action.APPROVE:
            service.approve(trade.id, user)
        elif action == Action.CANCEL:
            service.cancel(trade.id, user)
        elif action == Action.SEND_TO_EXECUTE:
            service.send_to_execute(trade.id, user)
        elif action == Action.UPDATE:
            service.update(trade.id, user, {"notional_amount": Decimal("1500000")})
        elif action == Action.BOOK:
            service.book(trade.id, user, strike=Decimal("1.10"))

    is_legal = (state, action) in TRANSITIONS

    if is_legal:
        # One of the privileged users must be able to drive this — we just
        # assert the transition check passes for at least one reasonable actor.
        # (Authorization is covered in the dedicated auth test module.)
        for user in (requester, approver, "outsider"):
            try:
                call(user)
                return  # succeeded — legal transition works
            except IllegalTransitionError:
                pytest.fail(f"Legal transition ({state}, {action}) raised")
            except Exception:
                continue
        pytest.fail(f"No user could perform legal transition ({state}, {action})")
    else:
        with pytest.raises(IllegalTransitionError):
            call(requester)


def test_allowed_actions_matches_transition_table():
    for state in ALL_STATES:
        expected = {a for (s, a) in TRANSITIONS if s == state}
        assert set(allowed_actions(state)) == expected


def test_terminal_states_allow_no_actions():
    assert allowed_actions(State.EXECUTED) == []
    assert allowed_actions(State.CANCELLED) == []
    assert State.EXECUTED.is_terminal
    assert State.CANCELLED.is_terminal
