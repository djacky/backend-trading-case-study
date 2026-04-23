"""HTTP request/response DTOs."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ..domain.details import TradeDetails
from ..domain.states import Action, State


class TradeCreateRequest(BaseModel):
    trading_entity: str
    counterparty: str
    direction: Literal["Buy", "Sell"]
    style: Literal["Forward"] = "Forward"
    notional_currency: str
    notional_amount: Decimal
    underlying: tuple[str, str]
    trade_date: date
    value_date: date
    delivery_date: date


class TradeUpdateRequest(BaseModel):
    """Partial update — only populated fields are applied."""

    trading_entity: Optional[str] = None
    counterparty: Optional[str] = None
    direction: Optional[Literal["Buy", "Sell"]] = None
    notional_currency: Optional[str] = None
    notional_amount: Optional[Decimal] = None
    underlying: Optional[tuple[str, str]] = None
    trade_date: Optional[date] = None
    value_date: Optional[date] = None
    delivery_date: Optional[date] = None
    note: Optional[str] = None


class BookRequest(BaseModel):
    strike: Decimal = Field(gt=0)
    note: Optional[str] = None


class ActionRequest(BaseModel):
    note: Optional[str] = None


class EventResponse(BaseModel):
    seq: int
    action: Action
    user_id: str
    timestamp: datetime
    from_state: Optional[State]
    to_state: State
    details_version: int
    note: Optional[str]


class TradeResponse(BaseModel):
    id: str
    state: State
    current_version: int
    requester_id: str
    approver_id: Optional[str]
    details: TradeDetails
    allowed_actions: list[Action]


class TradeWithHistoryResponse(TradeResponse):
    history: list[EventResponse]


class DiffResponse(BaseModel):
    trade_id: str
    from_version: int
    to_version: int
    changes: dict[str, tuple[Any, Any]]
