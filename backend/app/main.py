import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers import (
    bid,
    campaigns,
    creatives,
    dashboard,
    health,
    markets,
    proof,
    wallet,
)
from .services.auto_play import run_auto_play_loop
from .services.batch_settler import run_batch_settler_loop


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop_event = asyncio.Event()
    auto_play_task = asyncio.create_task(run_auto_play_loop(stop_event))
    # Session 16.8: batch settler emits the actual on-chain transfers for
    # /proof + simulate-play + auto-play, all of which now just queue
    # pending Settlement rows. Shares the stop_event so SIGTERM cleanly
    # winds down both loops.
    batch_settler_task = asyncio.create_task(run_batch_settler_loop(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        for task in (auto_play_task, batch_settler_task):
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-PAYMENT-RESPONSE"],
    )
    app.include_router(health.router)
    app.include_router(wallet.router)
    app.include_router(campaigns.router)
    app.include_router(creatives.router)
    app.include_router(dashboard.router)
    app.include_router(markets.router)
    app.include_router(bid.router)
    app.include_router(proof.router)
    return app


app = create_app()
