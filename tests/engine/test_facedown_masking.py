"""P3: facedown cards outside the hand are hidden information for everyone.

Rulebook: a facedown resolved/discarded card loses its type, color and actions
until it returns to hand. So it renders as an anonymous card back in every view
(the owner's included) and is not selectable as a color/type source.
"""

import pytest

from goa2.domain.models import CardContainerType, CardState, TargetType
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.steps import SelectStep
from tests.engine.effects.builders import EffectScenarioBuilder, skill_card

OWNER = "hero_owner"
OTHER = "hero_other"


def _state_with_discards() -> GameState:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(OWNER, at=(0, 0, 0))
        .blue_hero(OTHER, at=(3, 0, -3))
        .with_actor(OWNER)
        .build()
    )
    hero = state.get_hero(OWNER)
    assert hero is not None

    faceup = skill_card("faceup_card")
    faceup.state = CardState.DISCARD
    faceup.is_facedown = False

    hidden = skill_card("hidden_card")
    hidden.state = CardState.DISCARD
    hidden.is_facedown = True

    hero.deck = [faceup, hidden]
    hero.discard_pile = [faceup, hidden]
    return state


def _discard_view(state: GameState, viewer):
    view = build_view(state, for_hero_id=viewer)
    heroes = view["teams"]["RED"]["heroes"]
    return next(h for h in heroes if h["id"] == OWNER)["discard_pile"]


@pytest.mark.parametrize("viewer", [OWNER, OTHER, None])
def test_facedown_discard_card_is_masked_for_every_viewer(viewer):
    state = _state_with_discards()

    cards = _discard_view(state, viewer)
    hidden = cards[1]

    assert hidden["is_facedown"] is True
    assert "id" not in hidden
    assert "name" not in hidden
    assert hidden["color"] is None
    assert hidden["primary_action"] is None
    assert hidden["effect_id"] is None


@pytest.mark.parametrize("viewer", [OWNER, OTHER, None])
def test_faceup_discard_card_still_renders_fully(viewer):
    state = _state_with_discards()

    faceup = _discard_view(state, viewer)[0]

    assert faceup["id"] == "faceup_card"
    assert faceup["is_facedown"] is False


def test_facedown_resolved_card_is_masked_for_the_owner():
    state = _state_with_discards()
    hero = state.get_hero(OWNER)
    assert hero is not None
    hidden = hero.discard_pile.pop()
    hidden.state = CardState.RESOLVED
    hero.played_cards = [hidden]

    view = build_view(state, for_hero_id=OWNER)
    played = next(h for h in view["teams"]["RED"]["heroes"] if h["id"] == OWNER)["played_cards"]

    assert played[0]["is_facedown"] is True
    assert "id" not in played[0]


def _offered_card_ids(state: GameState, step: SelectStep) -> list[str]:
    result = step.resolve(state, state.execution_context)
    assert result.requires_input and result.input_request is not None
    return [opt.id for opt in result.input_request.options]


def test_card_select_over_discard_skips_facedown_cards():
    state = _state_with_discards()
    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DISCARD,
        prompt="Choose a discarded card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_card"]


def test_card_select_with_include_facedown_offers_both():
    state = _state_with_discards()
    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DISCARD,
        prompt="Retrieve a discarded card",
        output_key="picked",
        include_facedown=True,
    )

    assert _offered_card_ids(state, step) == ["faceup_card", "hidden_card"]


def test_card_select_over_played_skips_facedown_cards():
    state = _state_with_discards()
    hero = state.get_hero(OWNER)
    assert hero is not None
    for card in hero.discard_pile:
        card.state = CardState.RESOLVED
    hero.played_cards = list(hero.discard_pile)
    hero.discard_pile = []

    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.PLAYED,
        prompt="Choose a resolved card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_card"]


def test_hand_selection_is_unaffected_by_the_facedown_flag():
    """Hand cards are private, not 'facedown' in the rulebook sense."""
    state = _state_with_discards()
    hero = state.get_hero(OWNER)
    assert hero is not None
    for card in hero.discard_pile:
        card.state = CardState.HAND
    hero.hand = list(hero.discard_pile)
    hero.discard_pile = []

    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.HAND,
        prompt="Choose a card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_card", "hidden_card"]
