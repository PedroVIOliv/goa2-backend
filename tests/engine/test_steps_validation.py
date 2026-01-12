"""Tests for validation integration in Steps."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
)
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import PlaceUnitStep, MoveUnitStep


@pytest.fixture
def game_state_with_heroes():
    """State with two opposing heroes."""
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        turn=1,
        round=1,
    )

    blue_hero = Hero(id="blue_hero", name="Blue", team=TeamColor.BLUE, deck=[])
    red_hero = Hero(id="red_hero", name="Red", team=TeamColor.RED, deck=[])

    state.teams[TeamColor.BLUE].heroes.append(blue_hero)
    state.teams[TeamColor.RED].heroes.append(red_hero)

    # Initialize board with tiles for movement
    for q in range(-3, 4):
        for r in range(-3, 4):
            if abs(q + r) <= 3:
                h = Hex(q=q, r=r, s=-(q + r))
                state.board.tiles[h] = Tile(hex=h)

    return state


def test_place_unit_step_blocked_by_effect(game_state_with_heroes):
    """PlaceUnitStep should be blocked if validation fails."""
    state = game_state_with_heroes

    # Blue hero creates placement prevention effect
    state.active_effects.append(
        ActiveEffect(
            id="eff_1",
            source_id="blue_hero",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=3,
                origin_id="blue_hero",
                affects=AffectsFilter.ENEMY_UNITS,
            ),
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1,
            blocks_enemy_actors=True,
        )
    )

    # Place blue hero
    state.entity_locations["blue_hero"] = Hex(q=0, r=0, s=0)
    # Red hero in radius
    state.entity_locations["red_hero"] = Hex(q=2, r=-1, s=-1)

    # Red hero is current actor
    state.current_actor_id = "red_hero"

    # Try to place self
    step = PlaceUnitStep(
        unit_id="red_hero", target_hex_arg=Hex(q=3, r=-2, s=-1), is_mandatory=True
    )

    result = step.resolve(state, {})

    assert result.abort_action is True
    # Verify unit did NOT move
    assert state.entity_locations["red_hero"] == Hex(q=2, r=-1, s=-1)


def test_place_unit_step_succeeds_when_no_effect(game_state_with_heroes):
    """PlaceUnitStep proceeds if no blocking effect."""
    state = game_state_with_heroes
    state.entity_locations["red_hero"] = Hex(q=0, r=0, s=0)
    state.current_actor_id = "red_hero"

    target = Hex(q=1, r=0, s=-1)

    step = PlaceUnitStep(unit_id="red_hero", target_hex_arg=target)

    result = step.resolve(state, {})

    assert result.is_finished is True
    assert result.abort_action is False
    assert state.entity_locations["red_hero"] == target


def test_move_unit_step_capped_by_zone_effect(game_state_with_heroes):
    """MoveUnitStep blocked if distance exceeds max_value from effect."""
    state = game_state_with_heroes
    state.entity_locations["red_hero"] = Hex(q=0, r=0, s=0)
    state.current_actor_id = "red_hero"

    # Add movement cap effect (max 1)
    state.active_effects.append(
        ActiveEffect(
            id="eff_1",
            source_id="enemy",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.GLOBAL),  # Apply everywhere
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1,
            max_value=1,
        )
    )

    # Try to move 2 spaces
    step = MoveUnitStep(
        unit_id="red_hero",
        destination_key="target",
        range_val=2,
        is_mandatory=True,
        is_movement_action=True,
    )

    # Target is valid path-wise (2 steps away)
    target = Hex(q=2, r=0, s=-2)
    context = {"target": target}

    result = step.resolve(state, context)

    assert result.abort_action is True
    assert state.entity_locations["red_hero"] == Hex(q=0, r=0, s=0)
