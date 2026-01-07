from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from goa2.domain.state import GameState
from goa2.domain.models import MinionType, Minion, Hero, StatType, ActionType
from goa2.domain.types import UnitID, BoardEntityID

if TYPE_CHECKING:
    from goa2.domain.models import Card


def get_computed_stat(
    state: GameState, unit_id: UnitID, stat_type: StatType, base_value: int = 0
) -> int:
    """
    Calculates the final value of a stat for a unit.
    Formula: Base + Items + Modifiers
    """
    unit = state.get_unit(unit_id)
    if not unit:
        return base_value

    total = base_value

    # 1. Add Item Bonuses (for Heroes)
    if isinstance(unit, Hero):
        total += unit.items.get(stat_type, 0)

    # 2. Add Active Modifiers
    for mod in state.active_modifiers:
        if str(mod.target_id) == str(unit_id) and mod.stat_type == stat_type:
            total += mod.value_mod

    return total


def has_status(state: GameState, entity_id: BoardEntityID, status_tag: str) -> bool:
    """Checks if an entity has a specific status tag/override."""
    for mod in state.active_modifiers:
        if str(mod.target_id) == str(entity_id) and mod.status_tag == status_tag:
            return True
    return False


def calculate_minion_defense_modifier(state: GameState, target_unit_id: UnitID) -> int:
    """
    Calculates the cumulative defense modifier provided by nearby minions.
    Uses Hex.ring for optimized spatial lookups.
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
    for hex_coord in state.board.get_ring(target_loc, 1):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue

        if unit.team == target_team:
            if unit.type in (MinionType.MELEE, MinionType.HEAVY):
                total_mod += 1
        else:
            total_mod -= 1

    # --- RANGE 2 (Ring 2) ---
    for hex_coord in state.board.get_ring(target_loc, 2):
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
    base_value = card.primary_action_value or 0

    if card.primary_action == ActionType.ATTACK:
        result.primary_value = get_computed_stat(
            state, hero_id, StatType.ATTACK, base_value
        )
    elif card.primary_action == ActionType.MOVEMENT:
        result.primary_value = get_computed_stat(
            state, hero_id, StatType.MOVEMENT, base_value
        )
    elif card.primary_action == ActionType.DEFENSE:
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
