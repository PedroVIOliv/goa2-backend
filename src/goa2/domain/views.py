"""
Player-Scoped Views - Phase 4 of Client-Readiness Roadmap.

Provides view filtering so players only see what they're allowed to see.
In GoA2, visibility is purely based on card faceup/facedown state,
not team affiliation (allies see enemies' faceup cards too).
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List

from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.domain.models.card import Card
from goa2.domain.models.unit import Hero, Minion
from goa2.domain.models.enums import GamePhase, StatType
from goa2.domain.types import BoardEntityID


def build_view(
    state: GameState, for_hero_id: Optional[HeroID] = None
) -> Dict[str, Any]:
    """
    Build a player-scoped view of the game state.

    Visibility rules:
    - Requesting hero (for_hero_id): Sees all their cards, including facedown ones
    - All other heroes: Only see faceup cards (use card.current_* pattern)
    - Discard piles: Always visible (public information)
    - Board, units, effects, life counters: Always visible (public information)

    Args:
        state: The current game state
        for_hero_id: Hero ID to scope the view to. If None, returns public view
                     (no facedown cards visible to anyone, like a spectator)

    Returns:
        Serializable dict representation of the game state with filtered cards
    """
    # Build teams view
    teams_view: Dict[str, Any] = {}
    for team_color, team in state.teams.items():
        teams_view[team_color.value] = _build_team_view(team, for_hero_id)

    # Build board view (public info)
    board_view = _build_board_view(state)

    # Build effects view (public info)
    effects_view = _build_effects_view(state)

    # Build markers view (public info)
    markers_view = _build_markers_view(state)

    # Build tokens view (public info, with facedown hiding)
    tokens_view = _build_tokens_view(state, for_hero_id)

    # Build unresolved cards view (resolution order for frontend)
    unresolved_cards_view = _build_unresolved_cards_view(state, for_hero_id)

    return {
        "phase": state.phase.value,
        "round": state.round,
        "turn": state.turn,
        "current_actor_id": state.current_actor_id,
        "unresolved_hero_ids": list(state.unresolved_hero_ids),
        "unresolved_cards": unresolved_cards_view,
        "active_zone_id": state.active_zone_id,
        "cheats_enabled": state.cheats_enabled,
        "tie_breaker_team": state.tie_breaker_team.value,
        "teams": teams_view,
        "board": board_view,
        "effects": effects_view,
        "markers": markers_view,
        "tokens": tokens_view,
    }


def _build_unresolved_cards_view(
    state: GameState, for_hero_id: Optional[HeroID] = None
) -> List[Dict[str, Any]]:
    """
    Build an ordered list of unresolved cards for frontend visualization.

    Returns cards sorted by resolution priority (highest initiative first),
    with ties broken by tie_breaker_team. Only populated during RESOLUTION phase.
    """
    if state.phase != GamePhase.RESOLUTION:
        return []

    hero_ids = list(state.unresolved_hero_ids)
    if state.current_actor_id:
        hero_ids = [state.current_actor_id] + hero_ids

    if not hero_ids:
        return []

    from goa2.engine.stats import get_computed_stat

    entries = []
    for h_id in hero_ids:
        hero = state.get_hero(h_id)
        if not hero or not hero.current_turn_card:
            continue

        card = hero.current_turn_card
        base_init = card.get_base_stat_value(StatType.INITIATIVE)
        computed_init = get_computed_stat(state, h_id, StatType.INITIATIVE, base_init)

        entries.append(
            {
                "hero_id": h_id,
                "initiative": computed_init,
                "team": hero.team,
                "card": _build_card_view(card, is_own_hero=(h_id == for_hero_id)),
            }
        )

    # Sort: highest initiative first, tie-breaker team favored among same initiative
    tie_breaker = state.tie_breaker_team
    entries.sort(key=lambda e: (-e["initiative"], 0 if e["team"] == tie_breaker else 1))

    # Remove internal team field before returning
    for entry in entries:
        del entry["team"]

    return entries


def _build_team_view(team, for_hero_id: Optional[HeroID]) -> Dict[str, Any]:
    """Build a view for a single team."""
    return {
        "color": team.color.value,
        "life_counters": team.life_counters,
        "heroes": [_build_hero_view(hero, for_hero_id) for hero in team.heroes],
        "minions": [_build_minion_view(minion) for minion in team.minions],
    }


def _build_hero_view(hero: Hero, for_hero_id: Optional[HeroID]) -> Dict[str, Any]:
    """
    Build a view for a single hero.

    Visibility:
    - If hero.id == for_hero_id: Show all cards (hand, deck, played, current_turn)
    - Otherwise: Hand is empty, other card arrays show faceup cards, facedown cards hide sensitive fields
    - Discard pile: Always visible (public info)
    """
    is_own_hero = hero.id == for_hero_id

    return {
        "id": hero.id,
        "name": hero.name,
        "title": hero.title,
        "team": hero.team.value if hero.team else None,
        "level": hero.level,
        "gold": hero.gold,
        "items": hero.items,
        # Hand: Own hero sees all, others see empty array
        "hand": (
            [_build_card_view(card, is_own_hero=True) for card in hero.hand]
            if is_own_hero
            else []
        ),
        # Deck: Own hero sees full deck, others see count only
        "deck": (
            [_build_card_view(card, is_own_hero=is_own_hero) for card in hero.deck]
            if is_own_hero
            else {"count": len(hero.deck)}
        ),
        # Played cards: Own hero sees all, others see faceup only
        "played_cards": [
            _build_card_view(card, is_own_hero=is_own_hero)
            for card in hero.played_cards
        ],
        # Current turn card: Own hero sees all, others see faceup only
        "current_turn_card": (
            _build_card_view(hero.current_turn_card, is_own_hero=is_own_hero)
            if hero.current_turn_card
            else None
        ),
        # Discard pile: Always visible (public info) - use is_own_hero=True so all cards show full info
        "discard_pile": [
            _build_card_view(card, is_own_hero=True) for card in hero.discard_pile
        ],
        # Ultimate card: Own hero sees it, others see faceup only
        "ultimate_card": (
            _build_card_view(hero.ultimate_card, is_own_hero=is_own_hero)
            if hero.ultimate_card
            else None
        ),
    }


def _build_minion_view(minion: Minion) -> Dict[str, Any]:
    """Build a view for a minion (public info only)."""
    return {
        "id": minion.id,
        "type": minion.type.value,
        "team": minion.team.value if minion.team else None,
        "value": minion.value,  # 2 for MELEE/RANGED, 4 for HEAVY
        "is_heavy": minion.is_heavy,
    }


def _build_card_view(
    card: Optional[Card], is_own_hero: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Build a view for a single card.

    Args:
        card: The card to view (may be None)
        is_own_hero: If True, show all details even if facedown.
                     If False, show all for faceup, hide sensitive fields for facedown.

    Returns:
        Dict with card details, or None if card is None
    """
    if card is None:
        return None

    if is_own_hero or not card.is_facedown:
        # Own hero or faceup card: show all details
        return {
            "id": card.id,
            "name": card.name,
            "tier": card.tier.value,
            "color": card.color.value if card.color else None,
            "primary_action": (
                card.primary_action.value if card.primary_action else None
            ),
            "primary_action_value": card.primary_action_value,
            "secondary_actions": {
                k.value: v for k, v in card.secondary_actions.items()
            },
            "effect_id": card.effect_id,
            "effect_text": card.effect_text,
            "initiative": card.initiative,
            "state": card.state.value,
            "is_facedown": card.is_facedown,
            "is_ranged": card.is_ranged,
            "range_value": card.range_value,
            "radius_value": card.radius_value,
            "item": card.item.value if card.item else None,
            "is_active": card.is_active,
        }
    else:
        # Other hero's facedown card: use current_* pattern and hide sensitive fields
        return {
            "tier": card.current_tier.value,
            "color": card.current_color.value if card.current_color else None,
            "primary_action": (
                card.current_primary_action.value
                if card.current_primary_action
                else None
            ),
            "primary_action_value": card.current_primary_action_value,
            "secondary_actions": {
                k.value: v for k, v in card.current_secondary_actions.items()
            },
            "effect_id": card.current_effect_id,
            "effect_text": card.current_effect_text,
            "initiative": card.current_initiative,
            "state": card.state.value,
            "is_facedown": card.is_facedown,
            "item": card.item.value if card.item else None,
            "is_active": card.is_active,
        }


