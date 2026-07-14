"""Garrus effect tests — Battle Fury (ultimate passive).

Battle Fury: "Each time after one of your resolved cards is discarded, you
may perform its primary action."

Performing the discarded card's primary action is an action performed ON that
card, so action-prevention effects (Arien's Spell Break: "Enemy heroes in
radius cannot perform skill actions, except on gold cards") apply to it.
"""

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardContainerType, CardState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import DiscardCardStep

from ..builders import EffectScenarioBuilder, hero_card


def _activate_battle_fury(state, hero_id: str = "hero_garrus") -> None:
    """Configure Garrus so the battle_fury ultimate passive is active."""
    from goa2.data.heroes.registry import HeroRegistry

    garrus = state.get_hero(hero_id)
    assert garrus is not None
    garrus.level = 8
    template = HeroRegistry.get("Garrus")
    assert template is not None and template.ultimate_card is not None
    garrus.ultimate_card = template.ultimate_card


def _apply_spell_break(state, arien_id: str = "hero_arien") -> None:
    """Resolve Arien's Spell Break so its prevention effect is live."""
    from goa2.scripts.arien_effects import SpellBreakEffect

    arien = state.get_hero(arien_id)
    assert arien is not None
    previous_actor = state.current_actor_id
    state.current_actor_id = arien_id
    for step in SpellBreakEffect().get_steps(state, arien, hero_card("Arien", "spell_break")):
        step.resolve(state, {})
    state.current_actor_id = previous_actor


def _state_with_resolved_terrify():
    """Garrus with a resolved Terrify (skill) in his played area, Arien adjacent."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero("hero_garrus", at=(0, 0, 0))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .with_actor("hero_garrus")
        .build()
    )
    garrus = state.get_hero("hero_garrus")
    assert garrus is not None
    terrify = hero_card("Garrus", "terrify")
    terrify.state = CardState.RESOLVED
    garrus.played_cards.append(terrify)
    _activate_battle_fury(state)
    return state


def _discard_terrify_from_played(state):
    push_steps(
        state,
        [
            DiscardCardStep(
                hero_id="hero_garrus",
                card_id="terrify",
                source=CardContainerType.PLAYED,
            )
        ],
    )
    return process_stack(state)


@pytest.mark.effect_flow
def test_battle_fury_performs_discarded_skill_card_primary_action() -> None:
    """Discarding a resolved skill card offers Battle Fury; accepting performs
    the discarded card's primary action (Terrify opens with a unit select)."""
    state = _state_with_resolved_terrify()

    result = _discard_terrify_from_played(state)

    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.CONFIRM_PASSIVE

    state.execution_stack[-1].pending_input = {"selection": "YES"}
    result = process_stack(state)

    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT


@pytest.mark.effect_flow
def test_battle_fury_not_offered_for_skill_card_inside_spell_break() -> None:
    """Inside Spell Break, performing Terrify's primary would be a Skill action
    on a non-gold card — Battle Fury must not be offered at all."""
    state = _state_with_resolved_terrify()
    _apply_spell_break(state)

    result = _discard_terrify_from_played(state)

    # The discard itself still happens...
    garrus = state.get_hero("hero_garrus")
    assert garrus is not None
    assert any(c.id == "terrify" for c in garrus.discard_pile)

    # ...but no Battle Fury offer, and Terrify's primary never runs.
    assert result.input_request is None
    assert state.entity_locations["hero_arien"] == Hex(q=1, r=0, s=-1)
