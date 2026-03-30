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
    DurationType,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    MarkerType,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import TargetType, CardContainerType, Hero, Card
    from goa2.engine.stats import CardStats


@register_effect("venom_strike")
class VenomStrikeEffect(CardEffect):
    """
    Card Text: "Attack. This Round: Target has -1 Attack, -1 Defense, -1 Initiative."

    Now uses the Venom marker system instead of individual modifiers.
    The marker applies stat debuffs via get_computed_stat() reading markers.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Resolve Attack Sequence
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
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

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
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


@register_effect("rogue_skill_gold")
class RogueSkillGoldEffect(CardEffect):
    """
    Card Text: "Swap target enemy's current turn card with a card from their Resolved pile."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
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
