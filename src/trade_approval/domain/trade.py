"""Event-sourced Trade aggregate."""

import uuid
from typing import Optional

from .details import TradeDetails
from .errors import VersionNotFoundError
from .events import TradeEvent, utc_now
from .states import Action, State


class Trade:
    """A trade is a sequence of immutable events; state is derived from them."""

    def __init__(self, trade_id: str, events: list[TradeEvent]):
        if not events:
            raise ValueError("Trade must have at least one event")
        self.id = trade_id
        self.events: list[TradeEvent] = list(events)

    @classmethod
    def new(cls, creator_id: str, details: TradeDetails) -> "Trade":
        """Create a brand-new trade in Draft state."""
        trade_id = str(uuid.uuid4())
        initial = TradeEvent(
            seq=1,
            action=Action.CREATE,
            user_id=creator_id,
            timestamp=utc_now(),
            from_state=None,
            to_state=State.DRAFT,
            details_version=1,
            details_snapshot=details,
        )
        return cls(trade_id, [initial])

    @property
    def state(self) -> State:
        return self.events[-1].to_state

    @property
    def current_details(self) -> TradeDetails:
        return self.events[-1].details_snapshot

    @property
    def current_version(self) -> int:
        return self.events[-1].details_version

    @property
    def max_version(self) -> int:
        return max(e.details_version for e in self.events)

    @property
    def requester_id(self) -> str:
        # The user who created the trade is the requester.
        return self.events[0].user_id

    @property
    def approver_id(self) -> Optional[str]:
        # The first user (other than the requester) to act in PendingApproval
        # becomes the approver for the lifetime of the trade.
        requester = self.requester_id
        for event in self.events:
            if event.from_state == State.PENDING_APPROVAL and event.user_id != requester:
                return event.user_id
        return None

    def append(self, event: TradeEvent) -> None:
        self.events.append(event)

    def details_at_version(self, version: int) -> TradeDetails:
        """Return the trade details snapshot at a specific version."""
        for event in self.events:
            if event.details_version == version:
                return event.details_snapshot
        raise VersionNotFoundError(f"Version {version} not found for trade {self.id}")
