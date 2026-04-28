"""State machine: the single source of truth for legal transitions."""

from enum import Enum
from typing import NamedTuple

from .errors import IllegalTransitionError
from .states import Action, State


class AuthRule(str, Enum):
    """Who is allowed to perform an action."""

    REQUESTER = "requester"
    NOT_REQUESTER = "not_requester"       # 4-eyes: anyone except the requester
    APPROVER = "approver"                  # the user who first acted as approver
    REQUESTER_OR_APPROVER = "requester_or_approver"


class Transition(NamedTuple):
    to_state: State
    auth_rule: AuthRule


TRANSITIONS: dict[tuple[State, Action], Transition] = {
    (State.DRAFT, Action.SUBMIT):
        Transition(State.PENDING_APPROVAL, AuthRule.REQUESTER),

    (State.PENDING_APPROVAL, Action.APPROVE):
        Transition(State.APPROVED, AuthRule.NOT_REQUESTER),
    (State.PENDING_APPROVAL, Action.UPDATE):
        Transition(State.NEEDS_REAPPROVAL, AuthRule.NOT_REQUESTER),
    (State.PENDING_APPROVAL, Action.CANCEL):
        Transition(State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.NEEDS_REAPPROVAL, Action.APPROVE):
        Transition(State.APPROVED, AuthRule.REQUESTER),
    (State.NEEDS_REAPPROVAL, Action.CANCEL):
        Transition(State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.APPROVED, Action.SEND_TO_EXECUTE):
        Transition(State.SENT_TO_COUNTERPARTY, AuthRule.APPROVER),
    (State.APPROVED, Action.CANCEL):
        Transition(State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.SENT_TO_COUNTERPARTY, Action.BOOK):
        Transition(State.EXECUTED, AuthRule.REQUESTER_OR_APPROVER),
    (State.SENT_TO_COUNTERPARTY, Action.CANCEL):
        Transition(State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),
}


_ALLOWED_BY_STATE: dict[State, list[Action]] = {
    state: [a for (s, a) in TRANSITIONS if s == state] for state in State
}


def lookup(state: State, action: Action) -> Transition:
    """Resolve a transition or raise IllegalTransitionError."""
    try:
        return TRANSITIONS[(state, action)]
    except KeyError:
        raise IllegalTransitionError(state, action)


def allowed_actions(state: State) -> list[Action]:
    """Return the actions that are legal from a given state."""
    return list(_ALLOWED_BY_STATE[state])
