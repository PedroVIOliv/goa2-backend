from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CreateEffectStep,
    ForceDiscardStep,
    ForEachStep,
    GainCoinsStep,
    GameStep,
    MoveUnitStep,
    MultiSelectStep,
    RespawnMinionAtHexStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    BattleZoneFilter,
    ExcludeIdentityFilter,
    HasCardsInDiscardFilter,
    HasEmptyNeighborFilter,
    ObstacleFilter,
    RangeFilter,
    SpawnPointTeamFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models.enums import (
    StatType,
    TargetType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.stats import CardStats


# =============================================================================
# Shared Helper
# =============================================================================


def _count_empty_spawn_points(state: "GameState", hero_id: str, radius: int) -> int:
    """Count empty spawn points within radius of hero, in the active battle zone."""
    from goa2.domain.types import BoardEntityID
    from goa2.engine.topology import get_topology_service

    hero_hex = state.entity_locations.get(BoardEntityID(str(hero_id)))
    if not hero_hex:
        return 0

    active_zone_id = state.active_zone_id
    if not active_zone_id:
        return 0

    topology = get_topology_service()
    count = 0
    for h, tile in state.board.tiles.items():
        if not tile.spawn_point:
            continue
        # Must be in the active battle zone
        if tile.zone_id != active_zone_id:
            continue
        # Must be unoccupied
        if tile.is_occupied:
            continue
        # Must be within radius
        dist = topology.distance(hero_hex, h, state)
        if dist <= radius:
            count += 1
    return count


def _is_adjacent_to_empty_spawn_in_battle_zone(
    state: "GameState", unit_hex, active_zone_id: str
) -> bool:
    """Check if a hex is adjacent to an empty spawn point in the battle zone."""
    from goa2.engine.topology import get_topology_service

    topology = get_topology_service()
    neighbors = topology.get_connected_neighbors(unit_hex, state)
    for n in neighbors:
        tile = state.board.get_tile(n)
        if tile and tile.spawn_point and tile.zone_id == active_zone_id:
            if not tile.is_occupied:
                return True
    return False


# =============================================================================
# TIER II - BLUE: Weakness (SKILL)
# =============================================================================


@register_effect("weakness")
class WeaknessEffect(CardEffect):
    """
    Card Text: "This turn: Enemy heroes in radius have -4 Attack."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                stat_type=StatType.ATTACK,
                stat_value=-4,
                is_active=True,
            ),
        ]


# =============================================================================
# DEFENSE CARDS: Shield of Decay / Vampiric Shield / Aegis of Doom
# =============================================================================


class _SpawnPointDefenseEffect(CardEffect):
    """
    Base for defense cards that grant a bonus if there are 2+ empty spawn
    points in radius in the battle zone.
    """

    defense_bonus: int = 2

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        count = _count_empty_spawn_points(state, defender.id, stats.radius or 0)
        if count >= 2:
            return [
                SetContextFlagStep(key="defense_bonus", value=self.defense_bonus),
            ]
        return []


@register_effect("shield_of_decay")
class ShieldOfDecayEffect(_SpawnPointDefenseEffect):
    """
    Card Text: "+2 Defense if there are 2 or more empty spawn points in radius
    in the battle zone."
    """

    defense_bonus = 2


@register_effect("vampiric_shield")
class VampiricShieldEffect(_SpawnPointDefenseEffect):
    """
    Card Text: "+2 Defense if there are 2 or more empty spawn points in radius
    in the battle zone."
    """

    defense_bonus = 2


@register_effect("aegis_of_doom")
class AegisOfDoomEffect(_SpawnPointDefenseEffect):
    """
    Card Text: "+4 Defense if there are 2 or more empty spawn points in radius
    in the battle zone."
    """

    defense_bonus = 4


# =============================================================================
# GREEN SKILLS: Dark Ritual / Darker Ritual (gain coins)
# =============================================================================


class _RitualEffect(CardEffect):
    """
    Base for ritual cards: "If there are 2+ empty spawn points in radius in
    the battle zone, gain N coins."
    """

    coin_amount: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        count = _count_empty_spawn_points(state, hero.id, stats.radius or 0)
        if count >= 2:
            return [
                SetContextFlagStep(key="self", value=hero.id),
                GainCoinsStep(hero_key="self", amount=self.coin_amount),
            ]
        return []


@register_effect("dark_ritual")
class DarkRitualEffect(_RitualEffect):
    """
    Card Text: "If there are 2 or more empty spawn points in radius in the
    battle zone, gain 1 coin."
    """

    coin_amount = 1


@register_effect("darker_ritual")
class DarkerRitualEffect(_RitualEffect):
    """
    Card Text: "If there are 2 or more empty spawn points in radius in the
    battle zone, gain 2 coins."
    """

    coin_amount = 2


# =============================================================================
# UNTIERED - SILVER: Death Trap (SKILL)
# =============================================================================


@register_effect("death_trap")
class DeathTrapEffect(CardEffect):
    """
    Card Text: "An enemy hero in radius who is adjacent to an empty spawn
    point in the battle zone discards a card, if able."

    At build time, compute valid targets: enemy heroes in radius who are
    adjacent to an empty spawn point in the battle zone.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        from goa2.domain.types import BoardEntityID
        from goa2.engine.filters import ExcludeIdentityFilter

        radius = stats.radius or 0
        active_zone_id = state.active_zone_id
        if not active_zone_id:
            return []

        hero_hex = state.entity_locations.get(BoardEntityID(str(hero.id)))
        if not hero_hex:
            return []

        from goa2.engine.topology import get_topology_service

        topology = get_topology_service()

        # Find valid targets at build time: enemy heroes in radius adjacent
        # to an empty spawn point in the battle zone
        valid_target_ids: List[str] = []
        for team in state.teams.values():
            for enemy_hero in team.heroes:
                if enemy_hero.team == hero.team:
                    continue
                enemy_hex = state.entity_locations.get(
                    BoardEntityID(str(enemy_hero.id))
                )
                if not enemy_hex:
                    continue
                dist = topology.distance(hero_hex, enemy_hex, state)
                if dist > radius:
                    continue
                if _is_adjacent_to_empty_spawn_in_battle_zone(
                    state, enemy_hex, active_zone_id
                ):
                    valid_target_ids.append(str(enemy_hero.id))

        if not valid_target_ids:
            return []

        # Build exclude list: all enemy hero IDs NOT in valid_target_ids
        all_enemy_hero_ids: List[str] = []
        for team in state.teams.values():
            for enemy_hero in team.heroes:
                if enemy_hero.team != hero.team:
                    all_enemy_hero_ids.append(str(enemy_hero.id))
        exclude_ids = [eid for eid in all_enemy_hero_ids if eid not in valid_target_ids]

        # Store exclude list in context so ExcludeIdentityFilter can use it
        steps: List[GameStep] = []
        if exclude_ids:
            steps.append(
                SetContextFlagStep(key="death_trap_exclude", value=exclude_ids),
            )

        steps.extend(
            [
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select an enemy hero to discard a card (Death Trap)",
                    output_key="death_trap_victim",
                    is_mandatory=False,
                    filters=[
                        UnitTypeFilter(unit_type="HERO"),
                        TeamFilter(relation="ENEMY"),
                        RangeFilter(max_range=radius),
                        ExcludeIdentityFilter(
                            exclude_self=False,
                            exclude_keys=["death_trap_exclude"],
                        ),
                    ],
                ),
                ForceDiscardStep(victim_key="death_trap_victim"),
            ]
        )
        return steps


