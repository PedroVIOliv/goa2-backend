from goa2.domain.events import GameEventType
from goa2.domain.models import TOKEN_SUPPLY, TokenType
from goa2.engine.setup import GameSetup
from goa2.engine.steps import EndPhaseCleanupStep


def test_familiar_token_has_one_piece_ordinary_nonpersistent_supply() -> None:
    assert TOKEN_SUPPLY[TokenType.FAMILIAR] == 1

    state = GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json",
        ["Gydion"],
        ["Wasp"],
    )

    familiar_pool = state.token_pool[TokenType.FAMILIAR]
    assert len(familiar_pool) == 1
    familiar = familiar_pool[0]
    assert familiar.is_passable is False
    assert familiar.is_facedown is False
    assert familiar.persists_end_of_round is False
    assert familiar.is_immune_to_enemy_actions is False


def test_familiar_token_is_removed_during_end_phase_cleanup() -> None:
    state = GameSetup.create_game(
        "src/goa2/data/maps/forgotten_island.json",
        ["Gydion"],
        ["Wasp"],
    )
    familiar = state.token_pool[TokenType.FAMILIAR][0]
    destination = next(
        location
        for location, tile in state.board.tiles.items()
        if not tile.is_terrain and not tile.is_occupied
    )
    state.place_entity(str(familiar.id), destination)

    result = EndPhaseCleanupStep().resolve(state, {})

    assert state.get_position(str(familiar.id)) is None
    assert any(
        event.event_type == GameEventType.TOKEN_REMOVED and event.target_id == str(familiar.id)
        for event in result.events
    )
