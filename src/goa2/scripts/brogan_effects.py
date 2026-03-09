from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckHeroDefeatedThisRoundStep,
    CountCardsStep,
    CountStep,
    CreateEffectStep,
    DiscardCardStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    MoveSequenceStep,
    MoveUnitStep,
    PlaceUnitStep,
    PushUnitStep,
    RecordHexStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    AdjacencyFilter,
    InStraightLineFilter,
    PlayedCardFilter,
    StraightLinePathFilter,
    ObstacleFilter,
    OrFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    TargetType,
    ActionType,
    CardColor,
)
from goa2.domain.models.enums import (
    CardContainerType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import DisplacementType

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.effects import PassiveConfig
    from goa2.engine.stats import CardStats


# =============================================================================
# TIER I - BLUE: Brutal Jab
# =============================================================================


@register_effect("brutal_jab")
class BrutalJabEffect(CardEffect):
    """
    Card text: "You may move 1 space. Push an enemy unit or a token
    adjacent to you up to 1 space."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Optional move 1 space
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[RangeFilter(max_range=1), ObstacleFilter()],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),
            # 2. Select adjacent enemy unit or token to push
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(
                        filters=[
                            TeamFilter(relation="ENEMY"),
                            UnitTypeFilter(unit_type="TOKEN"),
                        ]
                    ),
                ],
            ),
            # 3. Choose push distance (0 or 1)
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-1)",
                output_key="push_distance",
                number_options=[0, 1],
                active_if_key="push_target_id",
            ),
            # 4. Execute push
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
            ),
        ]


# =============================================================================
# TIER II - BLUE: Mighty Punch
# =============================================================================


@register_effect("mighty_punch")
class MightyPunchEffect(CardEffect):
    """
    Card text: "You may move 1 space. Push an enemy unit or a token
    adjacent to you up to 2 spaces."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[RangeFilter(max_range=1), ObstacleFilter()],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(
                        filters=[
                            TeamFilter(relation="ENEMY"),
                            UnitTypeFilter(unit_type="TOKEN"),
                        ]
                    ),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-2)",
                output_key="push_distance",
                number_options=[0, 1, 2],
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# TIER III - BLUE: Savage Kick
# =============================================================================


@register_effect("savage_kick")
class SavageKickEffect(CardEffect):
    """
    Card text: "Move up to 2 spaces. Push an enemy unit or a token
    adjacent to you up to 2 spaces."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # Move up to 2
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[RangeFilter(max_range=2), ObstacleFilter()],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(
                        filters=[
                            TeamFilter(relation="ENEMY"),
                            UnitTypeFilter(unit_type="TOKEN"),
                        ]
                    ),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-2)",
                output_key="push_distance",
                number_options=[0, 1, 2],
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# UNTIERED - GOLD: Onslaught
# =============================================================================


@register_effect("onslaught")
class OnslaughtEffect(CardEffect):
    """
    Card text: "Target a unit adjacent to you. After the attack:
    Move into the space it occupied, if able."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select adjacent target
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="victim_id",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 2. Record victim's hex position before attack
            RecordHexStep(unit_key="victim_id", output_key="victim_hex"),
            # 3. Attack using pre-selected target
            AttackSequenceStep(
                damage=stats.primary_value, target_id_key="victim_id", range_val=1
            ),
            # 4. Move into target's former space (optional, "if able")
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="victim_hex",
                is_mandatory=False,
                range_val=1,
            )
        ]


# =============================================================================
# TIER II - BLUE: Shield Bash
# =============================================================================


@register_effect("shield_bash")
class ShieldBashEffect(CardEffect):
    """
    Card text: "An enemy hero adjacent to you who has played an attack card
    this turn discards a card, if able."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select adjacent enemy hero (who played attack this turn)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent enemy hero who played an attack card this turn",
                output_key="bash_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                    PlayedCardFilter(action_type=ActionType.ATTACK),
                ],
            ),
            # 2. Force discard (if able)
            ForceDiscardStep(victim_key="bash_victim"),
        ]


# =============================================================================
# TIER III - BLUE: Counterattack
# =============================================================================


@register_effect("counterattack")
class CounterattackEffect(CardEffect):
    """
    Card text: "An enemy hero adjacent to you who has played an attack card
    this turn discards a card, or is defeated."

    Same targeting as Shield Bash, but uses ForceDiscardOrDefeatStep.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent enemy hero who played an attack card this turn",
                output_key="counter_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                    PlayedCardFilter(action_type=ActionType.ATTACK),
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="counter_victim"),
        ]


# =============================================================================
# TIER I - RED: Mad Dash
# =============================================================================