# =============================================================================
# ATTACK CARDS: Littlefinger of Death / Finger of Death
# =============================================================================


class _FingerOfDeathEffect(CardEffect):
    """
    Base for "Choose one — Target a unit adjacent to you.
    Target a hero in range who has one or more cards in the discard."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose mode
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent unit, 2 = Attack hero in range with cards in discard",
                output_key="fod_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="fod_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="fod_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            # 3a. Melee: target adjacent unit
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="chose_melee",
            ),
            # 3b. Ranged: target hero in range with cards in discard
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                active_if_key="chose_ranged",
                target_filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    HasCardsInDiscardFilter(min_cards=1),
                ],
            ),
        ]


@register_effect("littlefinger_of_death")
class LittlefingerOfDeathEffect(_FingerOfDeathEffect):
    """
    Card Text: "Choose one — Target a unit adjacent to you.
    Target a hero in range who has one or more cards in the discard."
    """

    pass


@register_effect("finger_of_death")
class FingerOfDeathEffect(_FingerOfDeathEffect):
    """
    Card Text: "Choose one — Target a unit adjacent to you.
    Target a hero in range who has one or more cards in the discard."
    """

    pass


# =============================================================================
# TIER III - RED: Middlefinger of Death (ATTACK)
# =============================================================================


@register_effect("middlefinger_of_death")
class MiddlefingerOfDeathEffect(CardEffect):
    """
    Card Text: "Choose one, or both, on different targets —
    • Target a unit adjacent to you.
    • Target a hero in range who has one or more cards in the discard."

    Two-step flow: player picks which attack to do first, then is optionally
    offered the other attack on a different target.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose which attack to do first
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent unit first, 2 = Attack hero in range with discard first",
                output_key="mfod_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="mfod_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee_first",
            ),
            CheckContextConditionStep(
                input_key="mfod_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged_first",
            ),
            # --- PATH A: Melee first ---
            # 3a. Attack adjacent unit, store target
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="chose_melee_first",
            ),
            # 3a-follow. Optionally select hero in range with discard (different target)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Optionally target a hero in range with discard (Middlefinger of Death)",
                output_key="mfod_second_victim",
                is_mandatory=False,
                active_if_key="chose_melee_first",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    HasCardsInDiscardFilter(min_cards=1),
                    ExcludeIdentityFilter(
                        exclude_self=False,
                        exclude_keys=["victim_id"],
                    ),
                ],
            ),
            # 3a-follow. Attack the second target if selected
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_id_key="mfod_second_victim",
                active_if_key="mfod_second_victim",
            ),
            # --- PATH B: Ranged first ---
            # 3b. Attack hero in range with discard, store target
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                active_if_key="chose_ranged_first",
                target_filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    HasCardsInDiscardFilter(min_cards=1),
                ],
            ),
            # 3b-follow. Optionally select adjacent unit (different target)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Optionally target an adjacent unit (Middlefinger of Death)",
                output_key="mfod_second_victim",
                is_mandatory=False,
                active_if_key="chose_ranged_first",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                    ExcludeIdentityFilter(
                        exclude_self=False,
                        exclude_keys=["victim_id"],
                    ),
                ],
            ),
            # 3b-follow. Attack the second target if selected
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                target_id_key="mfod_second_victim",
                active_if_key="mfod_second_victim",
            ),
        ]


