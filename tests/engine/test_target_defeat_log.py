"""The per-turn defeat log and the attack-scoped CheckTargetDefeatedStep."""

import pytest
from pydantic import ValidationError

from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps import CheckTargetDefeatedStep, DefeatUnitStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _duel():
    return (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_red", at=(0, 0, 0))
        .blue_hero("hero_blue", at=(1, 0, -1))
        .red_hero("hero_ally", at=(2, 0, -2))
        .with_actor("hero_red")
        .build()
    )


def _check(state, *, by_actor: bool = False) -> bool:
    push_steps(
        state,
        [CheckTargetDefeatedStep(target_key="my_target", output_key="out", by_actor=by_actor)],
    )
    process_stack(state)
    return state.execution_context["out"]


def test_check_refuses_the_shared_victim_id_key():
    with pytest.raises(ValidationError):
        CheckTargetDefeatedStep(target_key="victim_id", output_key="out")


def test_a_hero_defeat_is_logged_even_when_it_ends_the_game():
    state = _duel()
    state.teams[TeamColor.BLUE].life_counters = 1
    push_steps(state, [DefeatUnitStep(victim_id="hero_blue", killer_id="hero_red")])
    process_stack(state)

    assert state.execution_context["defeat_log"] == [["hero_blue", "hero_red"]]


def test_check_only_counts_defeats_after_the_attack_began():
    state = _duel()
    ctx = state.execution_context
    ctx["my_target"] = "hero_blue"
    ctx["defeat_log"] = [["hero_blue", "hero_red"]]
    ctx["defeat_marks"] = {"my_target": 1}
    assert _check(state) is False

    ctx["defeat_log"].append(["hero_blue", "hero_red"])
    assert _check(state) is True


def test_check_by_actor_ignores_a_defeat_by_someone_else():
    state = _duel()
    ctx = state.execution_context
    ctx["my_target"] = "hero_blue"
    ctx["defeat_marks"] = {"my_target": 0}
    ctx["defeat_log"] = [["hero_blue", "hero_ally"]]

    assert _check(state) is True
    assert _check(state, by_actor=True) is False


def test_check_is_false_when_the_attack_never_marked_its_target():
    state = _duel()
    ctx = state.execution_context
    ctx["my_target"] = "hero_blue"
    ctx["defeat_log"] = [["hero_blue", "hero_red"]]

    assert _check(state) is False


def test_defeating_one_piece_logs_the_owner_and_every_piece():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_knight")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))

    push_steps(
        state, [DefeatUnitStep(victim_id=piece_id("hero_razzle", 2), killer_id="hero_knight")]
    )
    process_stack(state)

    logged = {victim for victim, _ in state.execution_context["defeat_log"]}
    assert logged == {"hero_razzle", piece_id("hero_razzle", 1), piece_id("hero_razzle", 2)}
