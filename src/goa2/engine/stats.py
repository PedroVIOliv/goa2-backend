from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from goa2.domain.state import GameState
from goa2.domain.models import MinionType, Minion, Hero, StatType, ActionType
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.domain.types import UnitID, BoardEntityID
from goa2.domain.hex import Hex
from goa2.engine.topology import (
    get_connected_ring,
    hex_in_scope as topology_hex_in_scope,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card
    from goa2.engine.effects import StatAura


def _is_effect_active(effect: ActiveEffect, state: GameState) -> bool:
    """
    Check if effect is currently active based on duration and is_active flag.
    Mirrors ValidationService._is_modifier_active() logic.
    """
    # PASSIVE effects are ALWAYS active
    if effect.duration == DurationType.PASSIVE:
        return True

    # Card-based effects use explicit is_active flag
    if effect.source_card_id:
        if not effect.is_active:
            return False

    # Check temporal duration
    if effect.duration == DurationType.THIS_TURN:
        return (
            state.turn == effect.created_at_turn
            and state.round == effect.created_at_round
        )

    if effect.duration == DurationType.NEXT_TURN:
        if state.round == effect.created_at_round:
            return state.turn == effect.created_at_turn + 1
        return False

    if effect.duration == DurationType.THIS_ROUND:
        return state.round == effect.created_at_round

    return False


def _get_origin_hex(effect: ActiveEffect, state: GameState) -> Optional[Hex]:
    """Resolve origin point for spatial effects."""
    if effect.scope.origin_hex:
        return effect.scope.origin_hex
    origin_id = effect.scope.origin_id or effect.source_id
    return state.entity_locations.get(BoardEntityID(origin_id))


def _hex_in_scope(effect: ActiveEffect, hex: Hex, state: GameState) -> bool:
    """Check if a hex is within effect's spatial scope (topology-aware)."""
    scope = effect.scope

    origin = _get_origin_hex(effect, state)
    if not origin and scope.shape != Shape.GLOBAL:
        return False

    # Use TopologyService for consolidated, topology-aware scope checking
    return topology_hex_in_scope(
        origin if origin else hex,  # For GLOBAL, origin doesn't matter
        hex,
        scope.shape,
        scope.range,
        state,
        scope.direction,
    )


def _matches_affects_filter(
    effect: ActiveEffect, target_id: str, state: GameState
) -> bool:
    """Check if target matches the relational filter."""
    affects = effect.scope.affects

    if affects == AffectsFilter.ALL_UNITS:
        return True

    source = state.get_entity(BoardEntityID(effect.source_id))
    target = state.get_entity(BoardEntityID(target_id))

    if not source or not target:
        return False

    source_team = getattr(source, "team", None)
    target_team = getattr(target, "team", None)
    is_hero = isinstance(target, Hero)
    is_minion = isinstance(target, Minion)

    if affects == AffectsFilter.SELF:
        return effect.source_id == target_id

    if affects == AffectsFilter.FRIENDLY_UNITS:
        return source_team == target_team

    if affects == AffectsFilter.FRIENDLY_HEROES:
        return source_team == target_team and is_hero

    if affects == AffectsFilter.ENEMY_UNITS:
        return source_team != target_team

    if affects == AffectsFilter.ENEMY_HEROES:
        return source_team != target_team and is_hero

    if affects == AffectsFilter.ALL_HEROES:
        return is_hero

    if affects == AffectsFilter.ALL_MINIONS:
        return is_minion

    return False


def is_unit_in_effect_scope(
    effect: ActiveEffect, unit_id: str, state: GameState
) -> bool:
    """Check if a unit is within an effect's scope (spatial + relational)."""
    unit_hex = state.entity_locations.get(BoardEntityID(unit_id))
    if not unit_hex:
        return False

    if not _matches_affects_filter(effect, unit_id, state):
        return False

    return _hex_in_scope(effect, unit_hex, state)


def get_computed_stat(
    state: GameState, unit_id: UnitID, stat_type: StatType, base_value: int = 0
) -> int:
    """
    Calculates the final value of a stat for a unit.
    Formula: Base + Items + Modifiers + ActiveEffects + Markers
    """
    unit = state.get_unit(unit_id)
    if not unit:
        return base_value

    total = base_value

    # 1. Add Item Bonuses (for Heroes)
    if isinstance(unit, Hero):
        item_bonus = unit.items.get(stat_type, 0)
        # Check for DOUBLE_ITEMS effect (Min: Inner Strength / Perfect Self)
        if item_bonus > 0:
            for effect in state.active_effects:
                if (
                    effect.effect_type == EffectType.DOUBLE_ITEMS
                    and effect.source_id == str(unit_id)
                    and _is_effect_active(effect, state)
                ):
                    item_bonus *= 2
                    break
        total += item_bonus

    # 2. Add AREA_STAT_MODIFIER effects
    for effect in state.active_effects:
        if effect.effect_type != EffectType.AREA_STAT_MODIFIER:
            continue
        if effect.stat_type != stat_type:
            continue
        if not _is_effect_active(effect, state):
            continue
        if not is_unit_in_effect_scope(effect, str(unit_id), state):
            continue
        total += effect.stat_value

    # 3. Add filter-based aura effects (for heroes with active auras)
    if isinstance(unit, Hero):
        from goa2.engine.effects import get_active_aura_effects

        for _card, effect in get_active_aura_effects(state, unit):
            for aura in effect.get_stat_auras():
                if aura.stat_type != stat_type:
                    continue
                # Check conditional aura restrictions
                if aura.basic_only or aura.action_type_only is not None:
                    card = unit.current_turn_card
                    if not card:
                        continue
                    if aura.basic_only and not card.is_basic:
                        continue
                    if aura.action_type_only is not None and card.primary_action != aura.action_type_only:
                        continue
                # Apply flat bonus or count-based bonus
                if aura.flat_bonus is not None:
                    total += aura.flat_bonus
                else:
                    hero_hex = state.entity_locations.get(BoardEntityID(str(unit_id)))
                    if not hero_hex:
                        continue
                    saved_actor = state.current_actor_id
                    state.current_actor_id = unit_id
                    try:
                        count = _count_matching_units(state, aura)
                    finally:
                        state.current_actor_id = saved_actor
                    total += count * aura.multiplier

    # 4. Add Marker effects (for heroes with markers on them)
    if isinstance(unit, Hero):
        for marker in state.get_markers_on_hero(str(unit_id)):
            for marker_stat_type, marker_value in marker.get_stat_effects():
                if marker_stat_type == stat_type:
                    total += marker_value

    return total


def _count_matching_units(state: GameState, aura: "StatAura") -> int:
    """Count all units on the board that match all aura filters.
    Range is handled by RangeFilter within count_filters."""
    count = 0
    for entity_id in state.entity_locations:
        if all(f.apply(str(entity_id), state, {}) for f in aura.count_filters):
            count += 1
    return count


def calculate_minion_defense_modifier(state: GameState, target_unit_id: UnitID) -> int:
    """
    Calculates the cumulative defense modifier provided by nearby minions.
    Uses Hex.ring for optimized spatial lookups.
    Respects topology constraints (reality splits).
    """
    target_loc = state.unit_locations.get(target_unit_id)
    if not target_loc:
        return 0

    target_unit = state.get_unit(target_unit_id)
    if not target_unit:
        return 0

    total_mod = 0
    target_team = target_unit.team

    def get_unit_at(hex_coord):
        tile = state.board.tiles.get(hex_coord)
        if tile and tile.occupant_id:
            return state.get_unit(UnitID(str(tile.occupant_id)))
        return None

    # --- RANGE 1 (Ring 1) ---
    for hex_coord in get_connected_ring(target_loc, 1, state):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue

        if unit.team == target_team:
            if unit.type in (MinionType.MELEE, MinionType.HEAVY):
                total_mod += 1
        else:
            total_mod -= 1

    # --- RANGE 2 (Ring 2) ---
    for hex_coord in get_connected_ring(target_loc, 2, state):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue

        if unit.team != target_team and unit.type == MinionType.RANGED:
            total_mod -= 1

    return total_mod


# -----------------------------------------------------------------------------
# Card Stats Helper
# -----------------------------------------------------------------------------


@dataclass
class CardStats:
    """
    Computed stats for a card's primary action with all buffs applied.

    Attributes:
        primary_value: The computed value for the primary action (damage/movement/defense)
        range: Attack/skill range. 1 (adjacent) if card is not ranged.
        radius: Area of effect. None if card has no radius.
    """

    primary_value: int = 0
    range: int = 1
    radius: Optional[int] = None


def compute_card_stats(state: GameState, hero_id: UnitID, card: Card) -> CardStats:
    """
    Computes all relevant stats for a card's primary action, applying buffs.

    This is the canonical way to get buffed stats for card effects:
    - primary_value: Based on card.primary_action type
      - ATTACK → applies ATTACK stat buffs
      - MOVEMENT → applies MOVEMENT stat buffs
      - DEFENSE → applies DEFENSE stat buffs
      - SKILL → 0 (skills don't have a numeric primary value)

    - range: Only computed with RANGE buffs if card.is_ranged is True,
             otherwise fixed at 1 (adjacent, not buffable)

    - radius: Only computed with RADIUS buffs if card.radius_value exists

    Usage:
        stats = compute_card_stats(state, hero.id, card)
        AttackSequenceStep(damage=stats.primary_value, range_val=stats.range)
    """
    result = CardStats()

    # 1. Compute primary action value with appropriate stat type
    base_value = card.current_primary_action_value or 0

    if card.current_primary_action == ActionType.ATTACK:
        result.primary_value = get_computed_stat(
            state, hero_id, StatType.ATTACK, base_value
        )
    elif card.current_primary_action == ActionType.MOVEMENT:
        result.primary_value = get_computed_stat(
            state, hero_id, StatType.MOVEMENT, base_value
        )
    elif card.current_primary_action in (ActionType.DEFENSE, ActionType.DEFENSE_SKILL):
        result.primary_value = get_computed_stat(
            state, hero_id, StatType.DEFENSE, base_value
        )
    else:
        # SKILL or other action types have no numeric primary value
        result.primary_value = 0

    # 2. Compute range (only if card is ranged, otherwise fixed at 1)
    if card.is_ranged and card.range_value:
        result.range = get_computed_stat(
            state, hero_id, StatType.RANGE, card.range_value
        )
    else:
        result.range = 1  # Adjacent, not buffable

    # 3. Compute radius (only if card has radius_value)
    if card.radius_value:
        result.radius = get_computed_stat(
            state, hero_id, StatType.RADIUS, card.radius_value
        )
    else:
        result.radius = None

    return result
