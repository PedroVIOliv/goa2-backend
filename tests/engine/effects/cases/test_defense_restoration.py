"""Defense inputs remain usable after the engine's JSON restoration paths."""

from pathlib import Path

import pytest

import goa2.scripts.xargatha_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType, InputResponse
from goa2.domain.models import ActionType, CardState
from goa2.engine.persistence import load_game, save_game
from goa2.engine.session import GameSession, SessionResult

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _respond(session: GameSession, result: SessionResult, selection: str) -> SessionResult:
    assert result.input_request is not None
    return session.advance(InputResponse(request_id=result.input_request.id, selection=selection))


@pytest.mark.effect_flow
@pytest.mark.parametrize("restoration", ["uninterrupted", "save_load", "rollback"])
def test_cleave_second_defense_survives_restoration(restoration: str, tmp_path: Path) -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_xargatha", at=(0, 0, 0), current_card=hero_card("Xargatha", "cleave"))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .blue_hero("hero_brogan", at=(0, 1, -1))
        .with_actor("hero_xargatha")
        .build()
    )
    shield = hero_card("Brogan", "brogan_shield")
    shield.state = CardState.HAND
    state.get_hero("hero_brogan").hand = [shield]

    # Use the normal card setup, but submit through GameSession: EffectRun.choose
    # bypasses the pending request ID guard that made the production retries fail.
    run_card(state, "hero_xargatha")
    session = GameSession(state)
    result = session.advance()
    result = _respond(session, result, "ATTACK")
    result = _respond(session, result, "hero_arien")
    assert result.input_request.player_id == "hero_arien"
    result = _respond(session, result, "PASS")
    assert result.input_request.request_type == InputRequestType.SELECT_OPTION
    assert result.input_request.can_rollback

    if restoration == "rollback":
        # The first defender's decision closes the old rollback segment. The
        # repeat prompt anchors a new one with ATTACK already in the context.
        result = _respond(session, result, "YES")
        result = session.rollback()
        assert result.input_request.request_type == InputRequestType.SELECT_OPTION
        assert type(session.state.execution_context["current_action_type"]) is str

    result = _respond(session, result, "YES")
    result = _respond(session, result, "hero_brogan")
    request = result.input_request
    assert request.request_type == InputRequestType.SELECT_CARD_OR_PASS
    assert request.player_id == "hero_brogan"
    assert "brogan_shield" in {option.id for option in request.options}
    position = session.state.get_position("hero_brogan")

    if restoration == "save_load":
        path = save_game(
            game_id="defense-restoration",
            state=session.state,
            player_tokens={},
            spectator_token="spectator",
            hero_to_token={},
            created_at=0,
            save_dir=str(tmp_path),
            rollback_snapshot=session._rollback_snapshot,
            rollback_actor_id=session._rollback_actor_id,
        )
        loaded = load_game(str(path))
        session = loaded["session"]
        result = loaded["last_result"]
        assert result.input_request.id == request.id
        assert result.input_request.player_id == request.player_id
        assert type(session.state.execution_context["current_action_type"]) is str

    result = _respond(session, result, "brogan_shield")
    assert result.input_request is None
    assert not session.state.execution_stack
    assert session.state.current_actor_id == "hero_xargatha"
    assert session.state.execution_context["current_action_type"] == ActionType.ATTACK
    assert session.state.execution_context["action_type_stack"] == []
    assert session.state.get_position("hero_brogan") == position
    brogan = session.state.get_hero("hero_brogan")
    assert brogan.hand == []
    assert [card.id for card in brogan.discard_pile] == ["brogan_shield"]
    combats = [
        event for event in result.events if event.event_type == GameEventType.COMBAT_RESOLVED
    ]
    assert len(combats) == 1
    assert combats[0].target_id == "hero_brogan"
    assert combats[0].metadata["outcome"] == "BLOCKED"
    assert combats[0].metadata["attack_value"] == 4
    assert combats[0].metadata["defense_value"] == 4
