import pytest

from goa2.domain.hex import Hex
from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.models.spawn import SpawnType
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.engine.starting_positions import (
    apply_position,
    destinations,
    eligible,
    position_view,
    request_swap,
    respond_swap,
)


@pytest.fixture
def state():
    return GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json", ["Min", "Arien"], ["Wasp", "Razzle"], seed=42
    )


def test_move_to_empty_spawn_updates_initial_snapshot(state):
    destination = destinations(state, "hero_min")[0]
    apply_position(state, "hero_min", destination)
    assert state.get_position("hero_min") == destination
    assert state.last_turn_positions == state.entity_locations
    assert state.board.get_tile(destination).occupant_id == "hero_min"


def test_swap_requires_recipient_and_preserves_state_on_rejection(state):
    before = dict(state.entity_locations)
    request = request_swap(state, "hero_min", "hero_arien")
    assert state.entity_locations == before
    with pytest.raises(ValueError):
        respond_swap(state, "hero_wasp", request, True)
    assert state.entity_locations == before
    assert position_view(state, "hero_wasp")["requests"] == []
    assert position_view(state, None) is None
    assert respond_swap(state, "hero_arien", request, True) == "hero_min"
    assert state.get_position("hero_min") == before["hero_arien"]
    assert state.get_position("hero_arien") == before["hero_min"]
    assert not state.starting_position_requests
    assert state.last_turn_positions == state.entity_locations


def test_commit_closes_window_and_invalidates_request_until_uncommit(state):
    request = request_swap(state, "hero_min", "hero_arien")
    session = GameSession(state)
    hero = state.get_hero(HeroID("hero_min"))
    session.commit_card(hero.id, hero.hand[0])
    assert not eligible(state, "hero_min")
    assert position_view(state, "hero_min") is None
    session.uncommit_card(hero.id)
    assert eligible(state, "hero_min")
    assert position_view(state, "hero_min")["destinations"]
    with pytest.raises(ValueError):
        respond_swap(state, "hero_arien", request, True)


def test_requests_survive_save_and_reject_stale_acceptance(state):
    old = request_swap(state, "hero_min", "hero_arien")
    latest = request_swap(state, "hero_min", "hero_arien")
    restored = GameState.model_validate_json(state.model_dump_json())
    with pytest.raises(ValueError):
        respond_swap(restored, "hero_arien", old, True)
    respond_swap(restored, "hero_arien", latest, False)
    assert not restored.starting_position_requests
    apply_position(state, "hero_min", destinations(state, "hero_min")[0])
    with pytest.raises(ValueError):
        respond_swap(state, "hero_arien", latest, True)


def test_razzle_moves_starting_piece_and_swaps(state):
    piece = state.get_piece_ids("hero_razzle")[0]
    destination = destinations(state, "hero_razzle")[0]
    apply_position(state, "hero_razzle", destination)
    assert state.get_position(piece) == destination
    assert "hero_razzle" not in state.entity_locations
    request = request_swap(state, "hero_razzle", "hero_wasp")
    respond_swap(state, "hero_wasp", request, True)
    assert state.get_position("hero_wasp") == destination


@pytest.mark.parametrize(
    "round_num,turn,phase",
    [(1, 2, GamePhase.PLANNING), (2, 1, GamePhase.PLANNING), (1, 1, GamePhase.RESOLUTION)],
)
def test_only_opening_planning(state, round_num, turn, phase):
    destination = destinations(state, "hero_min")[0]
    state.round, state.turn, state.phase = round_num, turn, phase
    with pytest.raises(ValueError):
        apply_position(state, "hero_min", destination)


def test_invalid_destinations_are_atomic(state):
    before = state.model_dump_json()
    for destination in [
        Hex(q=999, r=-999, s=0),
        state.get_position("hero_wasp"),
        state.get_position("hero_arien"),
    ]:
        with pytest.raises(ValueError):
            apply_position(state, "hero_min", destination)
        assert state.model_dump_json() == before
    with pytest.raises(ValueError):
        request_swap(state, "hero_min", "hero_wasp")
    assert state.model_dump_json() == before


def test_full_spawns_require_swap_not_stepping_off_spawn(state):
    # Reduce the spawn supply to the two occupied red spawns, producing a
    # controlled overflow case without depending on a particular large map.
    state.board.spawn_points = [
        sp
        for sp in state.board.spawn_points
        if sp.type != SpawnType.HERO
        or sp.team != TeamColor.RED
        or state.board.get_tile(sp.location).is_occupied
    ]
    assert destinations(state, "hero_min") == []
    spawn = state.get_position("hero_arien")
    adjacent = next(
        h
        for h in spawn.neighbors()
        if h in state.board.tiles
        and not state.board.tiles[h].is_obstacle
        and state.board.tiles[h].zone_id == state.board.tiles[spawn].zone_id
    )
    with pytest.raises(ValueError):
        apply_position(state, "hero_arien", adjacent)
    # Treat Arien's former spawn as an ordinary space to create an overflow
    # hero beside the remaining occupied spawn.
    state.board.spawn_points = [sp for sp in state.board.spawn_points if sp.location != spawn]
    state.place_entity(HeroID("hero_arien"), adjacent)
    legal = destinations(state, "hero_arien")
    assert all(state.board.tiles[h].zone_id == "RedBase" for h in legal)
    request = (
        request_swap(state, "hero_arien", "hero_min")
        if adjacent in state.get_position("hero_min").neighbors()
        else None
    )
    # Independently verify a real legal overflow beside Min's spawn.
    overflow = next(
        h
        for h in state.get_position("hero_min").neighbors()
        if h in state.board.tiles
        and not state.board.tiles[h].is_obstacle
        and state.board.tiles[h].zone_id == "RedBase"
    )
    apply_position(state, "hero_arien", overflow)
    request = request_swap(state, "hero_arien", "hero_min")
    respond_swap(state, "hero_min", request, True)
    assert state.get_position("hero_min") == overflow
    outside = next(
        (
            h
            for h in state.get_position("hero_arien").neighbors()
            if h in state.board.tiles
            and not state.board.tiles[h].is_obstacle
            and state.board.tiles[h].zone_id != "RedBase"
        ),
        None,
    )
    if outside is not None:
        with pytest.raises(ValueError):
            apply_position(state, "hero_min", outside)
