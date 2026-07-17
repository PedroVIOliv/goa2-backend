from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter

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

    # Retain unknown fields so legacy saves written through an older base-class
    # schema remain recoverable by revalidate_filters(). Current recursive
    # containers serialize and validate their children through AnyFilter.
    model_config = ConfigDict(extra="allow")

    type: FilterType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError


@lru_cache(maxsize=1)
def _any_filter_adapter() -> TypeAdapter:
    """Build the large registered filter adapter once, after registration completes."""
    from goa2.engine.step_types import AnyFilter

    return TypeAdapter(AnyFilter)


def revalidate_filter(raw: Any) -> FilterCondition:
    """Recover a concrete filter from serialized or legacy-degraded data.

    Recursive filter validators use this at every container boundary. Concrete
    instances pass through untouched; dictionaries and legacy base
    ``FilterCondition`` instances are validated against ``AnyFilter``.
    """
    if type(raw) is FilterCondition:
        raw = raw.model_dump(mode="json")
    if isinstance(raw, dict):
        return _any_filter_adapter().validate_python(raw)
    return raw


def revalidate_filters(raw_filters: list[Any]) -> list[FilterCondition]:
    """Apply :func:`revalidate_filter` to a list of filters."""
    return [revalidate_filter(raw) for raw in raw_filters]


def revalidate_filter_grid(raw_grid: list[list[Any]]) -> list[list[FilterCondition]]:
    """Recover every concrete filter in a nested filter grid."""
    return [revalidate_filters(raw_filters) for raw_filters in raw_grid]


def dump_filters(value: list[Any]) -> list[Any]:
    """Serialize filters through their concrete classes rather than the base schema."""
    return [
        filter_.model_dump(mode="json") if isinstance(filter_, FilterCondition) else filter_
        for filter_ in value
    ]


def dump_filter_grid(value: list[list[Any]]) -> list[list[Any]]:
    """Serialize a nested filter grid (``list[list[FilterCondition]]``) by
    instance, not by schema.

    Schema-driven serialization of these fields can degrade to the base
    ``FilterCondition`` schema (dropping every subclass field) depending on
    module import order; dumping each instance through its own class is
    deterministic. Used as a ``field_serializer`` for ``slot_filters`` fields.
    """
    return [dump_filters(slot) for slot in value]


# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------
