from __future__ import annotations
from typing import List, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    GameStep,
    PlaceMarkerStep,
    SelectStep,
    SwapCardStep,
)
from goa2.domain.models import (
    TargetType,
    CardContainerType,
    StatType,
    DurationType,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    ActionType,
    MarkerType,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import TargetType, CardContainerType, Hero, Card


@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    """
    Card Text: "Attack. This Round: Target has -1 Attack, -1 Defense, -1 Initiative."

    Now uses the Venom marker system instead of individual modifiers.
    The marker applies stat debuffs via get_computed_stat() reading markers.
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        from goa2.engine.stats import get_computed_stat

        base_dmg = 2
        damage = get_computed_stat(state, hero.id, StatType.ATTACK, base_dmg)

        return [
            # 1. Resolve Attack Sequence
            AttackSequenceStep(damage=damage, range_val=1),
            # 2. Place Venom marker on victim (-1 to all stats)
            PlaceMarkerStep(
                marker_type=MarkerType.VENOM,
                target_key="victim_id",
                value=-1,
            ),
        ]


@register_effect("rogue_slippery_ground")
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


@register_effect("rogue_skill_gold")
class RogueSkillGoldEffect(CardEffect):
    """
    Card Text: "Swap target enemy's current turn card with a card from their Resolved pile."
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        from goa2.engine.filters import TeamFilter

        return [
            # 1. Select Enemy Hero
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an Enemy Hero to sabotage.",
                output_key="target_hero_id",
                filters=[TeamFilter(relation="ENEMY")],
                is_mandatory=True,
            ),
            # 2. Select Card from THAT Hero's Resolved pile
            SelectStep(
                target_type=TargetType.CARD,
                prompt="Select a Resolved card to swap in.",
                output_key="swap_card_id",
                context_hero_id_key="target_hero_id",
                card_container=CardContainerType.PLAYED,
                is_mandatory=True,
            ),
            # 3. Perform Swap on THAT Hero
            SwapCardStep(
                target_card_key="swap_card_id", context_hero_id_key="target_hero_id"
            ),
        ]
