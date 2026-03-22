from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect, StatAura, PassiveConfig
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckAdjacencyStep,
    CheckContextConditionStep,
    CountStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    ForEachStep,
    GameStep,
    MayRepeatNTimesStep,
    MayRepeatOnceStep,
    MoveSequenceStep,
    MoveUnitStep,
    MultiSelectStep,
    PushUnitStep,
    RemoveUnitStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)
from goa2.engine.filters import (
    AdjacencyFilter,
    ExcludeIdentityFilter,
    ObstacleFilter,
    PlayedCardFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    ActionType,
    CardContainerType,
    TargetType,
)
from goa2.domain.models.enums import PassiveTrigger, StatType
from goa2.domain.types import HeroID

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# EASY: UNTIERED - SILVER: Back to Back (SKILL)
# =============================================================================


@register_effect("back_to_back")
class BackToBackEffect(CardEffect):
    """
    Card text: "Swap with a friendly minion in radius."

    Same pattern as Arien's arcane_whirlpool but with FRIENDLY minion.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.radius),
                ],
                prompt="Select a friendly minion to swap with.",
                output_key="swap_target_id",
                is_mandatory=True,
            ),
            SwapUnitsStep(unit_a_id=hero.id, unit_b_key="swap_target_id"),
        ]


# =============================================================================
# EASY: TIER I - BLUE: Listen Up (SKILL)
# =============================================================================


@register_effect("listen_up")
class ListenUpEffect(CardEffect):
    """
    Card text: "Swap two minions in radius."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                ],
                prompt="Select first minion to swap.",
                output_key="swap_a",
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                    ExcludeIdentityFilter(exclude_keys=["swap_a"]),
                ],
                prompt="Select second minion to swap.",
                output_key="swap_b",
                is_mandatory=True,
            ),
            SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b"),
        ]


# =============================================================================
# EASY: TIER II - BLUE: Roger Roger (SKILL)
# =============================================================================


@register_effect("roger_roger")
class RogerRogerEffect(CardEffect):
    """
    Card text: "Swap two minions in radius."

    Same as Listen Up but with larger radius (from card stats).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                ],
                prompt="Select first minion to swap.",
                output_key="swap_a",
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                    ExcludeIdentityFilter(exclude_keys=["swap_a"]),
                ],
                prompt="Select second minion to swap.",
                output_key="swap_b",
                is_mandatory=True,
            ),
            SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b"),
        ]


# =============================================================================
# EASY: TIER III - BLUE: Ready and Waiting (SKILL)
# =============================================================================


@register_effect("ready_and_waiting")
class ReadyAndWaitingEffect(CardEffect):
    """
    Card text: "Swap two minions in radius, ignoring heavy minion immunity."

    Same as Roger Roger but with skip_immunity_filter=True so heavy minions
    can be swapped.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                ],
                prompt="Select first minion to swap (ignores immunity).",
                output_key="swap_a",
                is_mandatory=True,
                skip_immunity_filter=True,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    RangeFilter(max_range=stats.radius),
                    ExcludeIdentityFilter(exclude_keys=["swap_a"]),
                ],
                prompt="Select second minion to swap (ignores immunity).",
                output_key="swap_b",
                is_mandatory=True,
                skip_immunity_filter=True,
            ),
            SwapUnitsStep(unit_a_key="swap_a", unit_b_key="swap_b"),
        ]


# =============================================================================
# EASY-MEDIUM: UNTIERED - GOLD: Point Blank Shot (ATTACK)
# =============================================================================


