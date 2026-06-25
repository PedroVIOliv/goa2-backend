from goa2.domain.models import TeamColor
from goa2.draft.models import (
    DraftActionType,
    DraftPlayer,
    DraftState,
    DraftStatus,
    DraftStep,
)


def test_draft_state_defaults_and_roundtrip():
    state = DraftState(
        draft_id="d1",
        map_name="forgotten_island",
        game_type="LONG",
        draft_mode="sequential_ban_pick",
        red_size=2,
        blue_size=2,
        created_at=1.0,
    )
    assert state.status is DraftStatus.LOBBY
    assert state.players == []
    assert state.bans == {TeamColor.RED: [], TeamColor.BLUE: []}
    assert state.picks == {TeamColor.RED: [], TeamColor.BLUE: []}
    assert state.current_index == 0
    assert state.game_id is None
    dumped = state.model_dump(mode="json")
    assert dumped["bans"] == {"RED": [], "BLUE": []}
    assert dumped["status"] == "LOBBY"


def test_player_and_step():
    p = DraftPlayer(id="p1", display_name="Alice", is_host=True)
    assert p.team is None and p.claimed_hero is None and p.is_captain is False
    s = DraftStep(index=0, action=DraftActionType.BAN, team=TeamColor.RED)
    assert s.action is DraftActionType.BAN
