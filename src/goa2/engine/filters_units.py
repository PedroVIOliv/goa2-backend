from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from goa2.domain.hex import Hex
from goa2.domain.models import FilterType, Hero, Minion, Unit
from goa2.domain.models.enums import (
    ActionType,
    MinionType,
    TokenType,
)
from goa2.domain.models.marker import MarkerType
from goa2.domain.models.token import Token
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition
from goa2.engine.topology import get_topology_service


class TeamFilter(FilterCondition):
    type: FilterType = FilterType.TEAM
    relation: Literal["FRIENDLY", "ENEMY", "SELF"]
    # RELATIVE to the actor executing the step

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        actor_id = state.current_actor_id
        if not actor_id:
            return False

        actor = state.get_entity(BoardEntityID(actor_id))
        target = state.get_entity(BoardEntityID(candidate)) if isinstance(candidate, str) else None

        if not actor or not target:
            # Only warn if strict logic required. For now, fail silently (filter mismatch)
            return False

        # Ensure both have 'team' attribute (Tokens might not)
        if not hasattr(actor, "team") or not hasattr(target, "team"):
            return False

        # Explicitly check if attributes are not None for Mypy
        actor_team = getattr(actor, "team", None)
        target_team = getattr(target, "team", None)

        if actor_team is None or target_team is None:
            return False

        if self.relation == "SELF":
            return actor.id == target.id

        is_same_team = actor_team == target_team

        if self.relation == "FRIENDLY":
            return is_same_team and (actor.id != target.id)
        elif self.relation == "ENEMY":
            return not is_same_team

        return False


class UnitTypeFilter(FilterCondition):
    type: FilterType = FilterType.UNIT_TYPE
    unit_type: Literal["HERO", "MINION", "TOKEN"]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = state.get_entity(BoardEntityID(candidate)) if isinstance(candidate, str) else None
        if not entity:
            return False

        if self.unit_type == "HERO":
            return isinstance(entity, Hero)
        elif self.unit_type == "MINION":
            return isinstance(entity, Minion)
        elif self.unit_type == "TOKEN":
            return isinstance(entity, Token)
        return False


class TokenTypeFilter(FilterCondition):
    type: FilterType = FilterType.TOKEN_TYPE
    token_type: TokenType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = state.get_entity(BoardEntityID(candidate)) if isinstance(candidate, str) else None
        return isinstance(entity, Token) and entity.token_type == self.token_type


class MinionTypesFilter(FilterCondition):
    type: FilterType = FilterType.MINION_TYPES
    minion_types: list[MinionType]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = state.get_entity(BoardEntityID(candidate)) if isinstance(candidate, str) else None
        if not entity or not isinstance(entity, Minion):
            return False

        return entity.type in self.minion_types


class AdjacencyFilter(FilterCondition):
    """
    Requires the target to be adjacent to a unit matching specific tags.
    E.g. "Adjacent to a Friendly Hero"

    If skip_immune=True, immune units are not counted as valid adjacent matches.
    This prevents e.g. charge effects from moving next to only immune enemies.
    """

    type: FilterType = FilterType.ADJACENCY
    target_tags: list[
        Literal["FRIENDLY", "ENEMY", "HERO", "MINION"]
    ]  # Tags are checked in AND fashion (must match all)
    skip_immune: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # Use topology-aware neighbors (respects reality splits)
        topology = get_topology_service()
        neighbors = topology.get_connected_neighbors(cand_hex, state)

        for n in neighbors:
            tile = state.board.get_tile(n)
            if not tile or not tile.occupant_id:
                continue

            # Use Unified Lookup
            occupant = state.get_entity(tile.occupant_id)
            if not occupant:
                continue

            actor_id = state.current_actor_id
            actor = state.get_entity(BoardEntityID(str(actor_id))) if actor_id else None

            if not actor:
                continue

            matches = True
            for tag in self.target_tags:
                if tag == "FRIENDLY":
                    # Mypy safety checks
                    occ_team = getattr(occupant, "team", None)
                    act_team = getattr(actor, "team", None)
                    if (
                        occ_team is None
                        or act_team is None
                        or occ_team != act_team
                        or occupant.id == actor.id
                    ):
                        matches = False
                elif tag == "ENEMY":
                    occ_team = getattr(occupant, "team", None)
                    act_team = getattr(actor, "team", None)
                    if occ_team is None or act_team is None or occ_team == act_team:
                        matches = False
                elif tag == "HERO":
                    if not isinstance(occupant, Hero):
                        matches = False
                elif tag == "MINION":
                    if not isinstance(occupant, Minion):
                        matches = False

            if matches:
                # Check if this adjacent unit is immune (heavy minion immunity
                # + ATTACK_IMMUNITY effects)
                if self.skip_immune and not ImmunityFilter().apply(
                    str(occupant.id), state, context
                ):
                    continue  # Skip immune units
                return True

        return False