@register_effect("point_blank_shot")
class PointBlankShotEffect(CardEffect):
    """
    Card text: "Target a unit in range. After the attack: If the target is
    adjacent to you, push it 1 space."

    Range is 1, so target is always adjacent at selection time. The "if adjacent"
    clause handles cases where the target might have moved during defense.
    We check adjacency after attack resolution and conditionally push.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack (range 1 = adjacent)
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            # 2. Check if victim is still adjacent after attack
            CheckAdjacencyStep(
                unit_a_id=hero.id,
                unit_b_key="victim_id",
                output_key="target_still_adjacent",
            ),
            # 3. Push 1 space if still adjacent
            PushUnitStep(
                target_key="victim_id",
                distance=1,
                active_if_key="target_still_adjacent",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# EASY-MEDIUM: TIER I - GREEN: Troop Movement (SKILL)
# =============================================================================


def _build_minion_move_steps(
    stats: "CardStats",
    output_prefix: str = "tm",
) -> List[GameStep]:
    """
    Shared helper: select a friendly minion in radius, move it 1 space
    to a space in radius.
    """
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            filters=[
                UnitTypeFilter(unit_type="MINION"),
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=stats.radius),
            ],
            prompt="Select a friendly minion in radius to move.",
            output_key=f"{output_prefix}_minion",
            is_mandatory=True,
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select destination (1 space, in radius).",
            output_key=f"{output_prefix}_dest",
            filters=[
                RangeFilter(max_range=1, origin_key=f"{output_prefix}_minion"),
                ObstacleFilter(is_obstacle=False),
                RangeFilter(max_range=stats.radius),  # Must stay in radius
            ],
            is_mandatory=True,
        ),
        MoveUnitStep(
            unit_key=f"{output_prefix}_minion",
            destination_key=f"{output_prefix}_dest",
            range_val=1,
            is_movement_action=False,
        ),
    ]


@register_effect("troop_movement")
class TroopMovementEffect(CardEffect):
    """
    Card text: "Move a friendly minion in radius 1 space, to a space in
    radius. May repeat once."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        base_steps = _build_minion_move_steps(stats, output_prefix="tm")
        return base_steps + [
            MayRepeatOnceStep(
                steps_template=_build_minion_move_steps(stats, output_prefix="tm_r"),
            ),
        ]


# =============================================================================
# EASY-MEDIUM: TIER II - GREEN: Marching Orders (SKILL)
# =============================================================================


@register_effect("marching_orders")
class MarchingOrdersEffect(CardEffect):
    """
    Card text: "Move a friendly minion in radius 1 space, to a space in
    radius. May repeat once."

    Same pattern as Troop Movement (larger radius from card stats).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        base_steps = _build_minion_move_steps(stats, output_prefix="mo")
        return base_steps + [
            MayRepeatOnceStep(
                steps_template=_build_minion_move_steps(stats, output_prefix="mo_r"),
            ),
        ]


# =============================================================================
# EASY-MEDIUM: TIER III - GREEN: Path to Victory (SKILL)
# =============================================================================


@register_effect("path_to_victory")
class PathToVictoryEffect(CardEffect):
    """
    Card text: "Move a friendly minion in radius 1 space, to a space in
    radius. May repeat up to two times."

    Same as Troop Movement but with 2 repeats (3 total moves).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        base_steps = _build_minion_move_steps(stats, output_prefix="ptv")
        return base_steps + [
            MayRepeatNTimesStep(
                max_repeats=2,
                prompt="Move another friendly minion? (Path to Victory)",
                steps_template=_build_minion_move_steps(stats, output_prefix="ptv_r"),
            ),
        ]


# =============================================================================
# MEDIUM: TIER II - BLUE: Steady Advance (SKILL)
# =============================================================================


@register_effect("steady_advance")
class SteadyAdvanceEffect(CardEffect):
    """
    Card text: "If there are two or more friendly minions in radius, you may
    retrieve a discarded card; if you do, you may move 1 space."

    Uses CountStep to check minion count, then conditional card retrieval
    from discard, then conditional move. Pattern from xargatha's
    Fresh Converts / By My Call effects.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Count friendly minions in radius
            CountStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.radius),
                ],
                output_key="friendly_minion_count",
            ),
            # 2. Check if 2+
            CheckContextConditionStep(
                input_key="friendly_minion_count",
                operator=">=",
                threshold=2,
                output_key="can_retrieve",
            ),
            # 3. Select card from discard (optional)
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve (optional).",
                output_key="retrieved_card",
                is_mandatory=False,
                active_if_key="can_retrieve",
            ),
            # 4. Retrieve the card
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
            # 5. Move 1 space (only if card was retrieved)
            MoveSequenceStep(
                unit_id=hero.id,
                range_val=1,
                is_mandatory=False,
                active_if_key="retrieved_card",
            ),
        ]


# =============================================================================
# MEDIUM: TIER III - BLUE: Unwavering Resolve (SKILL)
# =============================================================================


@register_effect("unwavering_resolve")
class UnwaveringResolveEffect(CardEffect):
    """
    Card text: "If there are two or more friendly minions in radius, you may
    retrieve a discarded card; if you do, move up to 2 spaces."

    Same as Steady Advance but move 2 instead of 1.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CountStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.radius),
                ],
                output_key="friendly_minion_count",
            ),
            CheckContextConditionStep(
                input_key="friendly_minion_count",
                operator=">=",
                threshold=2,
                output_key="can_retrieve",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve (optional).",
                output_key="retrieved_card",
                is_mandatory=False,
                active_if_key="can_retrieve",
            ),
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
            MoveSequenceStep(
                unit_id=hero.id,
                range_val=2,
                is_mandatory=False,
                active_if_key="retrieved_card",
            ),
        ]


