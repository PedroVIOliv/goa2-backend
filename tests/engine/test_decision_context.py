"""Isolated real-step contracts: metadata must describe the offered decision."""

import pytest

from goa2.data.heroes.gydion import create_gydion
from goa2.domain.models import ActionType, RuneType
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps.cards import ForceDiscardStep, ResolveCardStep
from goa2.engine.steps.markers import PlaceRunesStep
from goa2.engine.steps.reactions import ReactionWindowStep
from goa2.engine.steps.selection import ChooseRuneStep
from goa2.engine.steps.spells import CastSpellStep
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card


def _state():
    return (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_arien", at=(0, 0, 0), current_card=hero_card("Arien", "deluge"))
        .blue_hero("hero_wasp", at=(1, 0, -1))
        .with_actor("hero_arien")
        .build()
    )


def test_action_facts_identify_source_and_roles_without_changing_options():
    state = _state()
    push_steps(state, [ResolveCardStep(hero_id="hero_arien")])
    request = process_stack(state).input_request
    assert request is not None
    context = request.to_dict()["decision_context"]
    assert context["source_card_id"] == "deluge"
    assert context["actor_id"] == "hero_arien"
    assert context["purpose"] == "action"
    for option in request.options:
        role = context["choice_facts"][option.id]["action_role"]
        assert option.text.startswith(role.title() + ":")


@pytest.mark.parametrize("initiative", [False, True])
def test_defense_facts_describe_the_stat_actually_computed(initiative):
    state = _state()
    defender = state.get_hero("hero_wasp")
    defender.hand = [hero_card("Arien", "deluge")]
    defender.hand[0].secondary_actions[ActionType.DEFENSE] = 3
    state.execution_context.update(
        target_id="hero_wasp", attack_damage=5, defense_uses_initiative=initiative
    )
    push_steps(state, [ReactionWindowStep()])
    request = process_stack(state).input_request
    assert request is not None
    payload = request.to_dict()
    fact = payload["decision_context"]["choice_facts"]["deluge"]
    assert fact == {
        "defense_stat": "INITIATIVE" if initiative else "DEFENSE",
        "defense_kind": "secondary",
    }
    option = next(o for o in payload["options"] if o["id"] == "deluge")
    assert ("Init:" if initiative else "Def:") in option["text"]
    assert option["defense_value"] == (defender.hand[0].initiative if initiative else 3)
    assert payload["defense_needed"] == payload["attack_value"] - payload["minion_modifier"]


def test_forced_discard_has_explicit_purpose_and_victim_identity():
    state = _state()
    state.get_hero("hero_wasp").hand = [hero_card("Arien", "deluge")]
    state.execution_context["victim"] = "hero_wasp"
    push_steps(state, [ForceDiscardStep(victim_key="victim")])
    request = process_stack(state).input_request
    assert request is not None
    assert request.to_dict()["decision_context"]["purpose"] == "discard"
    assert request.to_dict()["decision_context"]["actor_id"] == "hero_wasp"


def test_rune_requests_keep_sequential_offers_and_identify_purpose():
    for step, purpose in [
        (PlaceRunesStep(hero_id="hero_arien"), "rune_inscription"),
        (
            ChooseRuneStep(
                output_key="rune", options=[RuneType.BIRD, RuneType.AXE], prompt="Translated"
            ),
            "rune_selection",
        ),
    ]:
        state = _state()
        push_steps(state, [step])
        request = process_stack(state).input_request
        assert request is not None
        assert request.to_dict()["decision_context"]["purpose"] == purpose
        assert all(isinstance(option.id, str) for option in request.options)


def test_spell_request_labels_survive_without_requiring_spellbook_visibility():
    # This is the real emitter used when the acting caster is not Gydion.
    spell = create_gydion().spells[0]
    request = CastSpellStep._request("hero_nebkher", [spell]).input_request
    assert request.to_dict()["decision_context"] == {
        "purpose": "cast_spell",
        "actor_id": "hero_nebkher",
        "choice_facts": {},
    }
    assert request.to_dict()["options"] == [{"id": spell.id, "text": spell.name}]


@pytest.mark.parametrize("nested_source", [False, True])
def test_attack_facts_describe_performed_card_and_remain_recipient_scoped(nested_source):
    from goa2.engine.steps.combat import AttackSequenceStep
    from goa2.server.visibility import input_request_for_viewer

    state = _state()
    attacker = state.get_hero("hero_arien")
    attacker.current_turn_card = hero_card("Arien", "noble_blade")
    attacker.current_turn_card.is_facedown = False
    if nested_source:
        attacker.hand = [hero_card("Arien", "deluge")]
        attacker.hand[0].is_facedown = False
        state.execution_context.update(performing_card_id="deluge", performing_card_owner_id=attacker.id)
    state.get_hero("hero_wasp").hand = [hero_card("Arien", "deluge")]
    state.execution_context["target"] = "hero_wasp"
    push_steps(state, [AttackSequenceStep(damage=4, target_id_key="target")])
    request = process_stack(state).input_request
    payload = input_request_for_viewer(request, state, "hero_wasp")
    facts = payload["decision_context"]
    assert facts["source_card_id"] == ("deluge" if nested_source else "noble_blade")
    assert facts["combat"] == {
        "attacker_id": "hero_arien", "is_basic": not nested_source, "is_ranged": False,
        "defense_stat": "DEFENSE", "friendly_minions": {}, "enemy_minions": {},
    }
    assert input_request_for_viewer(request, state, "hero_arien") is None
    assert input_request_for_viewer(request, state, None) is None
