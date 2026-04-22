from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .database import init_db
from .routers import bid, campaigns, health, proof, wallet


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(wallet.router)
    app.include_router(campaigns.router)
    app.include_router(bid.router)
    app.include_router(proof.router)
    return app


app = create_app()
