"""HTTP routes for the trade approval workflow."""

from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from ..analytics.risk import Forecast, RiskMetrics, compute_risk, forecast
from ..domain.details import TradeDetails
from ..domain.diff import diff_details
from ..domain.states import State
from ..domain.trade import Trade
from ..domain.workflow import allowed_actions
from ..services.trade_service import TradeService
from .deps import get_service, get_user
from .schemas import (
    ActionRequest,
    BookRequest,
    DiffResponse,
    EventResponse,
    TradeCreateRequest,
    TradeResponse,
    TradeUpdateRequest,
    TradeWithHistoryResponse,
)

router = APIRouter(prefix="/trades", tags=["trades"])


def _to_response(trade: Trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        state=trade.state,
        current_version=trade.current_version,
        requester_id=trade.requester_id,
        approver_id=trade.approver_id,
        details=trade.current_details,
        allowed_actions=allowed_actions(trade.state),
    )


# ---------------------------------------------------------------------------
# Creation and reads
# ---------------------------------------------------------------------------


@router.post("", response_model=TradeResponse, status_code=201)
def create_trade(
    req: TradeCreateRequest,
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    details = TradeDetails(**req.model_dump())
    trade = service.create_trade(user_id, details)
    return _to_response(trade)


@router.get("", response_model=list[TradeResponse])
def list_trades(
    state: Optional[State] = Query(None),
    user_id: Optional[str] = Query(None),
    service: TradeService = Depends(get_service),
) -> list[TradeResponse]:
    return [_to_response(t) for t in service.list_trades(state=state, user_id=user_id)]


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(
    trade_id: str,
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    return _to_response(service.get_trade(trade_id))


@router.get("/{trade_id}/history", response_model=TradeWithHistoryResponse)
def get_history(
    trade_id: str,
    service: TradeService = Depends(get_service),
) -> TradeWithHistoryResponse:
    trade = service.get_trade(trade_id)
    events = [
        EventResponse(**e.model_dump(exclude={"details_snapshot"}))
        for e in trade.events
    ]
    base = _to_response(trade).model_dump()
    return TradeWithHistoryResponse(**base, history=events)


@router.get("/{trade_id}/versions/{version}", response_model=TradeDetails)
def get_version(
    trade_id: str,
    version: int,
    service: TradeService = Depends(get_service),
) -> TradeDetails:
    trade = service.get_trade(trade_id)
    return trade.details_at_version(version)


@router.get("/{trade_id}/diff", response_model=DiffResponse)
def get_diff(
    trade_id: str,
    from_version: int = Query(..., alias="from", ge=1),
    to_version: int = Query(..., alias="to", ge=1),
    service: TradeService = Depends(get_service),
) -> DiffResponse:
    trade = service.get_trade(trade_id)
    before = trade.details_at_version(from_version)
    after = trade.details_at_version(to_version)
    return DiffResponse(
        trade_id=trade_id,
        from_version=from_version,
        to_version=to_version,
        changes=diff_details(before, after),
    )


# ---------------------------------------------------------------------------
# Workflow actions
# ---------------------------------------------------------------------------


@router.post("/{trade_id}/submit", response_model=TradeResponse)
def submit(
    trade_id: str,
    body: Optional[ActionRequest] = Body(default=None),
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    note = body.note if body else None
    return _to_response(service.submit(trade_id, user_id, note=note))


@router.post("/{trade_id}/approve", response_model=TradeResponse)
def approve(
    trade_id: str,
    body: Optional[ActionRequest] = Body(default=None),
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    note = body.note if body else None
    return _to_response(service.approve(trade_id, user_id, note=note))


@router.post("/{trade_id}/cancel", response_model=TradeResponse)
def cancel(
    trade_id: str,
    body: Optional[ActionRequest] = Body(default=None),
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    note = body.note if body else None
    return _to_response(service.cancel(trade_id, user_id, note=note))


@router.post("/{trade_id}/send-to-execute", response_model=TradeResponse)
def send_to_execute(
    trade_id: str,
    body: Optional[ActionRequest] = Body(default=None),
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    note = body.note if body else None
    return _to_response(service.send_to_execute(trade_id, user_id, note=note))


@router.patch("/{trade_id}", response_model=TradeResponse)
def update_trade(
    trade_id: str,
    body: TradeUpdateRequest,
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    updates = body.model_dump(exclude_none=True, exclude={"note"})
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    trade = service.update(trade_id, user_id, updates, note=body.note)
    return _to_response(trade)


@router.post("/{trade_id}/book", response_model=TradeResponse)
def book(
    trade_id: str,
    body: BookRequest,
    user_id: str = Depends(get_user),
    service: TradeService = Depends(get_service),
) -> TradeResponse:
    trade = service.book(trade_id, user_id, strike=body.strike, note=body.note)
    return _to_response(trade)


# ---------------------------------------------------------------------------
# Analytics (extras beyond the brief)
# ---------------------------------------------------------------------------


@router.get("/{trade_id}/risk", response_model=RiskMetrics)
def get_risk(
    trade_id: str,
    service: TradeService = Depends(get_service),
) -> RiskMetrics:
    return compute_risk(service.get_trade(trade_id))


@router.get("/{trade_id}/forecast", response_model=Forecast)
def get_forecast(
    trade_id: str,
    num_simulations: int = Query(1000, ge=100, le=10_000),
    num_steps: int = Query(10, ge=1, le=50),
    seed: Optional[int] = Query(None),
    service: TradeService = Depends(get_service),
) -> Forecast:
    return forecast(
        service.get_trade(trade_id),
        num_simulations=num_simulations,
        num_steps=num_steps,
        seed=seed,
    )
