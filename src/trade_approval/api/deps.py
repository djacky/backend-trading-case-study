"""FastAPI dependency injection wiring."""

from functools import lru_cache

from fastapi import Depends, Header

from ..repo.in_memory import InMemoryTradeRepository
from ..services.trade_service import TradeService


@lru_cache(maxsize=1)
def get_repo() -> InMemoryTradeRepository:
    """Process-wide singleton repo. Override in tests via dependency_overrides."""
    return InMemoryTradeRepository()


def get_service(
    repo: InMemoryTradeRepository = Depends(get_repo),
) -> TradeService:
    return TradeService(repo)


def get_user(x_user_id: str = Header(..., alias="X-User-Id", min_length=1)) -> str:
    """Prototype auth — the caller identifies themselves via X-User-Id header."""
    return x_user_id