@register_effect("mad_dash")
class MadDashEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2 spaces in a straight line to a
    space adjacent to an enemy unit, then target that unit.
    (If you cannot make this move, you cannot attack.)"
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                output_key="dash_destination",
                filters=[
                    RangeFilter(min_range=2, max_range=2),
                    InStraightLineFilter(origin_id=hero.id),
                    AdjacencyFilter(target_tags=["ENEMY"]),
                    ObstacleFilter(is_obstacle=False),
                    StraightLinePathFilter(origin_id=hero.id),
                ],
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="dash_destination",
                range_val=99,
            ),
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
        ]


# =============================================================================
# TIER II - RED: Bullrush
# =============================================================================


@register_effect("bullrush")
class BullrushEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2 or 3 spaces in a straight line to a
    space adjacent to an enemy unit, then target that unit."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                output_key="rush_destination",
                filters=[
                    RangeFilter(min_range=2, max_range=3),
                    InStraightLineFilter(origin_id=hero.id),
                    AdjacencyFilter(target_tags=["ENEMY"]),
                    ObstacleFilter(is_obstacle=False),
                    StraightLinePathFilter(origin_id=hero.id),
                ],
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="rush_destination",
                range_val=99,
            ),
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
        ]


# =============================================================================
# TIER III - RED: Furious Charge
# =============================================================================


@register_effect("furious_charge")
class FuriousChargeEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2, 3, or 4 spaces in a straight line to
    a space adjacent to an enemy unit, then target that unit."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                output_key="charge_destination",
                filters=[
                    RangeFilter(min_range=2, max_range=4),
                    InStraightLineFilter(origin_id=hero.id),
                    AdjacencyFilter(target_tags=["ENEMY"]),
                    ObstacleFilter(is_obstacle=False),
                    StraightLinePathFilter(origin_id=hero.id),
                ],
            ),
            MoveUnitStep(
                unit_id=hero.id,
                destination_key="charge_destination",
                range_val=99,
            ),
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
        ]


# =============================================================================
# TIER II - RED: Throwing Axe
# =============================================================================


@register_effect("throwing_axe")
class ThrowingAxeEffect(CardEffect):
    """
    Card text: "Choose one -
    * Target a unit adjacent to you.
    * You may discard a card; if you do, target a unit in range."

    Implementation: Player chooses option 1 (melee) or 2 (ranged).
    Uses CheckContextConditionStep to branch execution.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose mode
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent, 2 = Discard card to attack in range",
                output_key="attack_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            # 3a. Melee: select adjacent target
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="meelee_victim_id",
                is_mandatory=True,
                active_if_key="chose_melee",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                target_id_key="meelee_victim_id",
                range_val=1,
                active_if_key="chose_melee",
            ),
            # 3b. Ranged: optionally discard, then select target in range
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.HAND,
                prompt="You may discard a card (for ranged attack)",
                output_key="discard_for_range",
                is_mandatory=False,
                active_if_key="chose_ranged",
            ),
            DiscardCardStep(
                card_key="discard_for_range",
                hero_id=hero.id,
                active_if_key="discard_for_range",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                active_if_key="discard_for_range",
            ),
        ]


# =============================================================================
# TIER III - RED: Throwing Spear
# =============================================================================


@register_effect("throwing_spear")
class ThrowingSpearEffect(CardEffect):
    """
    Card text: "Choose one -
    * Target a unit adjacent to you.
    * You may discard a card. If you have a card in the discard,
      target a unit in range."

    Similar to Throwing Axe but the discard condition is different:
    Option 2 checks if there's already a card in discard OR you discard one.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose mode
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent, 2 = May discard for ranged attack",
                output_key="attack_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            # 3a. Melee path: select adjacent enemy → attack
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="melee_victim_id",
                is_mandatory=True,
                active_if_key="chose_melee",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                target_id_key="melee_victim_id",
                range_val=1,
                active_if_key="chose_melee",
            ),
            # 3b. Ranged path: optionally discard, then check discard pile
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.HAND,
                prompt="You may discard a card",
                output_key="discard_for_range",
                is_mandatory=False,
                active_if_key="chose_ranged",
            ),
            DiscardCardStep(
                card_key="discard_for_range",
                hero_id=hero.id,
                active_if_key="discard_for_range",
            ),
            # Count cards in discard pile (includes the one just discarded)
            CountCardsStep(
                hero_id=hero.id,
                card_container=CardContainerType.DISCARD,
                output_key="discard_count",
                active_if_key="chose_ranged",
            ),
            CheckContextConditionStep(
                input_key="discard_count",
                operator=">=",
                threshold=1,
                output_key="has_discard",
            ),
            # Attack in range only if discard pile has ≥1 card
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                active_if_key="has_discard",
            ),
        ]


