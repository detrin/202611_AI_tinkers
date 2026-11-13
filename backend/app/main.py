"""App factory. Run: uv run uvicorn backend.app.main:app --reload"""
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.routers import imports, inspirations, outfits, shopping, styles, system, users, wardrobe
from .container import Container, build_container
from .errors import DomainError

ROUTERS = (system, users, wardrobe, imports, inspirations, styles, shopping, outfits)


def create_app(container_factory: Callable[[], Container] = build_container) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container_factory()
        yield

    app = FastAPI(title="Wardrobe stylist API", version="0.2", lifespan=lifespan)
    for module in ROUTERS:
        app.include_router(module.router)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    return app


app = create_app()
