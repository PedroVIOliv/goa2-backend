"""Tests for Min's gold card (Fast as Lightning) when copied via Nebkher's Mind Grip.

The red card lookup is deferred to ``ApplyAfterAttackCardTextStep``, which
resolves **after** the gold attack completes.  The step propagates the red
card's custom ``target_id_key`` (e.g. ``tf_victim``) from
``context["defender_id"]`` so that after-attack steps that gate on that key
can find the attacked unit.
"""

import pytest

import goa2.data.heroes.min
import goa2.data.heroes.nebkher
import goa2.scripts.min_effects
import goa2.scripts.nebkher_effects  # noqa: F401 registers twist_fate, phantasmal_warrior
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, StepType, TokenType
from goa2.domain.models.token import Token
from goa2.domain.types import HeroID
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.stats import compute_card_stats
from goa2.engine.steps import (
    ApplyAfterAttackCardTextStep,
    AttackSequenceStep,
)
from tests.engine.effects.builders import EffectScenarioBuilder, hero_card
from tests.engine.effects.runner import run_card

# ===========================================================================
# Helpers
# ===========================================================================


def _place_token(state, token_id: str, token_type: TokenType, hex_coord: Hex, owner_id: str):
    token = Token(
        id=token_id,
        name=token_type.name.title(),
        token_type=token_type,
        owner_id=HeroID(owner_id),
    )
    state.register_entity(token, "token")
    state.token_pool.setdefault(token_type, []).append(token)
    state.place_entity(token_id, hex_coord)


# ===========================================================================
# Fixture: state with Nebkher as actor, Min as enemy, gold card in Min's slot
# ===========================================================================


@pytest.fixture
def mind_grip_state():
    """Nebkher is about to Mind Grip Min's gold card.

    Min played fast_as_lightning in her previous turn slot.
    Nebkher has a resolved red card (injected per test).
    Both heroes are on the board within range 5.
    """
    gold_card = hero_card("Min", "fast_as_lightning")

    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(6)] + [(q, 1, -q - 1) for q in range(4)])
        .red_hero("hero_min", at=(3, 0, -3))
        .blue_hero("hero_nebkher", at=(0, 0, 0))
        .red_hero("enemy", at=(1, 0, -1))
        .with_actor("hero_nebkher")
        .build()
    )

    # Min has the gold card in her previous turn slot
    gold_card.state = CardState.RESOLVED
    min_hero = state.get_hero(HeroID("hero_min"))
    min_hero.played_cards = [gold_card]

    # Nebkher's resolved_turn_count must be >=1 so PerformCardActionStep
    # resolves prev_index to 0.
    nebkher = state.get_hero(HeroID("hero_nebkher"))
    nebkher.resolved_turn_count = 1

    return state


# ===========================================================================
# Tests: build_steps produces deferred step (effect_contract)
# ===========================================================================


@pytest.mark.effect_contract
class TestBuildStepsStructure:
    """FastAsLightningEffect.build_steps now returns attack + deferred step."""

    def test_always_produces_deferred_step(self, mind_grip_state):
        """build_steps always returns [AttackSequenceStep, ApplyAfterAttackCardTextStep]."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        twist_fate = hero_card("NebKher", "twist_fate")
        twist_fate.state = CardState.RESOLVED
        nebkher.played_cards = [twist_fate]

        gold_card = hero_card("Min", "fast_as_lightning")
        effect = CardEffectRegistry.get("fast_as_lightning")
        stats = compute_card_stats(state, nebkher.id, gold_card)

        steps = effect.build_steps(state, nebkher, gold_card, stats)

        assert len(steps) == 2
        assert isinstance(steps[0], AttackSequenceStep)
        assert steps[0].target_id_key is None  # No longer propagated eagerly
        assert isinstance(steps[1], ApplyAfterAttackCardTextStep)
        assert steps[1].hero_id == "hero_nebkher"

    def test_build_steps_ignores_no_red_card(self, mind_grip_state):
        """Always produces deferred step even when no red card exists yet."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        gold_card = hero_card("Min", "fast_as_lightning")
        effect = CardEffectRegistry.get("fast_as_lightning")
        stats = compute_card_stats(state, nebkher.id, gold_card)

        steps = effect.build_steps(state, nebkher, gold_card, stats)

        assert len(steps) == 2
        assert isinstance(steps[0], AttackSequenceStep)
        assert isinstance(steps[1], ApplyAfterAttackCardTextStep)


# ===========================================================================
# Tests: deferred step resolution (effect_contract)
# ===========================================================================