# =============================================================================
# MEDIUM: TIER II - RED: Shootout (ATTACK)
# =============================================================================


@register_effect("shootout")
class ShootoutEffect(CardEffect):
    """
    Card text: "Target a unit in range. After the attack: If the target was
    adjacent to you, remove up to one enemy minion adjacent to you."
    (You gain no coins for removing a minion, only for defeating.)
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack target in range
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            # 2. Check if victim was adjacent after attack
            CheckAdjacencyStep(
                unit_a_id=hero.id,
                unit_b_key="victim_id",
                output_key="was_adjacent",
            ),
            # 3. Select an enemy minion adjacent to you (optional, only if adjacent)
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
                prompt="Select an enemy minion adjacent to you to remove (optional).",
                output_key="remove_target",
                is_mandatory=False,
                active_if_key="was_adjacent",
            ),
            # 4. Remove selected minion
            RemoveUnitStep(
                unit_key="remove_target",
                active_if_key="remove_target",
            ),
        ]


# =============================================================================
# TIER I - RED: Quickdraw (ATTACK)
# =============================================================================


def _build_attack_with_played_card_bonus(
    stats: "CardStats",
    bonus: int,
) -> List[GameStep]:
    """
    Shared pattern for Quickdraw / Gunslinger / Dead Shot:
    "Target a unit in range. +N Attack if the target played an attack card
    this turn."

    Uses CountStep with RangeFilter(max_range=0, origin_key="victim_id") to
    isolate the selected target, then PlayedCardFilter to check if it played
    an attack card. Count=1 means yes, 0 means no.
    """
    return [
        # 1. Select target
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select a unit in range to attack.",
            output_key="victim_id",
            filters=[
                RangeFilter(max_range=stats.range),
                TeamFilter(relation="ENEMY"),
            ],
            is_mandatory=True,
        ),
        # 2. Check if target played an attack card this turn
        # RangeFilter(max_range=0) from the victim matches only the victim itself
        CountStep(
            target_type=TargetType.UNIT,
            filters=[
                RangeFilter(max_range=0, origin_key="victim_id"),
                PlayedCardFilter(action_type=ActionType.ATTACK),
            ],
            output_key="played_attack_count",
        ),
        # 3. Convert count to boolean
        CheckContextConditionStep(
            input_key="played_attack_count",
            operator=">=",
            threshold=1,
            output_key="target_played_attack",
        ),
        # 4. Set bonus if condition met
        SetContextFlagStep(
            key="atk_bonus", value=bonus, active_if_key="target_played_attack"
        ),
        # 5. Attack with pre-selected target and conditional bonus
        AttackSequenceStep(
            damage=stats.primary_value,
            target_id_key="victim_id",
            range_val=stats.range,
            is_ranged=True,
            damage_bonus_key="atk_bonus",
        ),
    ]


@register_effect("quickdraw")
class QuickdrawEffect(CardEffect):
    """
    Card text: "Target a unit in range. +3 Attack if the target played an
    attack card this turn."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _build_attack_with_played_card_bonus(stats, bonus=3)


# =============================================================================
# TIER II - RED: Gunslinger (ATTACK)
# =============================================================================


@register_effect("gunslinger")
class GunslingerEffect(CardEffect):
    """
    Card text: "Target a unit in range. +3 Attack if the target played an
    attack card this turn."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _build_attack_with_played_card_bonus(stats, bonus=3)


# =============================================================================
# TIER III - RED: Dead Shot (ATTACK)
# =============================================================================


@register_effect("dead_shot")
class DeadShotEffect(CardEffect):
    """
    Card text: "Target a unit in range. +4 Attack if the target played an
    attack card this turn."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _build_attack_with_played_card_bonus(stats, bonus=4)


