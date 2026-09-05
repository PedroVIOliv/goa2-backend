"""Session-result logging shared by REST, WebSocket, and automatic decisions."""

from __future__ import annotations

from goa2.engine.session import SessionResult
from goa2.server.registry import ManagedGame
from goa2.server.replay import verify_replay_in_background


def log_session_result(game: ManagedGame, result: SessionResult) -> None:
    """Log a result at the current round/turn, verifying its replay on game over."""
    game_logger = game.game_logger
    if game_logger is None:
        return

    state = game.session.state
    game_logger.log_phase_change(result.current_phase.value, state.round, state.turn)
    if result.events:
        game_logger.log_events([event.model_dump() for event in result.events])
    if result.input_request:
        game_logger.log_input_request(result.input_request.to_dict())
    if result.winner:
        game_logger.log_game_over(result.winner)
        if game.replay_recorder is not None:
            verify_replay_in_background(str(game.replay_recorder.path), game.game_id)
