"""Shared fixtures for unit and integration tests."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from trade_approval.api.app import create_app
from trade_approval.api.deps import get_repo
from trade_approval.domain.details import TradeDetails
from trade_approval.repo.in_memory import InMemoryTradeRepository
from trade_approval.services.trade_service import TradeService


@pytest.fixture
def repo() -> InMemoryTradeRepository:
    return InMemoryTradeRepository()


@pytest.fixture
def service(repo: InMemoryTradeRepository) -> TradeService:
    return TradeService(repo)


@pytest.fixture
def client(repo: InMemoryTradeRepository):
    app = create_app()
    app.dependency_overrides[get_repo] = lambda: repo
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_details() -> TradeDetails:
    today = date.today()
    return TradeDetails(
        trading_entity="ABC Corp",
        counterparty="XYZ Bank",
        direction="Buy",
        notional_currency="EUR",
        notional_amount=Decimal("1000000"),
        underlying=("EUR", "USD"),
        trade_date=today,
        value_date=today + timedelta(days=30),
        delivery_date=today + timedelta(days=32),
    )


@pytest.fixture
def sample_payload() -> dict:
    today = date.today()
    return {
        "trading_entity": "ABC Corp",
        "counterparty": "XYZ Bank",
        "direction": "Buy",
        "notional_currency": "EUR",
        "notional_amount": "1000000",
        "underlying": ["EUR", "USD"],
        "trade_date": today.isoformat(),
        "value_date": (today + timedelta(days=30)).isoformat(),
        "delivery_date": (today + timedelta(days=32)).isoformat(),
    }
