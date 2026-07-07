from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from goa2.domain.models import FilterType
from goa2.domain.state import GameState

# Context key under which the batch completability search publishes the hexes
# its current hypothesis treats as empty (tokens whose removal is assumed).
# The search cannot mutate the board while exploring assignments, so filters
# that derive emptiness themselves (e.g. FarthestEmptyAdjacentFilter) must
# read this hint to stay consistent with the hypothesis. Absent outside the
# search, where the live board is authoritative.
BATCH_FREED_HEXES_KEY = "_batch_freed_hexes"


class FilterCondition(BaseModel):
    """
    Base class for all selection filters.
    """

    # Nested filter lists (e.g. ``slot_filters``) can deserialize as this base
    # class when a containing model's schema predates the AnyFilter annotation
    # patch in step_types.py. Retaining unknown fields keeps that lossless so
    # revalidate_filters() can recover the concrete filter later.
    model_config = ConfigDict(extra="allow")

    type: FilterType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError


def revalidate_filter(raw: Any) -> FilterCondition:
    """Recover a concrete filter from a degraded round-trip artifact.

    Filters nested two levels deep (a filter list inside a filter/step that is
    itself a union member) may deserialize as base ``FilterCondition``
    instances or plain dicts. This re-validates them against the ``AnyFilter``
    union; concrete instances pass through untouched.
    """
    if type(raw) is FilterCondition:
        raw = raw.model_dump(mode="json")
    if isinstance(raw, dict):
        from pydantic import TypeAdapter

        from goa2.engine.step_types import AnyFilter

        return TypeAdapter(AnyFilter).validate_python(raw)
    return raw


def revalidate_filters(raw_filters: list[Any]) -> list[FilterCondition]:
    """Apply :func:`revalidate_filter` to a list of filters."""
    return [revalidate_filter(raw) for raw in raw_filters]


def dump_filter_grid(value: list[list[Any]]) -> list[list[Any]]:
    """Serialize a nested filter grid (``list[list[FilterCondition]]``) by
    instance, not by schema.

    Schema-driven serialization of these fields can degrade to the base
    ``FilterCondition`` schema (dropping every subclass field) depending on
    module import order; dumping each instance through its own class is
    deterministic. Used as a ``field_serializer`` for ``slot_filters`` fields.
    """
    return [
        [f.model_dump(mode="json") if isinstance(f, FilterCondition) else f for f in slot]
        for slot in value
    ]


# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------
