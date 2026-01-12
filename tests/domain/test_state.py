import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    CardState,
)
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID
from goa2.domain.input import InputRequestType, InputRequest
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    DurationType,
)
from goa2.engine.validation import ValidationService


@pytest.fixture
def empty_state():
    board = Board()
    board.tiles[Hex(q=0, r=0, s=0)] = board.get_tile(Hex(q=0, r=0, s=0))
    board.tiles[Hex(q=1, r=0, s=-1)] = board.get_tile(Hex(q=1, r=0, s=-1))

    teams = {
        TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
        TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
    }
    return GameState(board=board, teams=teams)


def test_place_entity_updates_cache(empty_state):
    state = empty_state
    hex_loc = Hex(q=0, r=0, s=0)
    uid = "test_unit"

    # Action
    state.place_entity(BoardEntityID(uid), hex_loc)

    # Verify Master Record
    assert state.entity_locations[uid] == hex_loc

    # Verify Cache
    tile = state.board.get_tile(hex_loc)
    assert tile.occupant_id == uid
    assert tile.is_occupied


def test_move_entity_clears_old_cache(empty_state):
    state = empty_state
    start_hex = Hex(q=0, r=0, s=0)
    target_hex = Hex(q=1, r=0, s=-1)
    uid = "test_unit"

    state.place_entity(BoardEntityID(uid), start_hex)
    assert state.board.get_tile(start_hex).occupant_id == uid

    # Move
    state.place_entity(BoardEntityID(uid), target_hex)

    # Verify Old Cleared
    assert state.board.get_tile(start_hex).occupant_id is None
    assert not state.board.get_tile(start_hex).is_occupied

    # Verify New Set
    assert state.entity_locations[uid] == target_hex
    assert state.board.get_tile(target_hex).occupant_id == uid


def test_validator_rebuilds_cache():
    """Verify that loading state from dict/json syncs the board."""
    # Construct raw dict state directly
    # We want to ensure that if 'entity_locations' has data, but 'board.tiles' doesn't have occupancy,
    # the validator fills it in.

    h_dict = {"q": 0, "r": 0, "s": 0}

    state_dict = {
        "board": {
            "zones": {},
            "spawn_points": [],
            "tiles": {
                # Pydantic V2 allows some flexibility in key parsing or we can assume it loads
                # However, usually for JSON keys are strings "0,0,0".
                # Here we are testing python dict input.
                # Let's provide the tile structure expected.
                # Note: Dictionary keys in JSON/Dict for complex types usually require a specific format or serialization.
                # But for this test, we can minimalize the board to just have the tile structure needed.
            },
            "lane": [],
        },
        "teams": {
            "RED": {"color": "RED", "heroes": [], "minions": []},
            "BLUE": {"color": "BLUE", "heroes": [], "minions": []},
        },
        "entity_locations": {"ghost_unit": h_dict},
        "misc_entities": {},
    }

    # We need the Board to actually CONTAIN the tile at (0,0,0) so the validator can find it.
    # But passing keys for Hex in a dict is tricky without the serializer.
    # Instead of creating from dict, let's create the object and THEN modify it to simulate "unsynced" state,
    # then trigger validation? No, validation runs on init.

    # Alternative: Instantiate GameState with valid objects, but verify logic holds.
    # The validator runs `after` model init.

    board = Board()
    h = Hex(q=0, r=0, s=0)
    board.tiles[h] = board.get_tile(h)

    # If we init with entity_locations set, the validator should populate the board tile.
    # The board passed in has NO occupant.

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        entity_locations={"ghost_unit": h},
    )

    # Validator should have run
    tile = state.board.get_tile(h)
    assert tile.occupant_id == "ghost_unit"
    assert tile.is_occupied


def test_misc_entities_storage(empty_state):
    state = empty_state

    # Register a Token (simulated as dict for now since we didn't import Token class)
    token_id = BoardEntityID("trap_1")
    state.misc_entities[token_id] = {"type": "TRAP", "id": token_id}

    loc = Hex(q=0, r=0, s=0)
    state.place_entity(token_id, loc)

    # Lookup via unified method
    retrieved = state.get_entity(token_id)
    assert retrieved is not None
    assert retrieved["type"] == "TRAP"

    assert state.board.get_tile(loc).occupant_id == token_id


