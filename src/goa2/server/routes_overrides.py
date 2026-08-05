"""Consensus-override REST endpoints (schema catalogue + decision history)."""

from __future__ import annotations

from fastapi import APIRouter

from goa2.engine.overrides import OVERRIDE_OPS
from goa2.server.models import OverrideOpSchema, OverrideSchemaResponse

router = APIRouter(tags=["overrides"])


@router.get("/overrides/schema", response_model=OverrideSchemaResponse)
async def get_override_schema() -> OverrideSchemaResponse:
    """The op catalogue, auto-derived from the registry.

    Static and game-independent (like /heroes): clients fetch once and cache.
    A hand-written catalogue would drift the first time an op is added.
    """
    return OverrideSchemaResponse(
        ops=[
            OverrideOpSchema(
                name=op.name,
                family=op.family,
                label=op.label,
                description=op.description,
                args_schema=op.args_model.model_json_schema(),
            )
            for op in sorted(OVERRIDE_OPS.values(), key=lambda o: (o.family, o.name))
        ]
    )
