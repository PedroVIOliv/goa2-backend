"""Compatibility exports for validation services."""

from __future__ import annotations

from goa2.engine.validation_actions import ActionValidationMixin
from goa2.engine.validation_displacement import DisplacementValidationMixin
from goa2.engine.validation_effects import EffectValidationMixin
from goa2.engine.validation_movement import MovementValidationMixin
from goa2.engine.validation_targeting import TargetingValidationMixin
from goa2.engine.validation_terrain import TerrainValidationMixin
from goa2.engine.validation_types import ValidationContext, ValidationResult


class ValidationService(
    ActionValidationMixin,
    MovementValidationMixin,
    TargetingValidationMixin,
    DisplacementValidationMixin,
    TerrainValidationMixin,
    EffectValidationMixin,
):
    """
    Centralized validation authority.
    Single source of truth for "can X do Y to Z?"
    """


__all__ = ["ValidationContext", "ValidationResult", "ValidationService"]