class ImmunityFilter(FilterCondition):
    """
    Filters out candidates that are Immune.

    Checks two sources of immunity:
    1. Standard minion immunity (Heavy minions with friendly support)
    2. ATTACK_IMMUNITY effects (e.g., Expert Duelist - immune to attacks except from specific attacker)
    """

    type: FilterType = FilterType.IMMUNITY

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.domain.models.effect import EffectType
        from goa2.engine import rules  # Import inside to be safe

        target = state.get_entity(BoardEntityID(candidate)) if isinstance(candidate, str) else None
        if not target:
            return False

        if isinstance(target, Token) and target.is_immune_to_enemy_actions:
            actor_id = state.current_actor_id
            owner_id = target.owner_id
            actor = state.get_entity(BoardEntityID(str(actor_id))) if actor_id else None
            owner = state.get_hero(owner_id) if owner_id else None
            actor_team = getattr(actor, "team", None)
            owner_team = getattr(owner, "team", None)
            if actor_team is not None and owner_team is not None and actor_team != owner_team:
                return False

        # Check 1: Standard minion immunity (Heavy with support)
        if isinstance(target, Unit) and rules.is_immune(target, state):
            return False  # Immune = fails filter

        # Check 2: ATTACK_IMMUNITY effects
        # Only applies when current action is ATTACK
        current_action = context.get("current_action_type")
        if current_action == ActionType.ATTACK:
            current_actor_id = str(state.current_actor_id) if state.current_actor_id else None

            # Look for ATTACK_IMMUNITY effects where target is the protected unit
            for effect in state.active_effects:
                if effect.effect_type != EffectType.ATTACK_IMMUNITY:
                    continue
                if not effect.is_active:
                    continue

                # The effect protects its source_id (the hero who played the defense card)
                if effect.source_id != candidate:
                    continue

                # Check if current attacker is in the exception list
                if current_actor_id and current_actor_id in effect.except_attacker_ids:
                    continue  # This attacker is allowed to target

                # Target is immune to this attack
                return False

        return True  # Passes filter (not immune)


class UnitOnSpawnPointFilter(FilterCondition):
    """
    Filters unit candidates to those occupying a hex with a spawn point.
    """

    type: FilterType = FilterType.UNIT_ON_SPAWN_POINT

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, str):
            loc = state.entity_locations.get(BoardEntityID(candidate))
            if not loc:
                return False
            tile = state.board.get_tile(loc)
            if not tile:
                return False
            return tile.spawn_point is not None
        return False


class AdjacencyToContextFilter(FilterCondition):
    """
    Selects units adjacent to the entity ID stored in a context variable.
    """

    type: FilterType = FilterType.ADJACENCY_TO_CONTEXT
    target_key: str

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        target_id = context.get(self.target_key)

        if not target_id:
            return False

        target_hex = state.entity_locations.get(BoardEntityID(target_id))

        if not target_hex:
            return False

        cand_hex = None

        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # "Check via tile": Ensure both are valid board positions
        if not state.board.is_on_map(target_hex) or not state.board.is_on_map(cand_hex):
            return False
        # Use topology-aware adjacency (respects reality splits)
        topology = get_topology_service()
        return topology.are_adjacent(cand_hex, target_hex, state)


class ExcludeIdentityFilter(FilterCondition):
    """
    Excludes specific unit IDs or hexes from selection.
    Can exclude self and/or values found in context keys.
    Works for both unit ID (str) and Hex candidates.
    """

    type: FilterType = FilterType.EXCLUDE_IDENTITY
    exclude_self: bool = True
    exclude_keys: list[str] = Field(default_factory=list)

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if self.exclude_self and isinstance(candidate, str) and candidate == state.current_actor_id:
            return False
        for key in self.exclude_keys:
            val = context.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                if candidate in val:
                    return False
            elif val == candidate:
                return False
        return True


class ForcedMovementByEnemyFilter(FilterCondition):
    """
    Checks if the candidate is protected from forced movement by enemies.
    Delegates to ValidationService.
    """

    type: FilterType = FilterType.FORCED_MOVEMENT_BY_ENEMY

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return True

        result = state.validator.can_be_placed(
            state=state, unit_id=candidate, actor_id=actor_id, context=context
        )

        return result.allowed


class CanBePlacedByActorFilter(FilterCondition):
    """
    Filters out units that cannot be placed by the current actor.
    Delegates to ValidationService for actual logic.
    """

    type: FilterType = FilterType.CAN_BE_PLACED_BY_ACTOR

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return True  # No actor context, allow selection

        result = state.validator.can_be_placed(
            state=state, unit_id=candidate, actor_id=actor_id, context=context
        )

        return result.allowed


class HasMarkerFilter(FilterCondition):
    """
    Filters unit candidates to those that currently hold a specific marker.
    Non-hero candidates are rejected.
    """

    type: FilterType = FilterType.HAS_MARKER
    marker_type: MarkerType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False
        marker = state.markers.get(self.marker_type)
        if marker is None or not marker.is_placed:
            return False
        return marker.target_id == candidate
