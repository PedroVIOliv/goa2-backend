"""Tests for Min's Smoke Bomb (silver card) effect."""
import pytest

from goa2.domain.board import Board
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Card,
    CardColor,
    CardTier,
    ActionType,
    Team,
    TeamColor,
    Hero,
    Token,
    TokenType,
)
from goa2.domain.models.effect import EffectType
from goa2.domain.state import GameState
from goa2.domain.types import HeroID, BoardEntityID
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import ResolveCardStep

import goa2.scripts.min_effects  # noqa: F401


@pytest.fixture
def smoke_bomb_state():
    """
    Board layout (straight line):
      (0,0,0) - (1,-1,0) - (2,-2,0) - (3,-3,0)
      plus (0,1,-1) and (1,0,-1) for off-axis options
    """
    board = Board()
    hexes = [
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=-1, s=0),
        Hex(q=2, r=-2, s=0),
        Hex(q=3, r=-3, s=0),
        Hex(q=0, r=1, s=-1),
        Hex(q=1, r=0, s=-1),
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)

    min_hero = Hero(
        id=HeroID("hero_min"),
        name="Min",
        team=TeamColor.RED,
        deck=[],
    )
    enemy = Hero(
        id=HeroID("hero_enemy"),
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[min_hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
        current_actor_id=HeroID("hero_min"),
    )

    # Place heroes
    state.place_entity(BoardEntityID("hero_min"), Hex(q=0, r=0, s=0))
    state.place_entity(BoardEntityID("hero_enemy"), Hex(q=3, r=-3, s=0))

    # Set up token pool (1 smoke bomb)
    token = Token(
        id=BoardEntityID("smoke_bomb_1"),
        name="Smoke Bomb",
        token_type=TokenType.SMOKE_BOMB,
    )
    state.misc_entities[BoardEntityID("smoke_bomb_1")] = token
    state.token_pool[TokenType.SMOKE_BOMB] = [token]

    # Give Min the smoke bomb card
    smoke_card = Card(
        id="smoke_bomb",
        name="Smoke Bomb",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=12,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 1},
        radius_value=3,
        effect_id="smoke_bomb",
        effect_text="Place the Smoke bomb token in radius.",
        is_facedown=False,
    )
    min_hero.hand.append(smoke_card)
    min_hero.current_turn_card = smoke_card

    return state


def test_smoke_bomb_places_token_and_blocks_los(smoke_bomb_state):
    """Full flow: play Smoke Bomb, place token, verify LOS blocking."""
    state = smoke_bomb_state

    # Resolve card → should get action choice
    push_steps(state, [ResolveCardStep(hero_id="hero_min")])
    req = process_resolution_stack(state)
    assert req["type"] == "CHOOSE_ACTION"

    # Select SKILL action
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    req = process_resolution_stack(state)

    # Should now ask for hex selection (place smoke bomb)
    assert req["type"] == "SELECT_HEX"

    # Place at (1,-1,0) — between Min at (0,0,0) and enemy at (3,-3,0)
    state.execution_stack[-1].pending_input = {
        "selection": {"q": 1, "r": -1, "s": 0}
    }
    process_resolution_stack(state)

    # Verify token is placed
    assert state.entity_locations.get(BoardEntityID("smoke_bomb_1")) == Hex(
        q=1, r=-1, s=0
    )

    # Verify LOS_BLOCKER effect was created
    los_effects = [
        e for e in state.active_effects if e.effect_type == EffectType.LOS_BLOCKER
    ]
    assert len(los_effects) == 1
    assert los_effects[0].scope.origin_id == "smoke_bomb_1"
    assert los_effects[0].source_card_id is None  # token-bound, not card-bound

    # Verify targeting is blocked: enemy at (3,-3,0) cannot target Min at (0,0,0)
    # through smoke bomb at (1,-1,0)
    res = state.validator.can_be_targeted(state, "hero_enemy", "hero_min")
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason


def test_smoke_bomb_does_not_block_off_axis(smoke_bomb_state):
    """Smoke bomb only blocks straight-line targeting."""
    state = smoke_bomb_state

    # Manually place token and create effect (skip card flow)
    state.place_entity(BoardEntityID("smoke_bomb_1"), Hex(q=1, r=-1, s=0))

    from goa2.engine.effect_manager import EffectManager
    from goa2.domain.models.effect import DurationType, EffectScope, Shape

    EffectManager.create_effect(
        state,
        source_id="hero_min",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_id="smoke_bomb_1"),
        duration=DurationType.THIS_ROUND,
    )

    # Move enemy off the straight line to (1,0,-1)
    state.place_entity(BoardEntityID("hero_enemy"), Hex(q=1, r=0, s=-1))

    # Enemy at (1,0,-1) targeting Min at (0,0,0) — smoke bomb at (1,-1,0) is NOT between
    res = state.validator.can_be_targeted(state, "hero_enemy", "hero_min")
    assert res.allowed is True


def test_smoke_bomb_removing_token_removes_effect(smoke_bomb_state):
    """Removing the smoke bomb token also removes the LOS_BLOCKER effect."""
    state = smoke_bomb_state

    # Play Smoke Bomb through the full card flow
    push_steps(state, [ResolveCardStep(hero_id="hero_min")])
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {
        "selection": {"q": 1, "r": -1, "s": 0}
    }
    process_resolution_stack(state)

    # Effect exists
    los_effects = [
        e for e in state.active_effects if e.effect_type == EffectType.LOS_BLOCKER
    ]
    assert len(los_effects) == 1

    # Remove the token
    from goa2.engine.steps import _remove_token_from_board

    _remove_token_from_board(state, "smoke_bomb_1")

    # Effect should be gone
    los_effects = [
        e for e in state.active_effects if e.effect_type == EffectType.LOS_BLOCKER
    ]
    assert len(los_effects) == 0

    # Targeting is no longer blocked
    res = state.validator.can_be_targeted(state, "hero_enemy", "hero_min")
    assert res.allowed is True


def test_smoke_bomb_only_empty_hex(smoke_bomb_state):
    """Cannot place smoke bomb on occupied hex."""
    state = smoke_bomb_state

    push_steps(state, [ResolveCardStep(hero_id="hero_min")])
    process_resolution_stack(state)

    # Select SKILL
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    req = process_resolution_stack(state)

    # Check hex options — occupied hexes should be excluded
    assert req["type"] == "SELECT_HEX"
    option_hexes = [Hex(**h) for h in req["valid_hexes"]]

    # Min is at (0,0,0), enemy at (3,-3,0) — both should be excluded
    assert Hex(q=0, r=0, s=0) not in option_hexes
    assert Hex(q=3, r=-3, s=0) not in option_hexes

    # Empty hexes within radius 3 should be available
    assert Hex(q=1, r=-1, s=0) in option_hexes
    assert Hex(q=2, r=-2, s=0) in option_hexes
