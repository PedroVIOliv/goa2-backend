from __future__ import annotations

from typing import Any, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from .card import Card
from .enums import ActionType, CardColor, CardState, CardTier, StatType


class SpellCard(Card):
    """A card in Gydion's separate spellbook lifecycle.

    Spell cards reuse ordinary card actions and stats, but they never enter a
    hero's deck, hand, discard pile, played slots, or item area.
    """

    spell_rank: int = Field(ge=0)
    effect_id: str = ""
    initiative: int = 0
    state: CardState = CardState.OUTSIDE_SPELLBOOK
    is_facedown: bool = False
    # Re-declare inherited optional targeting fields so Pydantic's mypy
    # plugin keeps them optional on the subclass constructor as well.
    range_value: int | None = Field(None, description="Max distance if ranged")
    radius_value: int | None = Field(None, description="Area-of-effect radius")

    model_config = ConfigDict(
        frozen=False,
        populate_by_name=True,
        validate_assignment=True,
    )

    @classmethod
    def define(
        cls,
        *,
        id: str,
        name: str,
        spell_rank: int,
        tier: CardTier,
        color: CardColor,
        primary_action: ActionType,
        effect_text: str,
        image_id: str = "",
        primary_action_value: int | None = None,
        is_ranged: bool = False,
        range_value: int | None = None,
        radius_value: int | None = None,
        effect_id: str | None = None,
    ) -> Self:
        """Create a spell definition while centralizing invariant card fields."""
        return cls(
            id=id,
            name=name,
            image_id=image_id,
            spell_rank=spell_rank,
            tier=tier,
            color=color,
            initiative=0,
            primary_action=primary_action,
            primary_action_value=primary_action_value,
            secondary_actions={},
            is_ranged=is_ranged,
            range_value=range_value,
            radius_value=radius_value,
            item=None,
            effect_id=effect_id or id,
            effect_text=effect_text,
            state=CardState.OUTSIDE_SPELLBOOK,
            is_facedown=False,
        )

    @model_validator(mode="before")
    @classmethod
    def default_effect_id_to_card_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "effect_id" not in data and "id" in data:
            return {**data, "effect_id": str(data["id"])}
        return data

    @field_validator("state")
    @classmethod
    def validate_spell_state(cls, value: CardState) -> CardState:
        if value not in (CardState.SPELLBOOK, CardState.OUTSIDE_SPELLBOOK):
            raise ValueError("Spell cards must stay in a spellbook lifecycle state.")
        return value

    @field_validator("initiative")
    @classmethod
    def validate_inert_initiative(cls, value: int) -> int:
        if value != 0:
            raise ValueError("Spell cards must have inert initiative 0.")
        return value

    @field_validator("item")
    @classmethod
    def validate_no_item(cls, value: StatType | None) -> None:
        if value is not None:
            raise ValueError("Spell cards cannot be converted to items.")
        return None
