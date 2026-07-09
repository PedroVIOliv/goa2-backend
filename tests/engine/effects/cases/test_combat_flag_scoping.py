"""Combat flags set by a defense card are scoped to that one defense.

`auto_block`, `defense_invalid`, `defense_bonus` and `ignore_minion_defense` are
written by the DEFENDER's card (via build_defense_steps) and read by
ResolveCombatStep. A card that attacks more than once reuses one
execution_context for all of its attacks, so a flag left behind by the first
defense must not decide the second one.

Contrast `defense_uses_initiative`, which AttackSequenceStep rewrites on every
attack and therefore cannot go stale.
"""

from __future__ import annotations

import pytest

import goa2.scripts.silverarrow_effects  # registers rain_of_arrows
import goa2.scripts.tigerclaw_effects  # registers dodge
import goa2.scripts.xargatha_effects  # noqa: F401  (registers cleave)
from goa2.domain.models import ActionType, Card, CardColor, CardTier
from goa2.domain.types import BoardEntityID
from goa2.engine.handler import process_stack

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _bulwark() -> Card:
    """A defense card that blocks anything either attacker here can deal."""
    return Card(
        id="bulwark",
        name="Bulwark",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.DEFENSE,
        primary_action_value=20,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _dodge() -> Card:
    card = hero_card("Tigerclaw", "dodge")
    card.is_facedown = False
    return card


def _alive(state, hero_id: str) -> bool:
    return BoardEntityID(hero_id) in state.entity_locations


def _advance(run, state):
    """Drive the stack one step further and re-latch the pending request."""
    result = process_stack(state)
    run.latest_request = result.input_request
    return run


# =============================================================================
# defense_invalid: Cleave (melee, repeats on a different enemy hero)
# =============================================================================


def _cleave_state():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (0, 1, -1), (1, -1, 0), (-1, 1, 0)])
        .red_hero("hero_xargatha", at=(0, 0, 0), current_card=hero_card("Xargatha", "cleave"))
        .blue_hero("hero_tigerclaw", at=(1, 0, -1))
        .blue_hero("hero_victim", at=(0, 1, -1))
        .with_actor("hero_xargatha")
        .build()
    )
    state.get_hero("hero_tigerclaw").hand = [_dodge()]
    state.get_hero("hero_victim").hand = [_bulwark()]
    return state


@pytest.mark.effect_flow
def test_defense_invalid_does_not_leak_into_the_repeat_attack() -> None:
    """Dodge fails against melee, killing its owner. The next hero still blocks.

    Cleave deals 4. The second defender holds Defense 20, so only a stale
    defense_invalid could defeat them.
    """
    state = _cleave_state()

    run = run_card(state, "hero_xargatha")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT").choose("hero_tigerclaw")
    run.expect_input("SELECT_CARD_OR_PASS").choose("dodge")
    _advance(run, state)

    assert not _alive(state, "hero_tigerclaw"), "Dodge must fail against a melee attack"

    run.choose("YES")  # may-repeat prompt
    run.expect_input("SELECT_UNIT").choose("hero_victim")
    run.expect_input("SELECT_CARD_OR_PASS").choose("bulwark")
    run.finish()

    assert _alive(state, "hero_victim")


@pytest.mark.effect_flow
def test_defense_invalid_still_defeats_the_defender_that_played_it() -> None:
    """Control: within its own attack the flag must still do its job."""
    state = _cleave_state()

    run = run_card(state, "hero_xargatha")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT").choose("hero_tigerclaw")
    run.expect_input("SELECT_CARD_OR_PASS").choose("dodge")
    _advance(run, state)

    assert not _alive(state, "hero_tigerclaw")


# =============================================================================
# auto_block: Rain of Arrows (ranged, range 3, repeats on a different hero)
# =============================================================================


def _rain_state():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)] + [(3, -1, -2), (2, 1, -3), (1, 1, -2)])
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", "rain_of_arrows"),
        )
        .blue_hero("hero_tigerclaw", at=(3, 0, -3))
        .blue_hero("hero_victim", at=(3, -1, -2))
        .with_actor("hero_silverarrow")
        .build()
    )
    state.get_hero("hero_tigerclaw").hand = [_dodge()]
    state.get_hero("hero_victim").hand = []  # empty hand -> must PASS
    return state


@pytest.mark.effect_flow
def test_auto_block_does_not_leak_into_the_repeat_attack() -> None:
    """Dodge blocks the ranged attack. The next hero passes and must die.

    Rain of Arrows deals 3. The second defender has no cards, so only a stale
    auto_block could save them.
    """
    state = _rain_state()

    run = run_card(state, "hero_silverarrow")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT").choose("hero_tigerclaw")
    run.expect_input("SELECT_CARD_OR_PASS").choose("dodge")
    _advance(run, state)

    assert _alive(state, "hero_tigerclaw"), "Dodge blocks a ranged attack"

    run.expect_input("SELECT_UNIT").choose("hero_victim")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS")
    run.finish()

    assert not _alive(state, "hero_victim")


@pytest.mark.effect_flow
def test_auto_block_still_saves_the_defender_that_played_it() -> None:
    """Control: within its own attack the flag must still do its job."""
    state = _rain_state()

    run = run_card(state, "hero_silverarrow")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT").choose("hero_tigerclaw")
    run.expect_input("SELECT_CARD_OR_PASS").choose("dodge")
    _advance(run, state)

    assert _alive(state, "hero_tigerclaw")
