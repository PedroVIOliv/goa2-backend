"""P3: facedown cards outside the hand are hidden information for everyone.

Rulebook: a facedown resolved/discarded card loses its type, color and actions
until it returns to hand. So it renders as an anonymous card back in every view
(the owner's included) and is not selectable as a color/type source.
"""

import pytest

import goa2.data.heroes.nebkher  # registers NebKher in HeroRegistry
import goa2.scripts.nebkher_effects  # noqa: F401  registers twist_fate, phantasmal_warrior
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardContainerType,
    CardState,
    CardTier,
    TargetType,
)
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.steps import (
    ApplyAfterAttackCardTextStep,
    ForceDefenseCardMovementStep,
    MoveSequenceStep,
    SelectStep,
)
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card, skill_card

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


# ---------------------------------------------------------------------------
# Identity filters (color / type / actions) must not see through the mask,
# even when include_facedown re-adds the card as a selectable card back.
# ---------------------------------------------------------------------------


def _state_with_red_discards() -> GameState:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(OWNER, at=(0, 0, 0))
        .with_actor(OWNER)
        .build()
    )
    hero = state.get_hero(OWNER)
    assert hero is not None

    faceup = skill_card("faceup_red", color=CardColor.RED, tier=CardTier.I)
    faceup.state = CardState.DISCARD
    faceup.is_facedown = False

    hidden = skill_card("hidden_red", color=CardColor.RED, tier=CardTier.I)
    hidden.state = CardState.DISCARD
    hidden.is_facedown = True

    hero.deck = [faceup, hidden]
    hero.discard_pile = [faceup, hidden]
    return state


def test_color_filter_never_matches_a_facedown_discarded_card():
    state = _state_with_red_discards()
    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DISCARD,
        card_colors=[CardColor.RED],
        include_facedown=True,
        prompt="Choose a red discarded card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_red"]


def test_action_filter_never_matches_a_facedown_discarded_card():
    state = _state_with_red_discards()
    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DISCARD,
        card_action_types=[ActionType.SKILL],
        include_facedown=True,
        prompt="Choose a discarded skill card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_red"]


def test_tier_filter_never_matches_a_facedown_discarded_card():
    state = _state_with_red_discards()
    state.execution_context["wanted_tier"] = CardTier.I.value
    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DISCARD,
        card_tier_key="wanted_tier",
        include_facedown=True,
        prompt="Choose a tier I discarded card",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["faceup_red"]


def test_deck_searches_still_see_real_card_properties():
    """Deck cards are facedown but the FACEDOWN rule only covers resolved or
    discarded cards — deck fetches (Takahide's gold swaps) need true values."""
    state = _state_with_red_discards()
    hero = state.get_hero(OWNER)
    assert hero is not None

    deck_gold = skill_card("deck_gold", color=CardColor.GOLD, tier=CardTier.UNTIERED)
    deck_gold.state = CardState.DECK
    deck_gold.is_facedown = True
    hero.deck.append(deck_gold)

    step = SelectStep(
        target_type=TargetType.CARD,
        card_container=CardContainerType.DECK,
        card_colors=[CardColor.GOLD],
        card_states=[CardState.DECK],
        prompt="Choose a gold card in your deck",
        output_key="picked",
    )

    assert _offered_card_ids(state, step) == ["deck_gold"]


# ---------------------------------------------------------------------------
# ApplyAfterAttackCardTextStep: a facedown resolved red card has no color, so
# the lookup must skip it and keep searching (here: into the discard pile).
# ---------------------------------------------------------------------------


def test_after_attack_lookup_skips_facedown_red_and_finds_faceup_one():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)])
        .blue_hero("hero_nebkher", at=(0, 0, 0))
        .red_hero("enemy", at=(1, 0, -1))
        .with_actor("hero_nebkher")
        .build()
    )
    nebkher = state.get_hero("hero_nebkher")
    assert nebkher is not None

    hidden_red = hero_card("NebKher", "twist_fate")
    hidden_red.state = CardState.RESOLVED
    hidden_red.is_facedown = True
    nebkher.played_cards = [hidden_red]

    faceup_red = hero_card("NebKher", "phantasmal_warrior")
    faceup_red.state = CardState.DISCARD
    nebkher.discard_pile = [faceup_red]

    step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
    ctx = {"defender_id": "enemy"}
    result = step.resolve(state, ctx)

    assert result.is_finished
    # Phantasmal Warrior's target_id_key was propagated → the faceup discard
    # card was found; the facedown resolved red was skipped, not "found and
    # fizzled".
    assert ctx.get("pw_hero") == "enemy"


# ---------------------------------------------------------------------------
# ForceDefenseCardMovementStep: a facedown discarded defense card has no
# actions, so no movement can be forced from it.
# ---------------------------------------------------------------------------


def _defense_card_with_secondary_movement(facedown: bool) -> Card:
    card = Card(
        id="def_card",
        name="Defense Card",
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.DEFENSE,
        primary_action_value=1,
        secondary_actions={ActionType.MOVEMENT: 2},
        is_ranged=False,
        effect_id="",
        effect_text="",
    )
    card.state = CardState.DISCARD
    card.is_facedown = facedown
    return card


def _forced_movement_result(facedown: bool):
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(OWNER, at=(0, 0, 0))
        .with_actor(OWNER)
        .build()
    )
    hero = state.get_hero(OWNER)
    assert hero is not None
    hero.discard_pile = [_defense_card_with_secondary_movement(facedown)]

    step = ForceDefenseCardMovementStep()
    ctx = {"defense_card_id": "def_card", "victim_id": OWNER}
    return step.resolve(state, ctx)


def test_forced_movement_reads_no_actions_from_a_facedown_defense_card():
    result = _forced_movement_result(facedown=True)

    assert result.is_finished
    assert result.new_steps == []


def test_forced_movement_still_works_for_a_faceup_defense_card():
    result = _forced_movement_result(facedown=False)

    assert result.is_finished
    move_steps = [s for s in result.new_steps if isinstance(s, MoveSequenceStep)]
    assert len(move_steps) == 1
    assert move_steps[0].range_val == 2