def _build_board_view(state: GameState) -> Dict[str, Any]:
    """Build a view of the board (public info)."""
    # Get all tiles with occupant info
    tiles_view = {}
    for hex_obj, tile in state.board.tiles.items():
        tile_id = f"{hex_obj.q}_{hex_obj.r}_{hex_obj.s}"
        tile_data = {
            "hex": {"q": hex_obj.q, "r": hex_obj.r, "s": hex_obj.s},
            "zone_id": tile.zone_id,
            "is_terrain": tile.is_terrain,
            "occupant_id": tile.occupant_id,
            "spawn_point": (
                {
                    "location": {
                        "q": tile.spawn_point.location.q,
                        "r": tile.spawn_point.location.r,
                        "s": tile.spawn_point.location.s,
                    },
                    "team": tile.spawn_point.team.value,
                    "type": tile.spawn_point.type.value,
                    "minion_type": (
                        tile.spawn_point.minion_type.value
                        if tile.spawn_point.minion_type
                        else None
                    ),
                }
                if tile.spawn_point
                else None
            ),
        }
        tiles_view[tile_id] = tile_data

    # Get zone info
    zones_view = {}
    for zone in state.board.zones.values():
        zones_view[zone.id] = {
            "id": zone.id,
            "neighbors": zone.neighbors,
            "spawn_points": [
                {
                    "location": {
                        "q": sp.location.q,
                        "r": sp.location.r,
                        "s": sp.location.s,
                    },
                    "team": sp.team.value,
                    "type": sp.type.value,
                    "minion_type": sp.minion_type.value if sp.minion_type else None,
                }
                for sp in zone.spawn_points
            ],
        }

    # Get entity locations
    entity_locations = {
        entity_id: {"q": h.q, "r": h.r, "s": h.s}
        for entity_id, h in state.entity_locations.items()
    }

    return {
        "tiles": tiles_view,
        "zones": zones_view,
        "entity_locations": entity_locations,
    }


