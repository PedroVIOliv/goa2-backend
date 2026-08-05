"""GET /heroes endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from goa2.data.heroes.registry import HeroRegistry
from goa2.server.models import HeroMetadata

router = APIRouter(tags=["heroes"])


@router.get("/heroes", response_model=list[str])
async def list_heroes(include_playtest: bool = False) -> list[str]:
    return HeroRegistry.list_heroes(include_playtest=include_playtest)


@router.get("/heroes/metadata", response_model=list[HeroMetadata])
async def list_hero_metadata(include_playtest: bool = False) -> list[dict]:
    return HeroRegistry.list_hero_metadata(include_playtest=include_playtest)
