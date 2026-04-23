"""In-memory trade repository, thread-safe via RLock."""

import threading
from typing import Optional

from ..domain.errors import TradeNotFoundError
from ..domain.states import State
from ..domain.trade import Trade


class InMemoryTradeRepository:
    """Simple dict-backed store. Trade aggregates are mutated in place; the
    lock protects read-modify-write sequences in the service layer.
    """

    def __init__(self) -> None:
        self._trades: dict[str, Trade] = {}
        self.lock = threading.RLock()

    def save(self, trade: Trade) -> None:
        with self.lock:
            self._trades[trade.id] = trade

    def get(self, trade_id: str) -> Trade:
        with self.lock:
            if trade_id not in self._trades:
                raise TradeNotFoundError(f"Trade {trade_id} not found")
            return self._trades[trade_id]

    def list(
        self,
        state: Optional[State] = None,
        user_id: Optional[str] = None,
    ) -> list[Trade]:
        with self.lock:
            result = list(self._trades.values())
        if state is not None:
            result = [t for t in result if t.state == state]
        if user_id is not None:
            result = [t for t in result if any(e.user_id == user_id for e in t.events)]
        return result
