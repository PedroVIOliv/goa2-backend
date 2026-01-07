from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import AttackSequenceStep, CreateModifierStep, CreateEffectStep
from goa2.domain.models import (
    StatType,
    DurationType,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    ActionType,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card, GameStep


@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    """
    Card Text: "Attack. This Round: Target has -1 Attack, -1 Defense, -1 Initiative."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        # Skill primary_action_value must be None per pydantic validation,
        # so we either use a fixed value or metadata/radius_value if we want it dynamic.
        # For Rogue's Venom Strike, it's typically 2.
        from goa2.engine.stats import get_computed_stat

        base_dmg = 2
        damage = get_computed_stat(state, hero.id, StatType.ATTACK, base_dmg)

        return [
            # 1. Resolve Attack Sequence
            AttackSequenceStep(damage=damage, range_val=1),
            # 2. Apply venom debuffs to the victim
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.ATTACK,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
            ),
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.DEFENSE,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
            ),
            CreateModifierStep(
                target_key="victim_id",
                stat_type=StatType.INITIATIVE,
                value_mod=-1,
                duration=DurationType.THIS_ROUND,
            ),
        ]


@register_effect("slippery_ground")
class SlipperyGroundEffect(CardEffect):
    """
    Card Text: "This Turn: Adjacent enemies can only move up to 1 space."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(
                    shape=Shape.ADJACENT,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_UNITS,
                ),
                duration=DurationType.THIS_TURN,
                max_value=1,
            )
        ]


@register_effect("magnetic_dagger")
class MagneticDaggerEffect(CardEffect):
    """
    Card Text: "Attack. This Turn: Enemy heroes in Radius 3 cannot be
    placed or swapped by enemy actions."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        from goa2.engine.stats import get_computed_stat

        base_dmg = 2  # Rogue's standard damage
        damage = get_computed_stat(state, hero.id, StatType.ATTACK, base_dmg)

        radius = 3

        return [
            # 1. Standard attack
            AttackSequenceStep(damage=damage, range_val=1),
            # 2. Create placement prevention effect
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=radius,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                restrictions=[ActionType.MOVEMENT],
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False,
            ),
        ]
