"""Optional attack cancellation must preserve the surrounding action."""

import pytest

from goa2.domain.models import CardState
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import AttackSequenceStep, SetContextFlagStep
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card


@pytest.mark.parametrize("output_key", [None, "custom_target"])
@pytest.mark.parametrize("skip", [False, True])
@pytest.mark.parametrize("round_trip", [False, True])
def test_optional_attack_cancels_all_dependents(output_key, skip, round_trip):
    state = (
        EffectScenarioBuilder()
        .line_board(5)
        .red_hero("actor", at=(0, 0, 0))
        .blue_hero("defender", at=(1, 0, -1) if skip else (4, 0, -4))
        .with_actor("actor")
        .build()
    )
    key = output_key or "victim_id"
    defense = hero_card("Wasp", "reflect_projectiles")
    defense.state = CardState.DISCARD
    state.get_hero("defender").discard_pile = [defense]
    state.execution_context.update(
        {
            key: "defender",
            "defender_id": "defender",
            "defense_card_id": defense.id,
            "is_primary_defense": True,
            "block_succeeded": True,
            "action_type_stack": ["outer"],
        }
    )
    push_steps(
        state,
        [
            AttackSequenceStep(
                damage=4, range_val=1, is_mandatory=False, target_output_key=output_key
            ),
            SetContextFlagStep(key="continued", value=True),
        ],
    )
    if round_trip:
        state = GameState.model_validate_json(state.model_dump_json())
    result = process_stack(state)
    if skip:
        assert result.input_request.request_type.value == "SELECT_UNIT"
        if round_trip:
            state = GameState.model_validate_json(state.model_dump_json())
        state.execution_stack[-1].pending_input = {"selection": "SKIP"}
        result = process_stack(state)
    assert result.input_request is None
    assert result.events == []
    assert key not in state.execution_context
    assert state.execution_context["continued"] is True
    assert state.execution_context["action_type_stack"] == ["outer"]
    assert state.current_actor_id == "actor"


@pytest.mark.parametrize("value", [None, ""])
def test_empty_preselected_target_fizzles(value):
    state = (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("actor", at=(0, 0, 0))
        .with_actor("actor")
        .build()
    )
    state.execution_context["target"] = value
    result = AttackSequenceStep(damage=4, target_id_key="target", is_mandatory=False).resolve(
        state, state.execution_context
    )
    assert result.new_steps == []
    assert not result.abort_action