@pytest.mark.effect_contract
class TestDeferredStepResolution:
    """ApplyAfterAttackCardTextStep.resolve() tests."""

    def test_finds_red_card_and_produces_after_attack_steps(self, mind_grip_state):
        """Resolved Twist Fate card → produces after-attack steps with tf_victim."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        twist_fate = hero_card("NebKher", "twist_fate")
        twist_fate.state = CardState.RESOLVED
        nebkher.played_cards = [twist_fate]
        _place_token(state, "illusion_1", TokenType.ILLUSION, Hex(q=2, r=0, s=-2), "hero_nebkher")

        step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
        ctx = {"defender_id": "enemy"}
        result = step.resolve(state, ctx)

        assert result.is_finished
        assert len(result.new_steps) == 3
        assert getattr(result.new_steps[0], "active_if_key", None) == "tf_victim"
        assert result.new_steps[0].output_key == "tf_swap_enemy"
        assert result.new_steps[1].output_key == "tf_swap_token"
        assert result.new_steps[2].type == StepType.SWAP_UNITS
        # Custom key propagated from defender_id
        assert ctx.get("tf_victim") == "enemy"

    def test_custom_key_propagated_from_defender_id(self, mind_grip_state):
        """Phantasmal Warrior's pw_hero key gets defender_id value."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        p_warrior = hero_card("NebKher", "phantasmal_warrior")
        p_warrior.state = CardState.RESOLVED
        nebkher.played_cards = [p_warrior]

        step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
        ctx = {"defender_id": "enemy"}
        result = step.resolve(state, ctx)

        assert result.is_finished
        assert ctx.get("pw_hero") == "enemy"

    def test_no_red_card_produces_no_steps(self, mind_grip_state):
        """No resolved/discarded red card → resolve returns empty."""
        state = mind_grip_state

        step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0

    def test_red_card_in_hand_not_found(self, mind_grip_state):
        """Red card in hand only → not found (must be in played_cards or discard_pile)."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        twist_fate = hero_card("NebKher", "twist_fate")
        twist_fate.state = CardState.HAND
        nebkher.hand = [twist_fate]

        step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0

    def test_red_card_discarded_during_attack_is_found(self, mind_grip_state):
        """Red card discarded from hand to discard_pile during attack → found by deferred step."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        twist_fate = hero_card("NebKher", "twist_fate")
        twist_fate.state = CardState.DISCARD
        nebkher.discard_pile = [twist_fate]
        _place_token(state, "illusion_1", TokenType.ILLUSION, Hex(q=2, r=0, s=-2), "hero_nebkher")

        step = ApplyAfterAttackCardTextStep(hero_id="hero_nebkher")
        ctx = {"defender_id": "enemy"}
        result = step.resolve(state, ctx)

        assert result.is_finished
        assert len(result.new_steps) == 3
        assert getattr(result.new_steps[0], "active_if_key", None) == "tf_victim"


# ===========================================================================
# Integration: Mind Grip → Fast as Lightning → NebKher red-card follow-up
# ===========================================================================


@pytest.mark.effect_flow
class TestMindGripTwistFateIntegration:
    """Full stack execution for both Tier II NebKher red cards."""

    def test_twist_fate_iib_swaps_after_copied_fast_as_lightning_attack(self, mind_grip_state):
        """Mind Grip → Fast as Lightning → Twist Fate completes the optional swap."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        twist_fate = hero_card("NebKher", "twist_fate")
        twist_fate.state = CardState.RESOLVED
        nebkher.played_cards = [twist_fate]
        _place_token(state, "illusion_1", TokenType.ILLUSION, Hex(q=0, r=1, s=-1), "hero_nebkher")
        nebkher.current_turn_card = hero_card("NebKher", "mind_grip")
        state.get_hero(HeroID("enemy")).hand = [hero_card("NebKher", "twist_fate")]

        run = run_card(state, "hero_nebkher")
        run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
        run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_min")
        run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
        run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
        run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("twist_fate")
        run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
        run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
        run.finish()

        assert state.get_position("enemy") == Hex(q=0, r=1, s=-1)
        assert state.get_position("illusion_1") == Hex(q=1, r=0, s=-1)

    def test_phantasmal_warrior_iia_has_no_after_attack_follow_up(self, mind_grip_state):
        """Mind Grip does not run IIA's before-attack choices after the gold attack."""
        state = mind_grip_state
        nebkher = state.get_hero(HeroID("hero_nebkher"))

        phantasmal_warrior = hero_card("NebKher", "phantasmal_warrior")
        phantasmal_warrior.state = CardState.RESOLVED
        nebkher.played_cards = [phantasmal_warrior]
        _place_token(state, "illusion_1", TokenType.ILLUSION, Hex(q=0, r=1, s=-1), "hero_nebkher")
        nebkher.current_turn_card = hero_card("NebKher", "mind_grip")
        state.get_hero(HeroID("enemy")).hand = [hero_card("NebKher", "twist_fate")]

        run = run_card(state, "hero_nebkher")
        run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
        run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_min")
        run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
        run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
        run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("twist_fate")
        run.finish()

        assert state.get_position("enemy") == Hex(q=1, r=0, s=-1)
        assert state.get_position("illusion_1") == Hex(q=0, r=1, s=-1)
        assert "pw_choice" not in state.execution_context