def _build_effects_view(state: GameState) -> List[Dict[str, Any]]:
    """Build a view of active effects (public info)."""
    effects_view = []

    for effect in state.active_effects:
        origin_hex = effect.scope.origin_hex
        effect_view = {
            "id": effect.id,
            "type": effect.effect_type.value,
            "source_card_id": effect.source_card_id,
            "duration": effect.duration.value,
            "is_active": effect.is_active,
            "scope": {
                "shape": effect.scope.shape.value,
                "range": effect.scope.range,
                "origin_id": effect.scope.origin_id,
                "origin": (
                    {"q": origin_hex.q, "r": origin_hex.r, "s": origin_hex.s}
                    if origin_hex
                    else None
                ),
                "affects": effect.scope.affects.value,
            },
            "stat_type": effect.stat_type.value if effect.stat_type else None,
            "stat_value": effect.stat_value,
        }
        effects_view.append(effect_view)

    return effects_view


def _build_tokens_view(
    state: GameState, for_hero_id: Optional[HeroID] = None
) -> List[Dict[str, Any]]:
    """Build a view of tokens on the board with facedown hiding."""
    viewer_team = None
    if for_hero_id:
        hero = state.get_hero(for_hero_id)
        if hero:
            viewer_team = hero.team

    tokens_view = []
    for tokens in state.token_pool.values():
        for token in tokens:
            loc = state.entity_locations.get(BoardEntityID(str(token.id)))

            visible_type = token.token_type.value
            if token.is_facedown:
                owner_team = None
                if token.owner_id:
                    owner = state.get_hero(token.owner_id)
                    if owner:
                        owner_team = owner.team
                if viewer_team is None or viewer_team != owner_team:
                    visible_type = "mine"

            is_hidden = token.is_facedown and visible_type == "mine"
            tokens_view.append(
                {
                    "id": str(token.id),
                    "name": "Mine" if is_hidden else token.name,
                    "token_type": visible_type,
                    "owner_id": str(token.owner_id) if token.owner_id else None,
                    "is_facedown": token.is_facedown,
                    "is_passable": token.is_passable,
                    "hex": ({"q": loc.q, "r": loc.r, "s": loc.s} if loc else None),
                }
            )
    return tokens_view


def _build_markers_view(state: GameState) -> Dict[str, Any]:
    """Build a view of placed markers (public info)."""
    markers_view = {}

    for marker_type, marker in state.markers.items():
        markers_view[marker_type.value] = {
            "target_id": marker.target_id,
            "value": marker.value,
            "source_id": marker.source_id,
        }

    return markers_view