# =============================================================================
# TIER II - GREEN: Close Support (SKILL)
# =============================================================================


@register_effect("close_support")
class CloseSupportEffect(CardEffect):
    """
    Card text: "An enemy hero in radius adjacent to your friendly minion
    discards a card, if able."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius),
                    AdjacencyFilter(target_tags=["FRIENDLY", "MINION"]),
                ],
                prompt="Select an enemy hero adjacent to a friendly minion.",
                output_key="support_victim",
                is_mandatory=False,
            ),
            ForceDiscardStep(
                victim_key="support_victim",
                active_if_key="support_victim",
            ),
        ]


# =============================================================================
# TIER III - GREEN: Covering Fire (SKILL)
# =============================================================================


@register_effect("covering_fire")
class CoveringFireEffect(CardEffect):
    """
    Card text: "An enemy hero in radius adjacent to your friendly minion
    discards a card, or is defeated."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius),
                    AdjacencyFilter(target_tags=["FRIENDLY", "MINION"]),
                ],
                prompt="Select an enemy hero adjacent to a friendly minion.",
                output_key="support_victim",
                is_mandatory=False,
            ),
            ForceDiscardOrDefeatStep(
                victim_key="support_victim",
                active_if_key="support_victim",
            ),
        ]


# =============================================================================
# TIER III - RED: Bullet Hell (ATTACK)
# =============================================================================


@register_effect("bullet_hell")
class BulletHellEffect(CardEffect):
    """
    Card text: "Target a unit in range. After the attack: If the target was
    adjacent to you, remove up to two enemy minions adjacent to you."
    (You gain no coins for removing a minion, only for defeating.)
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Attack target in range
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            # 2. Check if victim was adjacent after attack
            CheckAdjacencyStep(
                unit_a_id=hero.id,
                unit_b_key="victim_id",
                output_key="was_adjacent",
            ),
            # 3. Select up to 2 enemy minions adjacent to you
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select enemy minions adjacent to you to remove.",
                output_key="remove_targets",
                max_selections=2,
                min_selections=0,
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
                active_if_key="was_adjacent",
            ),
            # 4. Remove each selected minion
            ForEachStep(
                list_key="remove_targets",
                item_key="current_remove_target",
                steps_template=[
                    RemoveUnitStep(unit_key="current_remove_target"),
                ],
            ),
        ]


# =============================================================================
# ULTIMATE - PURPLE: Big Sodding Gun (PASSIVE)
# =============================================================================


@register_effect("big_sodding_gun")
class BigSoddingGunEffect(CardEffect):
    """
    Card text: "Your basic attack has +2 Range and +2 Attack. If you push an
    enemy hero, that hero discards a card, or is defeated."

    Part 1: Stat auras with flat_bonus, restricted to basic attack cards.
    Part 2: AFTER_PUSH passive trigger checks if victim is an enemy hero.
    """

    def get_stat_auras(self) -> List["StatAura"]:
        return [
            StatAura(
                stat_type=StatType.ATTACK,
                flat_bonus=2,
                basic_only=True,
                action_type_only=ActionType.ATTACK,
            ),
            StatAura(
                stat_type=StatType.RANGE,
                flat_bonus=2,
                basic_only=True,
                action_type_only=ActionType.ATTACK,
            ),
        ]

    def get_passive_config(self) -> Optional["PassiveConfig"]:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_PUSH,
            uses_per_turn=0,  # Unlimited — fires on every push
            is_optional=False,  # Automatic, not a choice
        )

    def get_passive_steps(
        self,
        state: "GameState",
        hero: "Hero",
        card: "Card",
        trigger: "PassiveTrigger",
        context: Dict[str, Any],
    ) -> List[GameStep]:
        if trigger != PassiveTrigger.AFTER_PUSH:
            return []

        victim_id = context.get("push_victim_id")
        if not victim_id:
            return []

        # Only trigger on enemy heroes
        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return []  # Minion — ignore
        if victim.team == hero.team:
            return []  # Friendly hero — ignore

        return [
            ForceDiscardOrDefeatStep(victim_key="push_victim_id"),
        ]
