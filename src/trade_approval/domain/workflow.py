"""State machine: the single source of truth for legal transitions."""

from enum import Enum

from .states import Action, State


class AuthRule(str, Enum):
    """Who is allowed to perform an action."""

    REQUESTER = "requester"
    NOT_REQUESTER = "not_requester"       # 4-eyes: anyone except the requester
    APPROVER = "approver"                  # the user who first acted as approver
    REQUESTER_OR_APPROVER = "requester_or_approver"


# (from_state, action) -> (to_state, auth_rule)
TRANSITIONS: dict[tuple[State, Action], tuple[State, AuthRule]] = {
    (State.DRAFT, Action.SUBMIT): (State.PENDING_APPROVAL, AuthRule.REQUESTER),

    (State.PENDING_APPROVAL, Action.APPROVE): (State.APPROVED, AuthRule.NOT_REQUESTER),
    (State.PENDING_APPROVAL, Action.UPDATE): (State.NEEDS_REAPPROVAL, AuthRule.NOT_REQUESTER),
    (State.PENDING_APPROVAL, Action.CANCEL): (State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.NEEDS_REAPPROVAL, Action.APPROVE): (State.APPROVED, AuthRule.REQUESTER),
    (State.NEEDS_REAPPROVAL, Action.CANCEL): (State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.APPROVED, Action.SEND_TO_EXECUTE): (State.SENT_TO_COUNTERPARTY, AuthRule.APPROVER),
    (State.APPROVED, Action.CANCEL): (State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),

    (State.SENT_TO_COUNTERPARTY, Action.BOOK): (State.EXECUTED, AuthRule.REQUESTER_OR_APPROVER),
    (State.SENT_TO_COUNTERPARTY, Action.CANCEL): (State.CANCELLED, AuthRule.REQUESTER_OR_APPROVER),
}


def allowed_actions(state: State) -> list[Action]:
    """Return the actions that are legal from a given state."""
    return [action for (s, action) in TRANSITIONS if s == state]
