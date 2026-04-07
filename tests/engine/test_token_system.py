import pytest

from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Token,
    TokenType,
    TOKEN_SUPPLY,
)
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.setup import GameSetup
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import (
    EndPhaseCleanupStep,
    LanePushStep,
    MoveTokenStep,
    PlaceTokenStep,
    PushUnitStep,
    RemoveTokenStep,
    ResolveCardStep,
)


def _make_state() -> GameState:
    board = Board()
    hexes = [
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=-1, s=0),
        Hex(q=2, r=-2, s=0),
        Hex(q=0, r=1, s=-1),
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)

    actor = Hero(id="hero_a", name="Hero A", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[actor], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_a",
    )
    state.place_entity("hero_a", Hex(q=0, r=0, s=0))
    return state


def test_game_setup_initializes_token_pool():
    state = GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json", ["Arien"], ["Wasp"]
    )
    assert set(state.token_pool.keys()) == set(TokenType)
    for token_type, expected_count in TOKEN_SUPPLY.items():
        assert len(state.token_pool[token_type]) == expected_count


def test_place_move_remove_token_lifecycle():
    state = _make_state()
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(token)
    state.token_pool[TokenType.SMOKE_BOMB] = [token]

    context = {"target_hex": Hex(q=1, r=-1, s=0)}
    place_res = PlaceTokenStep(token_type=TokenType.SMOKE_BOMB).resolve(state, context)
    assert state.entity_locations["smoke_bomb_1"] == Hex(q=1, r=-1, s=0)
    assert any(e.event_type == GameEventType.TOKEN_PLACED for e in place_res.events)

    context["token_id"] = "smoke_bomb_1"
    context["dest"] = Hex(q=2, r=-2, s=0)
    move_res = MoveTokenStep(
        token_key="token_id",
        destination_key="dest",
        range_val=2,
    ).resolve(state, context)
    assert state.entity_locations["smoke_bomb_1"] == Hex(q=2, r=-2, s=0)
    assert any(e.event_type == GameEventType.TOKEN_MOVED for e in move_res.events)

    remove_res = RemoveTokenStep(token_id="smoke_bomb_1").resolve(state, context)
    assert "smoke_bomb_1" not in state.entity_locations
    assert "smoke_bomb_1" in state.misc_entities
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in remove_res.events)


def test_remove_token_clears_linked_effects():
    state = _make_state()
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(token)
    state.token_pool[TokenType.SMOKE_BOMB] = [token]
    state.place_entity("smoke_bomb_1", Hex(q=1, r=-1, s=0))

    state.active_effects.append(
        ActiveEffect(
            id="e1",
            source_id="smoke_bomb_1",
            effect_type=EffectType.LOS_BLOCKER,
            scope=EffectScope(shape=Shape.POINT, origin_id="smoke_bomb_1"),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
        )
    )
    assert len(state.active_effects) == 1

    RemoveTokenStep(token_id="smoke_bomb_1").resolve(state, {})
    assert len(state.active_effects) == 0


def test_end_phase_cleanup_clears_all_placed_tokens():
    state = _make_state()
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(token)
    state.token_pool[TokenType.SMOKE_BOMB] = [token]
    state.place_entity("smoke_bomb_1", Hex(q=1, r=-1, s=0))

    res = EndPhaseCleanupStep().resolve(state, {})
    assert "smoke_bomb_1" not in state.entity_locations
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in res.events)


def test_push_token_emits_token_event_and_no_after_push_step():
    state = _make_state()
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(token)
    state.place_entity("smoke_bomb_1", Hex(q=1, r=-1, s=0))

    res = PushUnitStep(
        target_id="smoke_bomb_1",
        source_hex=Hex(q=0, r=0, s=0),
        distance=1,
    ).resolve(state, {})
    assert any(e.event_type == GameEventType.TOKEN_PUSHED for e in res.events)
    assert res.new_steps == []


def test_clear_action_removes_adjacent_tokens():
    state = _make_state()
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(token)
    state.place_entity("smoke_bomb_1", Hex(q=0, r=1, s=-1))

    hero = state.get_hero("hero_a")
    hero.current_turn_card = Card(
        id="c1",
        name="Clear Card",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        secondary_actions={ActionType.CLEAR: 0},
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )

    push_steps(state, [ResolveCardStep(hero_id="hero_a")])
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "CLEAR"}
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "smoke_bomb_1"}
    process_resolution_stack(state)
    assert "smoke_bomb_1" not in state.entity_locations


def test_lane_push_removes_token_blocking_spawn():
    board = Board()
    spawn_hex = Hex(q=1, r=-1, s=0)
    lane_hex = Hex(q=0, r=0, s=0)
    far_hex = Hex(q=2, r=-2, s=0)
    board.tiles[spawn_hex] = Tile(hex=spawn_hex)
    board.tiles[lane_hex] = Tile(hex=lane_hex)
    board.tiles[far_hex] = Tile(hex=far_hex)
    board.zones["z_red_base"] = Zone(id="z_red_base", hexes=set(), neighbors=[])
    board.zones["z_mid"] = Zone(id="z_mid", hexes={lane_hex}, neighbors=[])
    board.zones["z_next"] = Zone(id="z_next", hexes={spawn_hex}, neighbors=[])
    board.zones["z_blue_base"] = Zone(id="z_blue_base", hexes={far_hex}, neighbors=[])
    board.lane = ["z_red_base", "z_mid", "z_next", "z_blue_base"]

    spawn = SpawnPoint(
        location=spawn_hex,
        team=TeamColor.RED,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )
    board.zones["z_next"].spawn_points = [spawn]

    minion = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.RED)
    token = Token(id="smoke_bomb_1", name="Smoke Bomb", token_type=TokenType.SMOKE_BOMB)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[minion]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        active_zone_id="z_mid",
        wave_counter=5,
    )
    state.register_entity(token)
    state.place_entity("smoke_bomb_1", spawn_hex)

    LanePushStep(losing_team=TeamColor.BLUE).resolve(state, {})
    assert "smoke_bomb_1" not in state.entity_locations
    assert "smoke_bomb_1" in state.misc_entities
    assert state.entity_locations.get("m1") == spawn_hex


def test_place_token_overflow_requires_selection():
    state = _make_state()
    t1 = Token(id="smoke_bomb_1", name="Smoke Bomb 1", token_type=TokenType.SMOKE_BOMB)
    t2 = Token(id="smoke_bomb_2", name="Smoke Bomb 2", token_type=TokenType.SMOKE_BOMB)
    state.register_entity(t1)
    state.register_entity(t2)
    state.token_pool[TokenType.SMOKE_BOMB] = [t1, t2]
    state.place_entity("smoke_bomb_1", Hex(q=1, r=-1, s=0))
    state.place_entity("smoke_bomb_2", Hex(q=2, r=-2, s=0))

    res = PlaceTokenStep(
        token_type=TokenType.SMOKE_BOMB,
        hex_key="target_hex",
    ).resolve(state, {"target_hex": Hex(q=0, r=1, s=-1)})

    assert res.is_finished is True
    assert res.requires_input is False
    assert len(res.new_steps) == 3
    assert res.new_steps[0].type.value == "select_step"
