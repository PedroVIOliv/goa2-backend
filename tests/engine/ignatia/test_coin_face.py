"""F0a — coin face derivation.

Locked ruling: the Tie Breaker coin face is the SAME bit as
state.tie_breaker_team. Mapping: BLUE team-favored -> blue face,
RED team-favored -> orange face.
"""

from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.domain.state import GameState


def _bare_state(tie_breaker: TeamColor) -> GameState:
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        tie_breaker_team=tie_breaker,
    )


def test_blue_favored_is_blue_face():
    assert _bare_state(TeamColor.BLUE).coin_face == "BLUE"


def test_red_favored_is_orange_face():
    assert _bare_state(TeamColor.RED).coin_face == "ORANGE"