# =============================================================================
# TIER I - GREEN: Shield
# =============================================================================


@register_effect("shield")
class ShieldEffect(CardEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a silver card. If you do, the minion is not removed.
    (The enemy hero still gains the coins for defeating the minion.)"
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.MINION_PROTECTION,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 1,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                allowed_discard_colors=[CardColor.SILVER],
                is_active=True,
            ),
        ]


# =============================================================================
# TIER II - GREEN: Bolster
# =============================================================================


@register_effect("bolster")
class BolsterEffect(ShieldEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a silver card. If you do, the minion is not removed."

    Same as Shield but at Tier II (stats differ via card definition — radius=2).
    """

    pass


# =============================================================================
# TIER III - GREEN: Fortify
# =============================================================================


@register_effect("fortify")
class FortifyEffect(CardEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a basic card. If you do, the minion is not removed."

    Same mechanic as Shield/Bolster but allows discarding ANY basic card
    (Gold or Silver) instead of only Silver.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.MINION_PROTECTION,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 2,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                allowed_discard_colors=[CardColor.GOLD, CardColor.SILVER],
                is_active=True,
            ),
        ]


# =============================================================================
# TIER II - GREEN: War Drummer
# =============================================================================


@register_effect("war_drummer")
class WarDrummerEffect(CardEffect):
    """
    Card text: "A friendly hero in range gains 1 coin; if any hero was
    defeated this round, that friendly hero gains 3 coins instead."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select friendly hero in range to gain coins",
                output_key="coin_target",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.range),
                ],
                skip_immunity_filter=True,
            ),
            CheckHeroDefeatedThisRoundStep(output_key="hero_died"),
            GainCoinsStep(hero_key="coin_target", amount=3, active_if_key="hero_died"),
            GainCoinsStep(hero_key="coin_target", amount=1, skip_if_key="hero_died"),
        ]


# =============================================================================
# TIER III - GREEN: Master Skald
# =============================================================================


@register_effect("master_skald")
class MasterSkaldEffect(CardEffect):
    """
    Card text: "A friendly hero in range gains 2 coins; if any hero was
    defeated this round, that friendly hero gains 4 coins instead."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select friendly hero in range to gain coins",
                output_key="coin_target",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.range),
                ],
                skip_immunity_filter=True,
            ),
            CheckHeroDefeatedThisRoundStep(output_key="hero_died"),
            GainCoinsStep(hero_key="coin_target", amount=4, active_if_key="hero_died"),
            GainCoinsStep(hero_key="coin_target", amount=2, skip_if_key="hero_died"),
        ]


# =============================================================================
# UNTIERED - SILVER: Bulwark
# =============================================================================


@register_effect("bulwark")
class BulwarkEffect(CardEffect):
    """
    Card text: "You may retrieve a discarded card.
    This turn: You and friendly units in radius cannot be moved, pushed,
    swapped or placed by enemy heroes."

    The displacement immunity uses PLACEMENT_PREVENTION with all displacement
    types blocked, targeting self + friendly units in radius.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Optionally retrieve a discarded card
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve (optional)",
                output_key="retrieved_card",
                is_mandatory=False,
            ),
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
            # 2. Create displacement immunity for self + friendlies in radius
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                duration=DurationType.THIS_TURN,
                displacement_blocks=[
                    DisplacementType.MOVE,
                    DisplacementType.PUSH,
                    DisplacementType.SWAP,
                    DisplacementType.PLACE,
                ],
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False,
            ),
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.SELF,
                ),
                duration=DurationType.THIS_TURN,
                displacement_blocks=[
                    DisplacementType.MOVE,
                    DisplacementType.PUSH,
                    DisplacementType.SWAP,
                    DisplacementType.PLACE,
                ],
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False,
            ),
        ]


# =============================================================================
# ULTIMATE (Purple/Tier IV) - Passive Ability
# =============================================================================


@register_effect("one_man_army")
class OneManArmyEffect(CardEffect):
    """
    Ultimate (Purple) - Brogan

    Card text: "During minion battle you count as a heavy minion;
    if you would be removed, lose the push instead."

    This effect has no steps or passive config. The logic is implemented
    directly in MinionBattleStep via _one_man_army_bonus(), which checks
    for heroes with effect_id "one_man_army" at level >= 8 in the active
    zone and adds +1 to their team's minion count.

    "Lose the push instead" is handled implicitly: CheckLanePushStep
    counts real minions only, so if all real minions die the push still
    triggers (Brogan isn't removed, but his team loses the zone).
    """

    def get_passive_config(self) -> Optional["PassiveConfig"]:
        return None

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return []
