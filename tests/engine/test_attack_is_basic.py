"""P4: ``attack_is_basic`` context flag.

Written by ``AttackSequenceStep.resolve`` on every resolve (alongside
``attack_is_ranged``) so Snorri's Oath defense cards (and any other basic-
attack-gated effect) can tell whether the incoming attack's source card is
GOLD/SILVER (basic) or a colored tier (non-basic).
"""

from __future__ import annotations

from goa2.domain.models import ActionType, Card, CardColor, CardTier
from goa2.engine.steps.combat import AttackSequenceStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _attack_card(card_id: str, color: CardColor, *, tier: CardTier = CardTier.UNTIERED) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=tier,
        color=color,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _state_with_card(card: Card):
    return (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_attacker", at=(0, 0, 0), current_card=card)
        .blue_hero("hero_defender", at=(1, 0, -1))
        .with_actor("hero_attacker")
        .build()
    )


def test_attack_is_basic_true_for_silver_card():
    card = _attack_card("silver_attack", CardColor.SILVER)
    state = _state_with_card(card)

    step = AttackSequenceStep(damage=2, range_val=1)
    step.resolve(state, state.execution_context)

    assert state.execution_context["attack_is_basic"] is True


def test_attack_is_basic_true_for_gold_card():
    card = _attack_card("gold_attack", CardColor.GOLD)
    state = _state_with_card(card)

    step = AttackSequenceStep(damage=2, range_val=1)
    step.resolve(state, state.execution_context)

    assert state.execution_context["attack_is_basic"] is True


def test_attack_is_basic_false_for_red_card():
    card = _attack_card("red_attack", CardColor.RED, tier=CardTier.I)
    state = _state_with_card(card)

    step = AttackSequenceStep(damage=2, range_val=1)
    step.resolve(state, state.execution_context)

    assert state.execution_context["attack_is_basic"] is False


def test_attack_is_basic_does_not_leak_between_attacks():
    """Same discipline as attack_is_ranged: written every resolve, not sticky."""
    basic_card = _attack_card("silver_attack", CardColor.SILVER)
    state = _state_with_card(basic_card)

    step = AttackSequenceStep(damage=2, range_val=1)
    step.resolve(state, state.execution_context)
    assert state.execution_context["attack_is_basic"] is True

    # Swap in a colored card and resolve a second attack sequence — the flag
    # must flip, not persist from the previous attack.
    colored_card = _attack_card("red_attack", CardColor.RED, tier=CardTier.I)
    state.get_hero("hero_attacker").current_turn_card = colored_card

    step2 = AttackSequenceStep(damage=2, range_val=1)
    step2.resolve(state, state.execution_context)
    assert state.execution_context["attack_is_basic"] is False
