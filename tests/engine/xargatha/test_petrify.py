"""
Tests for Xargatha's Petrify effect (Stone Gaze, Petrifying Stare, Turn into Statues).

Card text: "Next turn: Enemy heroes in radius count as both heroes and terrain,
and cannot perform movement actions. (If you move, the radius 'moves' with you.)"
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    DurationType,
    EffectScope,
    Shape,
    AffectsFilter,
)
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters import TerrainFilter
from goa2.engine.validation import ValidationService

# Register xargatha effects
import goa2.scripts.xargatha_effects  # noqa: F401


def make_stone_gaze_card():
    return Card(
        id="stone_gaze",
        name="Stone Gaze",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=8,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        is_ranged=False,
        radius_value=2,
        effect_id="stone_gaze",
        effect_text="Next turn: Enemy heroes in radius 2 count as both heroes and terrain, and cannot perform movement actions.",
        is_facedown=False,
    )


def make_petrifying_stare_card():
    return Card(
        id="petrifying_stare",
        name="Petrifying Stare",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=8,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        is_ranged=False,
        radius_value=3,
        effect_id="petrifying_stare",
        effect_text="Next turn: Enemy heroes in radius 3 count as both heroes and terrain, and cannot perform movement actions.",
        is_facedown=False,
    )


def make_turn_into_statues_card():
    return Card(
        id="turn_into_statues",
        name="Turn into Statues",
        tier=CardTier.III,
        color=CardColor.BLUE,
        initiative=8,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        is_ranged=False,
        radius_value=4,
        effect_id="turn_into_statues",
        effect_text="Next turn: Enemy heroes in radius 4 count as both heroes and terrain, and cannot perform movement actions.",
        is_facedown=False,
    )


def _make_petrify_state() -> GameState:
    """
    Board setup:
       - Red hero at (0, 0, 0)
       - Blue hero at (0, 2, -2) - distance 2 from Red (in Stone Gaze radius)
       - Another Red hero at (0, 5, -5) - distance 5 from Red (out of Stone Gaze radius 2)
    """
    board = Board()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)

    xargatha = Hero(id="hero_xargatha", name="Xargatha", team=TeamColor.BLUE, deck=[])
    xargatha.hand.append(make_stone_gaze_card())

    enemy_hero_1 = Hero(
        id="hero_enemy_1", name="Enemy Hero 1", team=TeamColor.RED, deck=[]
    )

    enemy_hero_2 = Hero(
        id="hero_enemy_2", name="Enemy Hero 2", team=TeamColor.RED, deck=[]
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[enemy_hero_1, enemy_hero_2], minions=[]
            ),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[xargatha], minions=[]),
        },
        turn=1,
        round=1,
    )

    state.place_entity("hero_xargatha", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy_1", Hex(q=0, r=2, s=-2))
    state.place_entity("hero_enemy_2", Hex(q=0, r=5, s=-5))

    state.current_actor_id = "hero_xargatha"

    return state


def test_is_terrain_hex_basic():
    """Test that is_terrain_hex correctly identifies static terrain."""
    state = _make_petrify_state()

    # Empty hex on board should not be terrain
    empty_hex = Hex(q=1, r=-1, s=0)
    assert empty_hex in state.board.tiles
    assert not state.validator.is_terrain_hex(state, empty_hex)


def test_is_terrain_hex_with_petrify():
    """Test that is_terrain_hex returns True for petrified enemy hero in scope."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2  # Activate NEXT_TURN effect

    # Enemy hero at distance 2 (in radius) should be terrain
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))


