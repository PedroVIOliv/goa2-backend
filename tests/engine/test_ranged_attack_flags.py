"""Regression tests: ranged attacks must set is_ranged=True on their
AttackSequenceStep, otherwise anti-ranged defenses cannot block them (M5)."""

import pytest

import goa2.scripts.dodger_effects
import goa2.scripts.wasp_effects  # noqa: F401 - register effects
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.stats import compute_card_stats
from goa2.engine.steps.combat import AttackSequenceStep


@pytest.fixture
def ranged_state():
    board = Board()
    z = Zone(id="z1", hexes={Hex(q=0, r=0, s=0), Hex(q=2, r=0, s=-2)}, neighbors=[])
    board.zones = {"z1": z}
    board.populate_tiles_from_zones()

    hero = Hero(id="hero", name="Hero", team=TeamColor.RED, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.place_entity("hero", Hex(q=0, r=0, s=0))
    state.current_actor_id = "hero"
    return state


def _make_card(effect_id: str) -> Card:
    return Card(
        id=effect_id,
        name=effect_id,
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        is_ranged=True,
        range_value=3,
        effect_id=effect_id,
        effect_text="t",
        is_facedown=False,
    )


def _collect_attacks(steps) -> list[AttackSequenceStep]:
    """Recurse into nested step templates (e.g. MayRepeatOnceStep)."""
    found: list[AttackSequenceStep] = []
    for step in steps:
        if isinstance(step, AttackSequenceStep):
            found.append(step)
        template = getattr(step, "steps_template", None)
        if template:
            found.extend(_collect_attacks(template))
    return found


@pytest.mark.parametrize(
    "effect_id",
    ["burning_skull", "charged_boomerang", "thunder_boomerang"],
)
def test_ranged_effect_attacks_are_flagged_ranged(ranged_state, effect_id):
    hero = ranged_state.get_hero("hero")
    card = _make_card(effect_id)
    hero.current_turn_card = card

    effect = CardEffectRegistry.get(effect_id)
    stats = compute_card_stats(ranged_state, hero.id, card)
    steps = effect.build_steps(ranged_state, hero, card, stats)

    attacks = _collect_attacks(steps)
    assert attacks, f"{effect_id} produced no AttackSequenceStep"
    for atk in attacks:
        assert atk.is_ranged is True, f"{effect_id} attack must set is_ranged=True"
