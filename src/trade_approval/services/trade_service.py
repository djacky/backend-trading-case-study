"""Orchestrates trade actions, enforcing transitions and authorization.

The service is the public library surface — callable without the HTTP layer.
"""

from decimal import Decimal
from typing import Any, Optional

from ..domain.errors import UnauthorizedActionError
from ..domain.events import TradeEvent, utc_now
from ..domain.states import Action, State
from ..domain.trade import Trade
from ..domain.details import TradeDetails
from ..domain.workflow import AuthRule, Transition, lookup
from ..repo.in_memory import InMemoryTradeRepository


class TradeService:
    def __init__(self, repo: InMemoryTradeRepository):
        self._repo = repo

    # ---------- Reads ----------

    def get_trade(self, trade_id: str) -> Trade:
        return self._repo.get(trade_id)

    def list_trades(
        self,
        state: Optional[State] = None,
        user_id: Optional[str] = None,
    ) -> list[Trade]:
        return self._repo.list(state=state, user_id=user_id)

    # ---------- Creation ----------

    def create_trade(self, creator_id: str, details: TradeDetails) -> Trade:
        trade = Trade.new(creator_id, details)
        self._repo.save(trade)
        return trade

    # ---------- Simple transitions (no payload) ----------

    def submit(self, trade_id: str, user_id: str, note: Optional[str] = None) -> Trade:
        return self._apply_simple(trade_id, Action.SUBMIT, user_id, note)

    def approve(self, trade_id: str, user_id: str, note: Optional[str] = None) -> Trade:
        return self._apply_simple(trade_id, Action.APPROVE, user_id, note)

    def cancel(self, trade_id: str, user_id: str, note: Optional[str] = None) -> Trade:
        return self._apply_simple(trade_id, Action.CANCEL, user_id, note)

    def send_to_execute(
        self, trade_id: str, user_id: str, note: Optional[str] = None
    ) -> Trade:
        return self._apply_simple(trade_id, Action.SEND_TO_EXECUTE, user_id, note)

    # ---------- Transitions that also update details ----------

    def update(
        self,
        trade_id: str,
        user_id: str,
        updates: dict[str, Any],
        note: Optional[str] = None,
    ) -> Trade:
        """Update trade details (approver-only) and move to NeedsReapproval."""
        with self._repo.lock:
            trade = self._repo.get(trade_id)
            transition = self._authorize(trade, Action.UPDATE, user_id)
            new_details = trade.current_details.with_updates(updates)
            trade.append(self._build_event(
                trade, Action.UPDATE, user_id, transition, new_details,
                bump_version=True, note=note,
            ))
            self._repo.save(trade)
            return trade

    def book(
        self,
        trade_id: str,
        user_id: str,
        strike: Decimal,
        note: Optional[str] = None,
    ) -> Trade:
        """Book the trade with the executed strike. Moves to Executed state."""
        with self._repo.lock:
            trade = self._repo.get(trade_id)
            transition = self._authorize(trade, Action.BOOK, user_id)
            new_details = trade.current_details.with_updates({"strike": strike})
            trade.append(self._build_event(
                trade, Action.BOOK, user_id, transition, new_details,
                bump_version=True, note=note,
            ))
            self._repo.save(trade)
            return trade

    # ---------- Helpers ----------

    def _apply_simple(
        self,
        trade_id: str,
        action: Action,
        user_id: str,
        note: Optional[str],
    ) -> Trade:
        with self._repo.lock:
            trade = self._repo.get(trade_id)
            transition = self._authorize(trade, action, user_id)
            trade.append(self._build_event(
                trade, action, user_id, transition, trade.current_details,
                bump_version=False, note=note,
            ))
            self._repo.save(trade)
            return trade

    def _authorize(self, trade: Trade, action: Action, user_id: str) -> Transition:
        """Resolve the transition and enforce its auth rule. Raises on either failure."""
        transition = lookup(trade.state, action)
        self._check_auth(trade, user_id, transition.auth_rule)
        return transition

    @staticmethod
    def _build_event(
        trade: Trade,
        action: Action,
        user_id: str,
        transition: Transition,
        new_details: TradeDetails,
        bump_version: bool,
        note: Optional[str],
    ) -> TradeEvent:
        return TradeEvent(
            seq=len(trade.events) + 1,
            action=action,
            user_id=user_id,
            timestamp=utc_now(),
            from_state=trade.state,
            to_state=transition.to_state,
            details_version=trade.current_version + (1 if bump_version else 0),
            details_snapshot=new_details,
            note=note,
        )

    @staticmethod
    def _check_auth(trade: Trade, user_id: str, rule: AuthRule) -> None:
        requester = trade.requester_id
        approver = trade.approver_id

        if rule == AuthRule.REQUESTER:
            if user_id != requester:
                raise UnauthorizedActionError(
                    f"Only the requester ({requester}) can perform this action"
                )
        elif rule == AuthRule.NOT_REQUESTER:
            if user_id == requester:
                raise UnauthorizedActionError(
                    "Requester cannot act as approver (4-eyes principle)"
                )
            # Once an approver is established, no other user may take over.
            if approver is not None and user_id != approver:
                raise UnauthorizedActionError(
                    f"Only the existing approver ({approver}) may perform this action"
                )
        elif rule == AuthRule.APPROVER:
            if approver is None or user_id != approver:
                raise UnauthorizedActionError(
                    "Only the approver of record may perform this action"
                )
        elif rule == AuthRule.REQUESTER_OR_APPROVER:
            if user_id != requester and user_id != approver:
                raise UnauthorizedActionError(
                    "Only the requester or approver may perform this action"
                )
        else:  # pragma: no cover — exhaustive
            raise AssertionError(f"Unhandled auth rule: {rule}")
