from __future__ import annotations
from typing import Any, List, Optional, TypedDict

from pydantic import BaseModel, Field

from goa2.domain.models import Card


class ValidationContext(TypedDict, total=False):
    """Context data passed to validation service."""

    card: Optional[Card]
    current_card_id: Optional[str]
    defense_value: Optional[int]
    skipped_respawn: Optional[bool]
    selection: Any  # Default output for SelectStep
    confirmation: Optional[bool]  # Default output for AskConfirmationStep
    # Allow arbitrary keys for now to maintain compatibility with legacy dicts
    # until strict typing is enforced everywhere
    __extra_items__: Any


class ValidationResult(BaseModel):
    """
    Standardized result for all validation checks.
    Provides data for both execution logic and frontend previews.
    """

    allowed: bool
    reason: str = ""
    blocking_effect_ids: List[str] = Field(default_factory=list)
    blocking_modifier_ids: List[str] = Field(default_factory=list)
    blocked_by_source: Optional[str] = None

    @staticmethod
    def allow() -> "ValidationResult":
        """Create a result indicating the action is allowed."""
        return ValidationResult(allowed=True)

    @staticmethod
    def deny(
        reason: str,
        effect_ids: Optional[List[str]] = None,
        modifier_ids: Optional[List[str]] = None,
        source: Optional[str] = None,
    ) -> "ValidationResult":
        """Create a result indicating the action is denied."""
        return ValidationResult(
            allowed=False,
            reason=reason,
            blocking_effect_ids=effect_ids or [],
            blocking_modifier_ids=modifier_ids or [],
            blocked_by_source=source,
        )
