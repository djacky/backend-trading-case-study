"""Domain-level exceptions. API layer maps these to HTTP status codes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .states import Action, State


class DomainError(Exception):
    """Base for domain exceptions."""


class TradeNotFoundError(DomainError):
    pass


class VersionNotFoundError(DomainError):
    pass


class IllegalTransitionError(DomainError):
    def __init__(self, state: "State", action: "Action"):
        super().__init__(
            f"Action '{action.value}' is not allowed in state '{state.value}'"
        )
        self.state = state
        self.action = action


class UnauthorizedActionError(DomainError):
    pass