# =============================================================================
# UNTIERED - GOLD: Dread Razor (ATTACK)
# =============================================================================


@register_effect("dread_razor")
class DreadRazorEffect(CardEffect):
    """
    Card Text: "Choose one — Target a unit adjacent to you.
    If you are adjacent to an empty spawn point in the battle zone,
    target a unit in range."

    At build time, check if hero is adjacent to an empty spawn point.
    If not, only offer melee option.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        from goa2.domain.types import BoardEntityID

        active_zone_id = state.active_zone_id
        hero_hex = state.entity_locations.get(BoardEntityID(str(hero.id)))

        can_ranged = False
        if hero_hex and active_zone_id:
            can_ranged = _is_adjacent_to_empty_spawn_in_battle_zone(
                state, hero_hex, active_zone_id
            )

        if not can_ranged:
            # Only melee option available
            return [
                AttackSequenceStep(
                    damage=stats.primary_value,
                    range_val=1,
                    is_ranged=True,
                ),
            ]

        # Both options available
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent unit, 2 = Attack unit in range",
                output_key="razor_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="razor_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="razor_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="chose_melee",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                active_if_key="chose_ranged",
            ),
        ]


# =============================================================================
# TIER II - RED: Burning Skull (ATTACK)
# =============================================================================


@register_effect("burning_skull")
class BurningSkullEffect(CardEffect):
    """
    Card Text: "Target a unit in range. After the attack: Move up to 1 minion
    adjacent to you 1 space, to a space not adjacent to you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Ranged attack
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a minion adjacent to you to move",
                output_key="skull_minion",
                is_mandatory=False,
                skip_immunity_filter=True,
                filters=[
                    RangeFilter(max_range=1),
                    UnitTypeFilter(unit_type="MINION"),
                    HasEmptyNeighborFilter(),
                ],
            ),
            # 3. Select destination: 1 space from minion, not adjacent to hero
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select destination (not adjacent to you)",
                output_key="skull_dest",
                active_if_key="skull_minion",
                filters=[
                    RangeFilter(max_range=1, origin_key="skull_minion"),
                    ObstacleFilter(is_obstacle=False),
                    RangeFilter(min_range=2, max_range=99),  # Not adjacent to hero
                ],
            ),
            # 4. Move minion
            MoveUnitStep(
                unit_key="skull_minion",
                destination_key="skull_dest",
                range_val=1,
                is_movement_action=False,
                active_if_key="skull_dest",
            ),
        ]


