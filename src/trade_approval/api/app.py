"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from ..domain.errors import (
    DomainError,
    IllegalTransitionError,
    TradeNotFoundError,
    UnauthorizedActionError,
    VersionNotFoundError,
)
from .routes_trades import router as trades_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trade Approval API",
        version="0.1.0",
        description=(
            "A workflow API for submitting, approving, updating, executing "
            "and booking forward trades, with a full audit log and a risk "
            "analytics layer (MTM + Monte Carlo P&L forecast)."
        ),
    )
    app.include_router(trades_router)

    @app.exception_handler(TradeNotFoundError)
    async def _trade_not_found(_req: Request, exc: TradeNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(VersionNotFoundError)
    async def _version_not_found(
        _req: Request, exc: VersionNotFoundError
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IllegalTransitionError)
    async def _illegal_transition(
        _req: Request, exc: IllegalTransitionError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(UnauthorizedActionError)
    async def _unauthorized(
        _req: Request, exc: UnauthorizedActionError
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _domain_error(_req: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PydanticValidationError)
    async def _pydantic_error(
        _req: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        # Domain-level Pydantic validation failure (raised inside handlers).
        # include_url=False keeps output tidy; input is stringified to keep
        # it JSON-safe (raw input may contain Decimal etc.).
        errors = exc.errors(include_url=False)
        for e in errors:
            if "input" in e:
                e["input"] = repr(e["input"])
            if "ctx" in e:
                e["ctx"] = {k: repr(v) for k, v in e["ctx"].items()}
        return JSONResponse(status_code=422, content={"detail": errors})

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
