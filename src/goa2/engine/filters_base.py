from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from goa2.domain.models import FilterType
from goa2.domain.state import GameState


class FilterCondition(BaseModel):
    """
    Base class for all selection filters.
    """

    type: FilterType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------
