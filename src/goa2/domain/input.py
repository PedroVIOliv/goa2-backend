"""
Unified Input Contract for GoA2 Engine.

This module defines the typed schemas for all input requests and responses
between the engine and clients. All steps use InputRequest for their
input_request field, providing a consistent contract.

Phase 1 of Client-Readiness Roadmap:
- Fixes pain point #3 (inconsistent format)
- Fixes pain point #4 (unused InputRequest model)
- Fixes pain point #8 (type coercion)
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class InputRequestType(str, Enum):
    """All possible input request types in the game engine."""

    # Legacy types (kept for backwards compatibility)
    NONE = "NONE"
    ACTION_CHOICE = "ACTION_CHOICE"
    MOVEMENT_HEX = "MOVEMENT_HEX"
    DEFENSE_CARD = "DEFENSE_CARD"
    TIE_BREAKER = "TIE_BREAKER"
    SELECT_ALLY = "SELECT_ALLY"
    FAST_TRAVEL_DESTINATION = "FAST_TRAVEL_DESTINATION"
    SELECT_ENEMY = "SELECT_ENEMY"
    UPGRADE_CHOICE = "UPGRADE_CHOICE"

    # Unified selection types
    SELECT_UNIT = "SELECT_UNIT"
    SELECT_UNIT_OR_TOKEN = "SELECT_UNIT_OR_TOKEN"
    SELECT_HEX = "SELECT_HEX"
    SELECT_CARD = "SELECT_CARD"
    SELECT_NUMBER = "SELECT_NUMBER"

    # Action/choice types
    CHOOSE_ACTION = "CHOOSE_ACTION"
    SELECT_CARD_OR_PASS = "SELECT_CARD_OR_PASS"
    SELECT_OPTION = "SELECT_OPTION"

    # Phase-specific types
    CHOOSE_ACTOR = "CHOOSE_ACTOR"
    CHOOSE_RESPAWN = "CHOOSE_RESPAWN"
    CHOOSE_RESPAWN_HEX = "CHOOSE_RESPAWN_HEX"
    UPGRADE_PHASE = "UPGRADE_PHASE"
    CONFIRM_PASSIVE = "CONFIRM_PASSIVE"


class InputOption(BaseModel):
    """
    A single option presented to the player.

    Used in the unified 'options' field of InputRequest.
    All options are serialized consistently regardless of type.
    """

    id: str  # Unique identifier for this option
    text: str  # Human-readable display text
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Additional data

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_value(cls, value: Any, text: Optional[str] = None) -> "InputOption":
        """
        Create an InputOption from various input types.

        Handles: str, int, dict, Hex objects, etc.
        Stores original value in metadata["raw"] for backwards compatibility.
        """
        if isinstance(value, InputOption):
            return value

        if isinstance(value, dict):
            # Dict with id/text keys (action options)
            if "id" in value:
                return cls(
                    id=str(value.get("id")),
                    text=str(value.get("text", value.get("id"))),
                    metadata={
                        k: v for k, v in value.items() if k not in ("id", "text")
                    },
                )
            # Hex-like dict
            if "q" in value and "r" in value and "s" in value:
                return cls(
                    id=f"hex_{value['q']}_{value['r']}_{value['s']}",
                    text=f"({value['q']},{value['r']},{value['s']})",
                    metadata={"hex": value, "raw": value},
                )
            # Generic dict - use string representation
            return cls(id=str(value), text=str(value), metadata={"raw": value})

        if hasattr(value, "q") and hasattr(value, "r") and hasattr(value, "s"):
            # Hex object - store both the original object and its dict form
            return cls(
                id=f"hex_{value.q}_{value.r}_{value.s}",
                text=f"({value.q},{value.r},{value.s})",
                metadata={
                    "hex": {"q": value.q, "r": value.r, "s": value.s},
                    "raw": value,  # Store original Hex object for tests
                },
            )

        # Simple value (str, int, etc.)
        return cls(id=str(value), text=text or str(value), metadata={})


class InputRequest(BaseModel):
    """
    Unified input request sent to clients.

    All steps that require player input construct this model.
    The 'options' field provides a consistent list of InputOption objects.

    Supports dict-like access for backwards compatibility with existing code
    that accesses fields via request["type"], request["options"], etc.
    """

    id: str = Field(default_factory=lambda: str(id(object())))  # Unique request ID
    request_type: InputRequestType  # What kind of input is needed
    player_id: str  # WHO must answer (hero_id or team delegate)
    prompt: str = ""  # Human-readable instruction

    # Unified options list - always present, may be empty
    options: List[InputOption] = Field(default_factory=list)

    # Common flags
    can_skip: bool = False  # Whether player can skip/pass
    can_rollback: bool = False  # Whether player can rollback to action choice

    # Legacy/additional context (for backwards compatibility during transition)
    context: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __getitem__(self, key: str) -> Any:
        """
        Dict-like access for backwards compatibility.

        Maps legacy keys to their new locations:
        - "type" -> request_type.value
        - "valid_options" -> raw options list
        - "options" -> raw options list
        - "candidates" -> raw options list
        - "valid_hexes" -> raw hex options list
        - Other keys -> try context, then attributes
        """
        dict_repr = self.to_dict()
        if key in dict_repr:
            return dict_repr[key]
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        """Check if key exists in dict representation."""
        return key in self.to_dict()

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like get for backwards compatibility."""
        try:
            return self[key]
        except KeyError:
            return default

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format for backwards compatibility.

        This method produces output compatible with the existing playtest.py
        handlers while we transition to the typed model.
        """
        result: Dict[str, Any] = {
            "type": self.request_type.value,
            "prompt": self.prompt,
            "player_id": self.player_id,
        }

        # Add can_skip if True
        if self.can_skip:
            result["can_skip"] = True

        # Add can_rollback if True
        if self.can_rollback:
            result["can_rollback"] = True

        # Helper to extract serializable value from option
        def get_serializable_value(opt: InputOption) -> Any:
            # Check for hex dict in metadata (always use dict form for JSON compatibility)
            if "hex" in opt.metadata:
                return opt.metadata["hex"]  # Already a dict
            # Check for raw value - convert Hex objects to dicts
            if "raw" in opt.metadata:
                raw = opt.metadata["raw"]
                if hasattr(raw, "q") and hasattr(raw, "r") and hasattr(raw, "s"):
                    return {"q": raw.q, "r": raw.r, "s": raw.s}
                return raw
            # Try to convert id back to int for number options
            if opt.id.lstrip("-").isdigit():
                return int(opt.id)
            return opt.id

        # Convert options based on request type for backwards compatibility
        if self.request_type in (
            InputRequestType.SELECT_UNIT,
            InputRequestType.SELECT_UNIT_OR_TOKEN,
            InputRequestType.SELECT_NUMBER,
            InputRequestType.SELECT_CARD,
        ):
            # These expect valid_options as list of raw values
            result["valid_options"] = [
                get_serializable_value(opt) for opt in self.options
            ]
            # Also add as candidates for MultiSelectStep compatibility
            result["candidates"] = result["valid_options"]
        elif self.request_type == InputRequestType.SELECT_HEX:
            # Hex selection expects valid_options as list of hex dicts (JSON-serializable)
            hex_values = [opt.metadata.get("hex", opt.id) for opt in self.options]
            result["valid_options"] = hex_values
            # Also add valid_hexes for backwards compatibility (displacement tests)
            result["valid_hexes"] = hex_values
        elif self.request_type == InputRequestType.CHOOSE_RESPAWN:
            # Respawn has both options and valid_hexes
            if any(opt.metadata.get("hex") for opt in self.options):
                # Return hex dicts for JSON compatibility
                result["valid_hexes"] = [
                    opt.metadata.get("hex")
                    for opt in self.options
                    if opt.metadata.get("hex")
                ]
            else:
                result["options"] = [opt.id for opt in self.options]
            # Include valid_hexes from context if present (serialize if needed)
            if "valid_hexes" in self.context:
                ctx_hexes = self.context["valid_hexes"]
                result["valid_hexes"] = [
                    {"q": h.q, "r": h.r, "s": h.s} if hasattr(h, "q") else h
                    for h in ctx_hexes
                ]
        elif self.request_type == InputRequestType.CHOOSE_RESPAWN_HEX:
            # Respawn hex selection - use hex dicts for JSON compatibility
            result["valid_hexes"] = [
                opt.metadata.get("hex", opt.id) for opt in self.options
            ]
            # Serialize context valid_hexes if present
            if "valid_hexes" in self.context:
                ctx_hexes = self.context["valid_hexes"]
                result["valid_hexes"] = [
                    {"q": h.q, "r": h.r, "s": h.s} if hasattr(h, "q") else h
                    for h in ctx_hexes
                ]
        elif self.request_type == InputRequestType.CONFIRM_PASSIVE:
            # Confirm passive expects simple string IDs ("YES", "NO")
            result["options"] = [opt.id for opt in self.options]
        elif self.request_type in (
            InputRequestType.CHOOSE_ACTION,
            InputRequestType.SELECT_OPTION,
        ):
            # Action choices expect options as list of dicts with id/text
            result["options"] = [
                {"id": opt.id, "text": opt.text, **opt.metadata} for opt in self.options
            ]
        elif self.request_type == InputRequestType.SELECT_CARD_OR_PASS:
            # Card or pass options as objects with id, text, and metadata
            result["options"] = [
                {"id": opt.id, "text": opt.text, **opt.metadata} for opt in self.options
            ]
        elif self.request_type == InputRequestType.CHOOSE_ACTOR:
            # Actor choice expects player_ids list
            result["player_ids"] = [opt.id for opt in self.options]
            if "team" in self.context:
                result["team"] = self.context["team"]
        elif self.request_type == InputRequestType.UPGRADE_PHASE:
            # Upgrade phase has special 'players' structure
            if "players" in self.context:
                result["players"] = self.context["players"]
        else:
            # Default: include options as-is
            if self.options:
                result["options"] = [
                    {"id": opt.id, "text": opt.text, **opt.metadata}
                    for opt in self.options
                ]

        # Merge any additional context
        for key, value in self.context.items():
            if key not in result:
                result[key] = value

        return result


class InputResponse(BaseModel):
    """
    Unified input response from clients.

    All player responses use this single shape, making validation simpler.
    The 'selection' field contains the player's choice.
    """

    request_id: str = ""  # ID of the request being answered
    selection: Any = None  # The player's selection (ID, hex dict, etc.)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def from_legacy(
        cls, legacy_dict: Dict[str, Any], request_id: str = ""
    ) -> "InputResponse":
        """
        Create an InputResponse from legacy handler response formats.

        Maps various legacy keys to the unified 'selection' field:
        - selection, choice, choice_id, selected_card_id, selected_hero_id, spawn_hex, winner_id
        """
        # Try various legacy keys in order of specificity
        selection = None

        if "selection" in legacy_dict:
            selection = legacy_dict["selection"]
        elif "choice" in legacy_dict:
            selection = legacy_dict["choice"]
        elif "choice_id" in legacy_dict:
            selection = legacy_dict["choice_id"]
        elif "selected_card_id" in legacy_dict:
            selection = legacy_dict["selected_card_id"]
        elif "selected_hero_id" in legacy_dict:
            selection = legacy_dict["selected_hero_id"]
        elif "spawn_hex" in legacy_dict:
            selection = legacy_dict["spawn_hex"]
        elif "winner_id" in legacy_dict:
            selection = legacy_dict["winner_id"]

        return cls(request_id=request_id, selection=selection)


# Helper function for creating InputRequest from raw values
def create_input_request(
    request_type: Union[InputRequestType, str],
    player_id: str,
    prompt: str = "",
    options: Optional[List[Any]] = None,
    can_skip: bool = False,
    **context: Any,
) -> InputRequest:
    """
    Factory function to create InputRequest with automatic option conversion.

    Args:
        request_type: The type of input request
        player_id: Who must provide input
        prompt: Human-readable prompt
        options: List of options (will be converted to InputOption)
        can_skip: Whether the player can skip
        **context: Additional context data

    Returns:
        A properly constructed InputRequest
    """
    if isinstance(request_type, str):
        request_type = InputRequestType(request_type)

    converted_options = []
    if options:
        for opt in options:
            converted_options.append(InputOption.from_value(opt))

    return InputRequest(
        request_type=request_type,
        player_id=str(player_id),
        prompt=prompt,
        options=converted_options,
        can_skip=can_skip,
        context=context,
    )
