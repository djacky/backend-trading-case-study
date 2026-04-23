"""Immutable audit events appended to a trade."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .details import TradeDetails
from .states import Action, State


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TradeEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    action: Action
    user_id: str
    timestamp: datetime
    from_state: Optional[State]
    to_state: State
    details_version: int
    details_snapshot: TradeDetails
    note: Optional[str] = None
