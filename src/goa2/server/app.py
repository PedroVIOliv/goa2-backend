"""FastAPI application factory."""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from goa2.server.errors import (
    AlreadyCommittedError,
    CardNotInHandError,
    GameNotFoundError,
    InvalidPhaseError,
    NotYourTurnError,
)
from goa2.server.registry import GameRegistry
from goa2.server.routes_games import router as games_router
from goa2.server.routes_heroes import router as heroes_router
from goa2.server.ws import router as ws_router

logger = logging.getLogger(__name__)


def register_all_effects():
    """Auto-discover and import all hero effect modules."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    for script_path in scripts_dir.glob("*_effects.py"):
        module_name = f"goa2.scripts.{script_path.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"Failed to load effect module {module_name}: {e}")


register_all_effects()


@asynccontextmanager
async def lifespan(app: FastAPI):
    save_dir = os.environ.get("GOA2_SAVE_DIR", "data/games")
    registry = GameRegistry(save_dir=save_dir)
    count = registry.restore_all()
    if count:
        logger.info("Restored %d game(s) from %s", count, save_dir)
    app.state.registry = registry
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="GoA2 API", version="0.1.0", lifespan=lifespan)

    # CORS
    allowed_origins = os.environ.get("GOA2_CORS_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Routers
    app.include_router(heroes_router)
    app.include_router(games_router)
    app.include_router(ws_router)

    # Exception handlers
    @app.exception_handler(GameNotFoundError)
    async def _game_not_found(request: Request, exc: GameNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AlreadyCommittedError)
    async def _already_committed(request: Request, exc: AlreadyCommittedError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(CardNotInHandError)
    async def _card_not_in_hand(request: Request, exc: CardNotInHandError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidPhaseError)
    async def _invalid_phase(request: Request, exc: InvalidPhaseError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(NotYourTurnError)
    async def _not_your_turn(request: Request, exc: NotYourTurnError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app
