"""PerformCardActionStep (NebKher P5 — Mind Grip bullet 1).

"Perform an action on the card in the previous turn slot of an enemy hero in
range; if you would place any tokens this way, place Illusion tokens instead;
skip giving markers."

Locked interpretations (2026-07-07):
- The chooser is exactly the normal card-resolution menu minus defense
  (primary, secondary movement, Hold, Fast Travel where legal — Hold always
  exists, so every card offers at least one action).
- build_steps is called when the primary action is chosen.
- Values come from THAT card, computed with the PERFORMER as actor.
- Token placements inside the copied effect place Illusion tokens instead.
- Marker steps are skipped; the rest of the effect continues.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType, InputResponse
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    Team,
    TeamColor,
    TokenType,
)
from goa2.domain.models.enums import StatType
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.handler import process_stack, push_steps, submit_input
from goa2.engine.setup import GameSetup
from goa2.engine.steps import PerformCardActionStep, PlaceMarkerStep, PlaceTokenStep
from goa2.engine.steps.utility import SetContextFlagStep

TOKEN_EFFECT_ID = "test_pca_token_effect"
MARKER_EFFECT_ID = "test_pca_marker_effect"


@register_effect(TOKEN_EFFECT_ID)
class _TokenPlacingEffect(CardEffect):
    """Places a TREE token at a fixed hex (target_hex pre-seeded)."""

    def build_steps(self, state, hero, card, stats):
        return [PlaceTokenStep(token_type=TokenType.TREE, hex_key="pca_tree_hex")]


@register_effect(MARKER_EFFECT_ID)
class _MarkerGivingEffect(CardEffect):
    """Gives a marker, then sets a flag (the flag must survive the skip)."""

    def build_steps(self, state, hero, card, stats):
        return [
            PlaceMarkerStep(marker_type=MarkerType.VENOM, target_id="hero_enemy", value=-1),
            SetContextFlagStep(key="pca_after_marker", value=True),
        ]


def _card(
    card_id: str,
    *,
    primary: ActionType = ActionType.ATTACK,
    primary_value: int | None = 3,
    effect_id: str = "",
    secondary: dict | None = None,
) -> Card:
    card = Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=primary,
        primary_action_value=primary_value,
        secondary_actions=dict(secondary or {ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3}),
        effect_id=effect_id,
        effect_text="",
    )
    card.state = CardState.RESOLVED
    card.is_facedown = False
    return card


def _state() -> GameState:
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(6)} | {Hex(q=0, r=1, s=-1), Hex(q=1, r=1, s=-2)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    actor = Hero(id="hero_actor", name="Actor", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[actor], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_actor", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=3, r=0, s=-3))
    state.current_actor_id = "hero_actor"
    GameSetup._initialize_token_pool(state)
    return state


def _run_perform(state: GameState, card: Card, **step_kwargs):
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = [card]
    enemy.resolved_turn_count = 1
    state.execution_context["pca_card"] = card.id
    state.execution_context["pca_owner"] = "hero_enemy"
    push_steps(
        state,
        [
            PerformCardActionStep(
                card_key="pca_card",
                card_owner_key="pca_owner",
                hero_id="hero_actor",
                **step_kwargs,
            )
        ],
    )
    return process_stack(state)


def _option_ids(result) -> list[str]:
    assert result.input_request is not None
    return [opt.id for opt in result.input_request.options]


def test_menu_offers_all_actions_except_defense() -> None:
    state = _state()
    result = _run_perform(state, _card("enemy_attack_card"))

    ids = _option_ids(result)
    assert "ATTACK" in ids  # primary
    assert "MOVEMENT" in ids  # secondary
    assert "HOLD" in ids  # always available
    assert "DEFENSE" not in ids


def test_menu_routed_to_performer() -> None:
    state = _state()
    result = _run_perform(state, _card("enemy_attack_card"))
    assert result.input_request.player_id == "hero_actor"


def test_invalid_action_rerequests_the_same_menu() -> None:
    state = _state()
    first = _run_perform(state, _card("enemy_attack_card"))
    assert first.input_request is not None
    expected_options = _option_ids(first)

    submit_input(
        state,
        InputResponse(request_id=first.input_request.id, selection="NOT_AN_OPTION"),
    )
    retried = process_stack(state)

    assert retried.input_request is not None
    assert retried.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert _option_ids(retried) == expected_options
    assert len(state.execution_stack) == 1
    assert isinstance(state.execution_stack[-1], PerformCardActionStep)


def test_primary_defense_card_offers_only_non_defense_options() -> None:
    state = _state()
    card = _card(
        "enemy_defense_card",
        primary=ActionType.DEFENSE,
        primary_value=7,
        secondary={ActionType.MOVEMENT: 2},
    )
    result = _run_perform(state, card)

    ids = _option_ids(result)
    assert "DEFENSE" not in ids
    assert "MOVEMENT" in ids
    assert "HOLD" in ids


def test_attack_value_computed_with_performer_stats() -> None:
    """Card attack 3 + performer's +1 ATTACK item = menu shows 4."""
    state = _state()
    actor = state.get_hero("hero_actor")
    actor.items[StatType.ATTACK] = 1

    result = _run_perform(state, _card("enemy_attack_card", primary_value=3))
    attack_opt = next(o for o in result.input_request.options if o.id == "ATTACK")
    assert "4" in attack_opt.text


def test_secondary_movement_moves_the_performer() -> None:
    state = _state()
    result = _run_perform(state, _card("enemy_attack_card"))

    state.execution_stack[-1].pending_input = {"selection": "MOVEMENT"}
    result = process_stack(state)

    # The follow-up is a movement selection for the PERFORMER.
    assert result.input_request is not None
    assert result.input_request.player_id == "hero_actor"


def test_primary_with_token_placement_substitutes_illusions() -> None:
    state = _state()
    state.execution_context["pca_tree_hex"] = Hex(q=1, r=1, s=-2)
    card = _card(
        "enemy_token_card",
        primary=ActionType.SKILL,
        primary_value=None,
        effect_id=TOKEN_EFFECT_ID,
    )
    _run_perform(state, card, token_type_override=TokenType.ILLUSION)

    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    process_stack(state)

    tile = state.board.get_tile(Hex(q=1, r=1, s=-2))
    assert tile is not None and tile.occupant_id is not None
    token = state.get_entity(tile.occupant_id)
    assert token is not None
    assert token.token_type == TokenType.ILLUSION
    # Pulled from the Illusion supply, not the Tree supply.
    assert len(state.token_pool[TokenType.TREE]) == 3


def test_skip_markers_skips_marker_and_continues() -> None:
    state = _state()
    card = _card(
        "enemy_marker_card",
        primary=ActionType.SKILL,
        primary_value=None,
        effect_id=MARKER_EFFECT_ID,
    )
    _run_perform(state, card, skip_markers=True)

    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    process_stack(state)

    assert state.markers.get(MarkerType.VENOM) is None
    assert state.execution_context.get("pca_after_marker") is True


def test_markers_still_given_without_skip() -> None:
    state = _state()
    card = _card(
        "enemy_marker_card2",
        primary=ActionType.SKILL,
        primary_value=None,
        effect_id=MARKER_EFFECT_ID,
    )
    _run_perform(state, card)

    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    process_stack(state)

    assert state.markers.get(MarkerType.VENOM) is not None
