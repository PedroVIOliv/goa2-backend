"""GET /heroes endpoint."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from goa2.data.heroes.registry import HeroRegistry
from goa2.server.models import HeroMetadata

router = APIRouter(tags=["heroes"])


@router.get("/heroes", response_model=List[str])
async def list_heroes() -> List[str]:
    return HeroRegistry.list_heroes()


@router.get("/heroes/metadata", response_model=List[HeroMetadata])
async def list_hero_metadata() -> List[dict]:
    return HeroRegistry.list_hero_metadata()
