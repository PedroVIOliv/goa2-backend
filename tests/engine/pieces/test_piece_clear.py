"""A multi-piece hero (Razzle) has no owner-level board position, so the CLEAR
action must gate on board presence (any piece), not on the owner's position.
Otherwise CLEAR silently bakes a no-op and no piece can ever clear a token."""

from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, CardColor, CardTier
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.steps.cards import ResolveCardStep
from goa2.engine.steps.selection import MultiSelectStep
from goa2.engine.steps.utility import LogMessageStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _clear_card() -> Card:
    return Card(
        id="test_clear",
        name="Test Clear",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        secondary_actions={ActionType.CLEAR: 0},
        is_ranged=False,
        range_value=1,
        effect_id="test_clear",
        effect_text="",
        is_facedown=False,
    )


def _state():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=_clear_card())
        .blue_hero("hero_knight", at=(4, 0, -4))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))
    return state


def test_clear_builds_real_selection_for_multipiece_hero():
    state = _state()
    state.current_actor_id = "hero_razzle"

    step = ResolveCardStep(hero_id="hero_razzle")
    step.pending_input = {"selection": "CLEAR"}
    result = step.resolve(state, {})

    # A real token selection must be built (the RangeFilter keys off the bound
    # acting piece at execution), not the "not on board" no-op LogMessageStep.
    assert any(isinstance(s, MultiSelectStep) for s in result.new_steps)
    assert not any(
        isinstance(s, LogMessageStep) and "not on board" in s.message for s in result.new_steps
    )