def test_is_terrain_hex_out_of_scope():
    """Test that is_terrain_hex returns False for hero outside radius."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2  # Activate NEXT_TURN effect

    # Enemy hero at distance 5 (out of radius 2) should NOT be terrain
    assert not state.validator.is_terrain_hex(state, Hex(q=0, r=5, s=-5))


def test_terrain_filter_respects_petrify():
    """Test that TerrainFilter correctly identifies petrified hexes as terrain."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2  # Activate NEXT_TURN effect

    filter = TerrainFilter(is_terrain=True)

    # Hex with petrified enemy hero should match terrain filter
    assert filter.apply(Hex(q=0, r=2, s=-2), state, {})

    # Hex with hero outside radius should NOT match
    assert not filter.apply(Hex(q=0, r=5, s=-5), state, {})

    # Empty hex should NOT match
    empty_hex = Hex(q=1, r=-1, s=0)
    assert not filter.apply(empty_hex, state, {})


def test_movement_prevention():
    """Test that petrified hero cannot perform MOVEMENT action."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2  # Activate NEXT_TURN effect

    result = state.validator.can_perform_action(
        state, "hero_enemy_1", ActionType.MOVEMENT
    )
    assert not result.allowed
    assert "action" in result.reason.lower()


def test_fast_travel_prevention():
    """Test that petrified hero cannot perform FAST_TRAVEL action."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2  # Activate NEXT_TURN effect

    result = state.validator.can_perform_action(
        state, "hero_enemy_1", ActionType.FAST_TRAVEL
    )
    assert not result.allowed
    assert "action" in result.reason.lower()


def test_next_turn_timing():
    """Test that effect is not active on creation turn, but active next turn."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)

    # On creation turn (turn=1), effect should NOT be active yet
    assert not state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))

    # Next turn (turn=2, same round), effect should be active
    state.turn = 2
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))


def test_turn_into_statues_integration():
    """Test full Turn into Statues effect via CreateEffectStep."""
    state = _make_petrify_state()
    state.current_actor_id = "hero_xargatha"

    xargatha = state.get_hero("hero_xargatha")
    card = make_turn_into_statues_card()

    from goa2.engine.stats import compute_card_stats

    stats = compute_card_stats(state, xargatha.id, card)
    effect = CardEffectRegistry.get("turn_into_statues")
    steps = effect.build_steps(state, xargatha, card, stats)
    push_steps(state, steps)
    process_resolution_stack(state)

    # Effect should be created but not active yet (NEXT_TURN timing)
    assert len(state.active_effects) == 1
    effect = state.active_effects[0]
    assert effect.effect_type == EffectType.PETRIFY
    assert effect.duration == DurationType.NEXT_TURN

    # Should NOT be terrain yet (same turn)
    assert not state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))

    # Next turn, should be active
    state.turn = 2
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))
    # Enemy at distance 5 is outside radius 4, should NOT be terrain
    assert not state.validator.is_terrain_hex(state, Hex(q=0, r=5, s=-5))


def test_stone_gaze_moves_with_caster():
    """Test that Stone Gaze radius follows Xargatha when she moves."""
    state = _make_petrify_state()

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2

    # Enemy hero at distance 2 should be terrain
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))

    # Move Xargatha closer to enemy_hero_2
    state.entity_locations["hero_xargatha"] = Hex(q=0, r=3, s=-3)

    # Now enemy_hero_2 should be in range (distance 1 from new position)
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=5, s=-5))


def test_friendly_hero_not_petrified():
    """Test that friendly heroes are not affected by PETRIFY."""
    state = _make_petrify_state()

    # Add a friendly hero to Blue team
    friendly_hero = Hero(
        id="hero_friendly",
        name="Friendly Hero",
        team=TeamColor.BLUE,
        deck=[],
    )
    state.teams[TeamColor.BLUE].heroes.append(friendly_hero)
    state.entity_locations["hero_friendly"] = Hex(q=0, r=1, s=-1)

    effect = ActiveEffect(
        id="petrify_1",
        source_id="hero_xargatha",
        effect_type=EffectType.PETRIFY,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_xargatha",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
        duration=DurationType.NEXT_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    state.turn = 2

    # Friendly hero should NOT be terrain
    assert not state.validator.is_terrain_hex(state, Hex(q=0, r=1, s=-1))

    # Enemy hero in range should be terrain
    assert state.validator.is_terrain_hex(state, Hex(q=0, r=2, s=-2))
