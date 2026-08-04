import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.domain.types import BoardEntityID, HeroID

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


@pytest.mark.effect_flow
def test_mad_dash_may_cross_passable_mine() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_brogan", at=(0, 0, 0), current_card=hero_card("Brogan", "mad_dash"))
        .blue_minion("target", at=(3, 0, -3))
        .blue_hero("mine_owner", at=(5, 0, -5))
        .with_actor("hero_brogan")
        .build()
    )
    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_DUD,
        owner_id=HeroID("mine_owner"),
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_DUD] = [mine]
    state.register_entity(mine, "token")
    state.place_entity(mine.id, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_brogan")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_HEX)

    destinations = {option.metadata["raw"] for option in run.latest_request.options}
    assert Hex(q=2, r=0, s=-2) in destinations