# =============================================================================
# TIER III - RED: Blazing Skull (ATTACK)
# =============================================================================


@register_effect("blazing_skull")
class BlazingSkullEffect(CardEffect):
    """
    Card Text: "Target a unit in range. After the attack: Move up to 2 minions
    adjacent to you 1 space each, to spaces not adjacent to you."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Ranged attack
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
            ),
            # 2. Select up to 2 adjacent minions
            MultiSelectStep(
                target_type=TargetType.UNIT,
                prompt="Select up to 2 minions adjacent to you to move",
                output_key="skull_minions",
                max_selections=2,
                min_selections=0,
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    UnitTypeFilter(unit_type="MINION"),
                ],
            ),
            # 3. For each selected minion: pick destination + move
            ForEachStep(
                list_key="skull_minions",
                item_key="current_skull_minion",
                steps_template=[
                    # Clear destination from previous iteration
                    SetContextFlagStep(key="skull_dest", value=None),
                    SelectStep(
                        target_type=TargetType.HEX,
                        prompt="Select destination (not adjacent to you)",
                        output_key="skull_dest",
                        is_mandatory=False,
                        filters=[
                            RangeFilter(max_range=1, origin_key="current_skull_minion"),
                            ObstacleFilter(is_obstacle=False),
                            RangeFilter(min_range=2, max_range=99),  # Not adjacent to hero
                        ],
                    ),
                    MoveUnitStep(
                        unit_key="current_skull_minion",
                        destination_key="skull_dest",
                        range_val=1,
                        is_movement_action=False,
                        active_if_key="skull_dest",
                    ),
                ],
            ),
        ]


# =============================================================================
# TIER III - BLUE: Enfeeblement (SKILL)
# =============================================================================


@register_effect("enfeeblement")
class EnfeeblementEffect(CardEffect):
    """
    Card Text: "This turn: Enemy heroes in radius have -6 Attack and cannot
               repeat actions."
    """

    def build_steps(
        self, state: "GameState", hero: "Hero", card: "Card", stats: "CardStats"
    ) -> List[GameStep]:
        return [
            # -6 Attack (same pattern as Weakness)
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                stat_type=StatType.ATTACK,
                stat_value=-6,
                is_active=True,
            ),
            # Cannot repeat actions
            CreateEffectStep(
                effect_type=EffectType.REPEAT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                is_active=True,
            ),
        ]


# =============================================================================
# TIER II - GREEN: Necromancy (SKILL)
# =============================================================================


def _build_respawn_steps(
    state: "GameState",
    hero: "Hero",
    stats: "CardStats",
    max_range: int,
) -> List[GameStep]:
    """
    Shared logic for Necromancy/Necromastery: find limbo minions, let the
    player choose one (if multiple), then respawn it at a filtered hex.
    """
    team_obj = state.teams.get(hero.team) if hero.team else None
    if not team_obj:
        return []

    # Find all friendly limbo minions, one per type
    seen_types = set()
    limbo_minions = []
    for m in team_obj.minions:
        if m.id not in state.entity_locations and m.type not in seen_types:
            seen_types.add(m.type)
            limbo_minions.append(m)
    if not limbo_minions:
        return []

    steps: List[GameStep] = []

    if len(limbo_minions) == 1:
        # Auto-select the only limbo minion
        steps.append(
            SetContextFlagStep(key="respawn_minion", value=limbo_minions[0].id),
        )
    else:
        # Let player choose which minion type to respawn
        number_options = list(range(1, len(limbo_minions) + 1))
        number_labels = {
            i + 1: f"{m.type.value} Minion"
            for i, m in enumerate(limbo_minions)
        }
        minion_id_map = {
            i + 1: m.id for i, m in enumerate(limbo_minions)
        }
        steps.append(
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose a minion to respawn",
                output_key="respawn_choice",
                number_options=number_options,
                number_labels=number_labels,
                is_mandatory=True,
            ),
        )
        # Map the number choice to the minion ID
        for num, minion_id in minion_id_map.items():
            steps.append(
                CheckContextConditionStep(
                    input_key="respawn_choice",
                    operator="==",
                    threshold=num,
                    output_key=f"chose_minion_{num}",
                ),
            )
            steps.append(
                SetContextFlagStep(
                    key="respawn_minion",
                    value=minion_id,
                    active_if_key=f"chose_minion_{num}",
                ),
            )

    # Respawn at filtered hex
    steps.append(
        RespawnMinionAtHexStep(
            team=hero.team,
            unit_key="respawn_minion",
            hex_filters=[
                SpawnPointTeamFilter(relation="FRIENDLY"),
                BattleZoneFilter(),
                ObstacleFilter(is_obstacle=False),
                RangeFilter(max_range=max_range),
            ],
        ),
    )
    return steps


@register_effect("necromancy")
class NecromancyEffect(CardEffect):
    """
    Card Text: "Respawn a friendly minion in an empty friendly spawn point
    adjacent to you in the battle zone."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _build_respawn_steps(state, hero, stats, max_range=1)


