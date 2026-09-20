"""Turn-slot bookkeeping and lookups, isolated from phase advancement."""

import pytest

from goa2.domain.models import ActionType, CardState
from goa2.engine.filters import HasPreviousSlotCardFilter, HasResolvedCardFilter, PlayedCardFilter
from goa2.engine.phases import start_revelation_phase
from goa2.engine.steps import DefeatUnitStep, FinalizeHeroTurnStep, PerformCardActionStep
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card


def _state():
    return (
        EffectScenarioBuilder()
        .line_board(5)
        .red_hero("hero_nebkher", at=(0, 0, 0), current_card=hero_card("NebKher", "mind_grip"))
        .blue_hero("hero_brynn", at=(2, 0, -2), current_card=hero_card("Brynn", "familiar_ground"))
        .with_actor("hero_nebkher")
        .build()
    )


@pytest.mark.parametrize("removal", ["retrieve", "discard"])
def test_empty_current_slot_is_completed_once_without_shifting_later_cards(removal):
    state = _state()
    state.turn = 2
    hero = state.get_hero("hero_brynn")
    previous = hero_card("Brynn", "peak_precision")
    previous.state = CardState.RESOLVED
    hero.played_cards = [previous]
    hero.resolved_turn_count = 1
    current = hero.current_turn_card
    if removal == "retrieve":
        hero.return_card_to_hand(current)
    else:
        hero.discard_card(current, from_hand=False)
    finalize = FinalizeHeroTurnStep(hero_id=str(hero.id))
    finalize.resolve(state, state.execution_context)
    finalize.resolve(state, state.execution_context)
    assert hero.played_cards == [previous, None]
    assert hero.resolved_turn_count == 2
    state.turn = 3
    next_card = hero_card("Brynn", "hide_traces")
    hero.current_turn_card = next_card
    finalize.resolve(state, state.execution_context)
    assert hero.played_cards == [previous, None, next_card]
    assert hero.resolved_turn_count == 3


def test_defeat_then_finalization_does_not_complete_two_slots():
    state = _state()
    hero = state.get_hero("hero_brynn")
    current = hero.current_turn_card
    DefeatUnitStep(victim_id=str(hero.id), killer_id="hero_nebkher").resolve(state, {})
    FinalizeHeroTurnStep(hero_id=str(hero.id)).resolve(state, state.execution_context)
    assert hero.played_cards == [current]
    assert hero.resolved_turn_count == 1


def test_passing_reserves_the_empty_turn_slot():
    state = _state()
    hero = state.get_hero("hero_brynn")
    hero.current_turn_card = None
    state.pending_inputs = {
        "hero_brynn": None,
        "hero_nebkher": state.get_hero("hero_nebkher").current_turn_card,
    }
    start_revelation_phase(state)
    assert hero.played_cards == [None]
    assert hero.resolved_turn_count == 1


@pytest.mark.parametrize("performer_count", [0, 1, 2])
@pytest.mark.parametrize("owner_count", [1, 2])
def test_previous_slot_is_relative_to_game_turn_not_either_heroes_progress(
    performer_count, owner_count
):
    state = _state()
    state.turn = 2
    performer = state.get_hero("hero_nebkher")
    owner = state.get_hero("hero_brynn")
    performer.resolved_turn_count = performer_count
    owner.resolved_turn_count = owner_count
    previous = hero_card("Brynn", "peak_precision")
    previous.state = CardState.RESOLVED
    current = owner.current_turn_card
    owner.played_cards = [previous] if owner_count == 1 else [previous, current]
    if owner_count == 2:
        owner.current_turn_card = None
    assert HasPreviousSlotCardFilter().apply(str(owner.id), state, {})
    step = PerformCardActionStep(
        previous_slot=True, hero_id=str(performer.id), card_owner_key="owner"
    )
    result = step.resolve(state, {"owner": str(owner.id)})
    assert result.input_request is not None
    assert previous.name in result.input_request.prompt
    owner.played_cards[0] = None
    assert not HasPreviousSlotCardFilter().apply(str(owner.id), state, {})
    assert step.resolve(state, {"owner": str(owner.id)}).input_request is None


@pytest.mark.parametrize("actor_count", [0, 2])
def test_current_slot_filters_work_when_actor_progress_differs(actor_count):
    state = _state()
    state.turn = 2
    state.get_hero("hero_nebkher").resolved_turn_count = actor_count
    owner = state.get_hero("hero_brynn")
    current = owner.current_turn_card
    owner.current_turn_card = None
    owner.played_cards = [None, current]
    assert HasResolvedCardFilter().apply(str(owner.id), state, {})
    assert PlayedCardFilter(action_type=ActionType.ATTACK, card_color=current.color).apply(
        str(owner.id), state, {}
    )
    owner.played_cards = [current, None]
    assert not HasResolvedCardFilter().apply(str(owner.id), state, {})
    assert not PlayedCardFilter(card_color=current.color).apply(str(owner.id), state, {})
