from __future__ import annotations

from typing import Any, ClassVar

from goa2.domain.hex import Hex
from goa2.domain.models import FilterType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, UnitID

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition


class OrFilter(FilterCondition):
    """Passes if ANY child filter passes (logical OR)."""

    type: FilterType = FilterType.OR_FILTER
    filters: list[FilterCondition] = []

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        return any(f.apply(candidate, state, context) for f in self.filters)


class AndFilter(FilterCondition):
    """Passes if ALL child filters pass (logical AND)."""

    type: FilterType = FilterType.AND_FILTER
    filters: list[FilterCondition] = []

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        return all(f.apply(candidate, state, context) for f in self.filters)


class CountMatchFilter(FilterCondition):
    """
    Hex filter: for a candidate hex, counts all units on the board that pass
    the provided sub-filters when those sub-filters are evaluated with the
    candidate hex as the origin. Passes if count is within [min_count, max_count].

    This is effectively "is this hex near N things matching X?". It works by
    temporarily publishing the candidate hex to context under a private key
    ("_cmf_origin_hex"), so sub-filters that accept `origin_hex_key` (e.g.
    RangeFilter) evaluate distance from the candidate hex.

    Used by Misa's swoop_in: "place yourself adjacent to 2+ enemy units".
    """

    type: FilterType = FilterType.COUNT_MATCH
    sub_filters: list[FilterCondition] = []
    min_count: int = 1
    max_count: int | None = None

    ORIGIN_HEX_KEY: ClassVar[str] = "_cmf_origin_hex"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Accept either a Hex (e.g. Misa's swoop_in target hex) or a unit-ID
        # string (e.g. Silverarrow's "is this target isolated?" check). For a
        # unit-ID candidate, resolve to its current hex and use that as origin.
        if isinstance(candidate, Hex):
            origin_hex = candidate
        elif isinstance(candidate, str):
            loc = state.entity_locations.get(BoardEntityID(candidate))
            if loc is None:
                return False
            origin_hex = loc
        else:
            return False

        # Temporarily publish candidate hex for sub-filter origin resolution.
        prev = context.get(self.ORIGIN_HEX_KEY)
        context[self.ORIGIN_HEX_KEY] = origin_hex.model_dump()
        try:
            # Gather candidate units — mirrors CountStep's UNIT path.
            count = 0
            for eid in state.entity_locations.keys():
                unit = state.get_unit(UnitID(str(eid)))
                if unit is None:
                    continue
                ok = True
                for f in self.sub_filters:
                    if not f.apply(str(eid), state, context):
                        ok = False
                        break
                if ok:
                    count += 1
        finally:
            if prev is None:
                context.pop(self.ORIGIN_HEX_KEY, None)
            else:
                context[self.ORIGIN_HEX_KEY] = prev

        if count < self.min_count:
            return False
        if self.max_count is not None and count > self.max_count:
            return False
        return True