# =============================================================================
# TIER III - GREEN: Necromastery (SKILL)
# =============================================================================


@register_effect("necromastery")
class NecromasteryEffect(CardEffect):
    """
    Card Text: "Respawn a friendly minion in an empty friendly spawn point
    in radius in the battle zone."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return _build_respawn_steps(state, hero, stats, max_range=stats.radius or 0)


# =============================================================================
# NOT YET IMPLEMENTED — Cards requiring new infrastructure
# =============================================================================
#
# The following 3 cards are NOT registered. Each section explains the card text,
# what blocks implementation, and what infrastructure is needed.
#
# -----------------------------------------------------------------------------
# darkest_ritual (Tier III Green — SKILL)
# -----------------------------------------------------------------------------
# Card Text: "If there are 2 or more empty spawn points in radius in the
#             battle zone, gain 2 coins. If you have your Ultimate, gain an
#             Attack item."
#
# The coins part is trivial (same pattern as darker_ritual).
# BLOCKER: "gain an Attack item" has no existing step.
# NEEDS:
#   - A new GainItemStep (new StepType.GAIN_ITEM) that does
#     hero.items[StatType.ATTACK] = hero.items.get(StatType.ATTACK, 0) + 1
#   - The "if you have your Ultimate" condition = hero.level >= 8
#     (can be checked at build time since state is available)
#   - Register new StepType enum + add to AnyStep union in step_types.py
#
# -----------------------------------------------------------------------------
# tide_of_darkness (Ultimate Purple — PASSIVE)
# -----------------------------------------------------------------------------
# Card Text: "While you are performing an action, all spaces count as if they
#             were in the battle zone and had a friendly minion spawn point."
#
# This is the most complex card in Dodger's kit.
# BLOCKER: Global passive override that changes board perception.
# NEEDS:
#   - A passive effect (probably EffectType.ZONE_OVERRIDE or similar) that
#     temporarily modifies how the board/zone system works during Dodger's turn
#   - All spawn point checks must respect this override:
#     * _count_empty_spawn_points() helper
#     * _is_adjacent_to_empty_spawn_in_battle_zone() helper
#     * SpawnPointFilter / AdjacentSpawnPointFilter
#     * RespawnMinionStep spawn logic
#   - All "in the battle zone" checks must treat every hex as in-zone
#   - Implementation approach: add an active_effects check in the board/zone
#     query methods (e.g. state.board.get_zone_for_hex could check for
#     ZONE_OVERRIDE effects on the current actor)
#   - Should be implemented LAST, after all other Dodger cards work correctly
