"""Result logs preserve game chronology across manual and automatic decisions."""

import json
from unittest.mock import Mock

import pytest

from goa2.domain.board import Board
from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.models import GamePhase
from goa2.domain.state import GameState
from goa2.engine.session import GameSession, SessionResult, SessionResultType
from goa2.server.registry import GameRegistry
from goa2.server.result_logging import log_session_result


@pytest.fixture
def game():
    state = GameState(board=Board(), teams={}, round=3, turn=2)
    game = GameRegistry().create_game(GameSession(state), [])
    game_logger = game.game_logger
    yield game
    game_logger.close()


def test_saved_log_tracks_current_round_and_turn(game):
    request = InputRequest(
        request_type=InputRequestType.SELECT_UNIT,
        player_id="hero_arien",
        prompt="Choose a target",
    )
    event = GameEvent(event_type=GameEventType.GOLD_GAINED, metadata={"amount": 1})
    log_session_result(
        game,
        SessionResult(
            result_type=SessionResultType.INPUT_NEEDED,
            current_phase=GamePhase.RESOLUTION,
            events=[event],
            input_request=request,
        ),
    )
    game.session.state.round = 4
    game.session.state.turn = 1
    log_session_result(
        game,
        SessionResult(
            result_type=SessionResultType.GAME_OVER,
            current_phase=GamePhase.GAME_OVER,
            winner="RED",
        ),
    )

    entries = json.loads(game.game_logger.json_file.read_text())
    assert [entry["type"] for entry in entries] == [
        "PHASE_CHANGE",
        "GAME_EVENT",
        "INPUT_REQUEST",
        "PHASE_CHANGE",
        "GAME_OVER",
    ]
    assert [(entry["round"], entry["turn"], entry["phase"]) for entry in entries] == [
        (3, 2, "RESOLUTION"),
        (3, 2, "RESOLUTION"),
        (3, 2, "RESOLUTION"),
        (4, 1, "GAME_OVER"),
        (4, 1, "GAME_OVER"),
    ]
    assert entries[1]["data"] == event.model_dump(mode="json")
    assert entries[2]["data"]["player_id"] == request.player_id
    assert entries[-1]["data"] == {"winner": "RED"}


@pytest.mark.parametrize(
    "has_logger,has_recorder,winner,should_verify",
    [
        (True, True, "RED", True),
        (True, True, None, False),
        (True, False, "RED", False),
        (False, True, "RED", False),
    ],
)
def test_replay_verification_conditions(
    game, monkeypatch, has_logger, has_recorder, winner, should_verify
):
    verify = Mock()
    monkeypatch.setattr("goa2.server.result_logging.verify_replay_in_background", verify)
    replay_path = str(game.replay_recorder.path)
    if not has_logger:
        game.game_logger = None
    if not has_recorder:
        game.replay_recorder = None

    log_session_result(
        game,
        SessionResult(
            result_type=(
                SessionResultType.GAME_OVER if winner else SessionResultType.ACTION_COMPLETE
            ),
            current_phase=GamePhase.GAME_OVER if winner else GamePhase.RESOLUTION,
            winner=winner,
        ),
    )

    if should_verify:
        verify.assert_called_once_with(replay_path, game.game_id)
    else:
        verify.assert_not_called()
