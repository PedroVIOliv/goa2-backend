"""PlaceUnitStep can teleport a token (Wuk Throw cards)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Token, TokenType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID
from goa2.engine.steps.movement import PlaceUnitStep

DEST = Hex(q=3, r=0, s=-3)


def _state_with_tree() -> tuple[GameState, str]:
    board = Board()
    board.zones = {"z": Zone(id="z", hexes={Hex(q=q, r=0, s=-q) for q in range(5)})}
    board.populate_tiles_from_zones()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    tree = Token(id=BoardEntityID("tree_1"), name="Tree", token_type=TokenType.TREE)
    state.register_entity(tree, "token")
    state.place_entity("tree_1", Hex(q=0, r=0, s=0))
    return state, "tree_1"


def test_place_unit_step_moves_token() -> None:
    state, tree_id = _state_with_tree()
    result = PlaceUnitStep(unit_id=tree_id, target_hex_arg=DEST).resolve(state, {})
    assert result.is_finished
    assert state.entity_locations[BoardEntityID(tree_id)] == DEST


def test_place_token_emits_token_event() -> None:
    state, tree_id = _state_with_tree()
    result = PlaceUnitStep(unit_id=tree_id, target_hex_arg=DEST).resolve(state, {})
    event_types = {e.event_type for e in result.events}
    assert GameEventType.TOKEN_MOVED in event_types
    assert GameEventType.UNIT_PLACED not in event_types
