"""P1: rune_slots field, persistence invariants, view exposure."""

from goa2.domain.models import Hero, RuneType
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from tests.engine.effects.builders import EffectScenarioBuilder

RUNES = {1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN}


def _state() -> GameState:
    return (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_snorri", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(3, 0, -3))
        .with_actor("hero_snorri")
        .build()
    )


def test_rune_slots_default_empty():
    assert Hero(id="hero_x", name="X", deck=[]).rune_slots == {}


def test_rune_slots_survive_retrieve_cards():
    state = _state()
    snorri = state.get_hero("hero_snorri")
    snorri.rune_slots = dict(RUNES)
    snorri.retrieve_cards()  # end-of-round card cleanup
    assert snorri.rune_slots == RUNES


def test_rune_slots_serialization_roundtrip():
    state = _state()
    state.get_hero("hero_snorri").rune_slots = dict(RUNES)
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.get_hero("hero_snorri").rune_slots == RUNES


def test_rune_slots_public_in_opponent_view():
    state = _state()
    state.get_hero("hero_snorri").rune_slots = dict(RUNES)
    view = build_view(state, for_hero_id="hero_knight")
    snorri_view = _find_hero(view, "hero_snorri")
    assert snorri_view["rune_slots"] == {"1": "axe", "2": "bird", "3": "anvil", "4": "horn"}


def _find_hero(view: dict, hero_id: str) -> dict:
    for team in view["teams"].values():
        for hero in team["heroes"]:
            if hero["id"] == hero_id:
                return hero
    raise AssertionError(f"{hero_id} not in view")