def test_awaiting_input_type():
    s = GameState(board=Board(), teams={})
    assert s.awaiting_input_type == InputRequestType.NONE


def test_hero_card_lifecycle():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(
        id="c1",
        name="C1",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e",
        effect_text="t",
    )
    h1.hand.append(c1)

    # Planning
    # ... logic tested in integration tests usually
    assert c1.state == CardState.HAND


def test_retrieve_cards_logic():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(
        id="c1",
        name="C1",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e",
        effect_text="t",
        played_this_round=True,
        state=CardState.DISCARD,
    )
    h1.discard_pile.append(c1)

    h1.retrieve_cards()
    assert c1.state == CardState.HAND
    assert c1 in h1.hand
    assert not c1.played_this_round


def test_awaiting_input_type():
    s = GameState(board=Board(), teams={})
    assert s.awaiting_input_type == InputRequestType.NONE

    s.input_stack.append(
        InputRequest(
            id="req1",
            request_type=InputRequestType.SELECT_UNIT,
            prompt="T",
            player_id="p1",
        )
    )
    assert s.awaiting_input_type == InputRequestType.SELECT_UNIT


def test_hero_card_lifecycle():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(
        id="c1",
        name="C1",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e",
        effect_text="t",
    )
    c2 = Card(
        id="c2",
        name="C2",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="e",
        effect_text="t",
    )

    h1.hand = [c1, c2]

    # 1. Play Card (Planning)
    h1.play_card(c1)

    assert c1 not in h1.hand
    assert c1.state == CardState.UNRESOLVED
    assert c1.is_facedown is True
    assert c1.played_this_round is True

    # 2. Discard (Defense or Cleanup)
    h1.discard_card(c2, from_hand=True)

    assert c2 not in h1.hand
    assert c2 in h1.discard_pile
    assert c2.state == CardState.DISCARD
    assert c2.is_facedown is False
    assert c2.played_this_round is False  # Was discarded directly, not played

    # 3. Discard Already Played Card
    # Simulate resolution -> Discard
    h1.discard_card(c1, from_hand=False)  # Skip hand check
    assert c1 in h1.discard_pile
    assert c1.state == CardState.DISCARD
    assert (
        c1.played_this_round is True
    )  # Retains the flag! This is crucial for "Both Played and Discarded"


def test_retrieve_cards_logic():
    h1 = Hero(id="h1", name="H", team=TeamColor.RED, deck=[])
    c1 = Card(
        id="c1",
        name="C1",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e",
        effect_text="t",
        played_this_round=True,
        state=CardState.DISCARD,
    )
    c2 = Card(
        id="c2",
        name="C2",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="e",
        effect_text="t",
        played_this_round=True,
        state=CardState.RESOLVED,
    )

    h1.discard_pile = [c1]
    h1.played_cards = [c2]
    h1.hand = []

    # Execute Retrieve
    h1.retrieve_cards()

    # Verify Hand
    assert len(h1.hand) == 2
    assert c1 in h1.hand
    assert c2 in h1.hand

    # Verify Piles Cleared
    assert len(h1.discard_pile) == 0
    assert len(h1.played_cards) == 0

    # Verify State Reset
    assert c1.state == CardState.HAND
    assert c1.played_this_round is False
    assert c2.state == CardState.HAND
    assert c2.played_this_round is False


# --- Effect System Integration Tests ---


def test_game_state_has_active_effects(empty_state):
    """GameState has active_effects list."""
    assert hasattr(empty_state, "active_effects")
    assert empty_state.active_effects == []


def test_game_state_add_effect(empty_state):
    """GameState can add effects to active_effects list."""
    effect = ActiveEffect(
        id="eff_1",
        source_id="hero_1",
        effect_type=EffectType.PLACEMENT_PREVENTION,
        scope=EffectScope(shape=Shape.RADIUS, range=3),
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1,
    )

    empty_state.add_effect(effect)

    assert len(empty_state.active_effects) == 1
    assert empty_state.active_effects[0].id == "eff_1"


def test_game_state_validator_property(empty_state):
    """GameState has validator property that returns ValidationService."""
    assert empty_state.validator is not None
    assert isinstance(empty_state.validator, ValidationService)


def test_game_state_validator_is_cached(empty_state):
    """GameState validator is cached (same instance on multiple accesses)."""
    v1 = empty_state.validator
    v2 = empty_state.validator
    assert v1 is v2
