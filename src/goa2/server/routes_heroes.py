"""GET /heroes endpoint."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from goa2.data.heroes.registry import HeroRegistry

router = APIRouter(tags=["heroes"])


@router.get("/heroes", response_model=List[str])
async def list_heroes() -> List[str]:
    return HeroRegistry.list_heroes()
