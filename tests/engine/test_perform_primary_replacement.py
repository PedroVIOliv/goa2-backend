from __future__ import annotations

import goa2.scripts.ursafar_effects  # noqa: F401
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Hero, TeamColor, TokenType
from goa2.domain.models.effect import EffectType
from goa2.domain.models.token import Token
from goa2.domain.rules_version import CURRENT_RULES_VERSION
from goa2.domain.state import GameState
from goa2.engine.handler import push_steps
from goa2.engine.steps import PerformPrimaryActionStep
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card
from tests.engine.effects.runner import EffectRun

ARENA = [(q, r, -q - r) for q in range(-2, 3) for r in range(-2, 3) if abs(q + r) <= 2]


def _state_with_discarded(card_id: str, *, rules_version: int = CURRENT_RULES_VERSION) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes(ARENA)
        .red_hero("hero_ursafar", at=(0, 0, 0))
        .with_actor("hero_ursafar")
        .build()
    )
    state.rules_version = rules_version
    hero = state.get_hero("hero_ursafar")
    assert hero is not None
    card = hero_card("Ursafar", card_id)
    card.state = CardState.DISCARD
    hero.discard_pile.append(card)
    state.execution_context["perform_card"] = card_id
    return state


def _perform(state: GameState) -> EffectRun:
    push_steps(state, [PerformPrimaryActionStep(card_key="perform_card", hero_id="hero_ursafar")])
    return EffectRun(state=state, hero_id="hero_ursafar")


def _place_token(state: GameState, token_id: str, at: Hex) -> None:
    token = Token(id=token_id, name="Ice", token_type=TokenType.ICE)
    state.register_entity(token)
    state.place_entity(token_id, at)


def _add_enemy(state: GameState, hero_id: str, at: Hex) -> None:
    enemy = Hero(id=hero_id, name=hero_id, team=TeamColor.BLUE, deck=[], level=1)
    state.teams[TeamColor.BLUE].heroes.append(enemy)
    state.place_entity(hero_id, at)


def _option_ids(run: EffectRun) -> list[str]:
    assert run.latest_request is not None
    return [o.id for o in run.latest_request.options]


def _enraged(state: GameState) -> bool:
    return any(e.effect_type == EffectType.ENRAGED for e in state.active_effects)


def test_movement_primary_offers_fast_travel_and_performs_it_instead() -> None:
    state = _state_with_discarded("cold_ire")
    run = _perform(state).expect_input(InputRequestType.CHOOSE_ACTION)
    assert _option_ids(run) == ["MOVEMENT", "FAST_TRAVEL"]

    run.choose("FAST_TRAVEL").expect_input(InputRequestType.SELECT_HEX)
    run.choose(Hex(q=2, r=0, s=-2)).finish()

    assert state.entity_locations["hero_ursafar"] == Hex(q=2, r=0, s=-2)
    assert not _enraged(state)


def test_choosing_the_primary_performs_the_card_effect() -> None:
    state = _state_with_discarded("cold_ire")
    run = _perform(state).expect_input(InputRequestType.CHOOSE_ACTION)

    run.choose("MOVEMENT").expect_input(InputRequestType.SELECT_HEX)
    run.choose(Hex(q=1, r=0, s=-1)).finish()

    assert state.entity_locations["hero_ursafar"] == Hex(q=1, r=0, s=-1)
    assert _enraged(state)


def test_no_choice_when_fast_travel_is_illegal() -> None:
    state = _state_with_discarded("cold_ire")
    _add_enemy(state, "enemy", Hex(q=2, r=-2, s=0))

    _perform(state).expect_input(InputRequestType.SELECT_HEX)


def test_attack_primary_offers_clear_and_clears_instead() -> None:
    state = _state_with_discarded("rip")
    _place_token(state, "ice_1", Hex(q=1, r=0, s=-1))
    run = _perform(state).expect_input(InputRequestType.CHOOSE_ACTION)
    assert _option_ids(run) == ["ATTACK", "CLEAR"]

    run.choose("CLEAR").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("ice_1").finish()

    assert "ice_1" not in state.entity_locations
    assert not _enraged(state)


def test_no_clear_choice_without_an_adjacent_token() -> None:
    state = _state_with_discarded("rip")
    _place_token(state, "ice_1", Hex(q=2, r=0, s=-2))
    _add_enemy(state, "enemy", Hex(q=1, r=0, s=-1))

    _perform(state).expect_input(InputRequestType.SELECT_UNIT)


def test_saves_without_a_rules_version_load_on_the_original_rules() -> None:
    state = _state_with_discarded("cold_ire")
    saved = state.model_dump(mode="json")
    del saved["rules_version"]

    assert GameState.model_validate(saved).rules_version == 0


def test_games_on_older_rules_never_offer_a_replacement() -> None:
    state = _state_with_discarded("cold_ire", rules_version=0)

    _perform(state).expect_input(InputRequestType.SELECT_HEX)
