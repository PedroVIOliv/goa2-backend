"""How far a mandatory failure unwinds depends on WHOSE action failed.

Rulebook: "If for any reason you cannot complete a mandatory step in the card
text, stop performing the action at that step, and skip any remaining steps."
That is scoped to the card text being followed, so a nested action the acting
hero performs themselves (Ursafar's Angry Roar performing one of his own cards)
takes the whole action down with it. A nested action performed by *another* hero
(Whisper forcing the defender to move on their defense card) cannot: their
inability is not the acting hero failing a step of their own card text, which is
why such clauses read "if able". `RestoreActionContextStep(other_hero_action=True)`
marks that case and stops the unwind.
"""

from goa2.domain.board import Board
from goa2.domain.models import ActionType, TargetType, TeamColor
from goa2.domain.models.team import Team
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import SelectStep, SetContextFlagStep
from goa2.engine.steps.phases import RestoreActionContextStep, push_action_context


def _state() -> GameState:
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )


def _impossible_selection() -> SelectStep:
    """Mandatory unit selection with no units on the board — aborts."""
    return SelectStep(
        target_type=TargetType.UNIT,
        prompt="Impossible selection",
        output_key="never_set",
        is_mandatory=True,
    )


def _nested_action(state: GameState, *, other_hero_action: bool) -> None:
    context = state.execution_context
    context["current_card_id"] = "outer_card"
    context["current_action_type"] = ActionType.ATTACK
    push_action_context(
        context,
        action_type=ActionType.MOVEMENT,
        card_id="inner_card",
        card_owner_id="hero_other",
    )
    push_steps(
        state,
        [
            _impossible_selection(),
            SetContextFlagStep(key="inner_step_ran"),
            RestoreActionContextStep(other_hero_action=other_hero_action),
            SetContextFlagStep(key="outer_step_ran"),
        ],
    )


def test_abort_in_another_heros_nested_action_resumes_the_outer_action() -> None:
    state = _state()
    _nested_action(state, other_hero_action=True)

    process_stack(state)

    context = state.execution_context
    assert "inner_step_ran" not in context
    assert context.get("outer_step_ran") is True
    assert context["current_card_id"] == "outer_card"
    assert context["current_action_type"] == ActionType.ATTACK
    assert "action_context_stack" not in context


def test_abort_in_own_nested_action_stops_the_whole_action() -> None:
    state = _state()
    _nested_action(state, other_hero_action=False)

    process_stack(state)

    context = state.execution_context
    assert "inner_step_ran" not in context
    assert "outer_step_ran" not in context
    assert "action_context_stack" not in context


def test_abort_outside_a_nested_action_still_clears_the_whole_action() -> None:
    state = _state()
    push_steps(
        state,
        [
            _impossible_selection(),
            SetContextFlagStep(key="later_step_ran"),
        ],
    )

    process_stack(state)

    assert "later_step_ran" not in state.execution_context
    assert not state.execution_stack


def test_aborted_nested_defense_restores_outer_copy_policy_before_combat() -> None:
    """Isolate unwinding: an aborted inner action must not replace the attack's policy."""
    from goa2.engine.steps.combat import ResolveCombatStep
    from goa2.engine.steps.utility import SetActorStep

    state = _state()
    context = state.execution_context
    context.update(
        {
            "defense_card_id": "defense",
            "is_primary_defense": True,
            "current_card_id": "outer_copy",
            "token_type_override": "illusion",
            "skip_markers": True,
            "substitution_actor_id": "attacker",
        }
    )
    push_action_context(
        context, action_type=ActionType.SKILL, card_id="inner_copy", card_owner_id="defender"
    )
    context.update(
        {"token_type_override": "tree", "skip_markers": False, "substitution_actor_id": "defender"}
    )
    push_steps(
        state,
        [
            _impossible_selection(),
            RestoreActionContextStep(),
            SetActorStep(actor_key="_pre_defense_actor", save_key="_discard"),
            ResolveCombatStep(damage=3),
        ],
    )
    process_stack(state)
    assert context["current_card_id"] == "outer_copy"
    assert context["token_type_override"] == "illusion"
    assert context["skip_markers"] is True
    assert context["substitution_actor_id"] == "attacker"
    assert "action_context_stack" not in context
