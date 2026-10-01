"""Immunity to (basic / non-basic) attacks covers every effect of that attack action.

The attack's basic-ness comes from the performed card, so it is known for the
whole action: unit choices made before the attack step, and area effects the
attack creates, respect Gydion's Shield / Invulnerability too. Allies' attacks
included; skills on basic cards are unaffected.
"""

from __future__ import annotations

import pytest

from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardTier, StatType
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.rules_version import ATTACK_IMMUNITY_COVERS_WHOLE_ACTION, CURRENT_RULES_VERSION
from goa2.domain.types import UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps.effects import CreateEffectStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _shield(state, hero_id: str = "hero_gydion") -> None:
    EffectManager.create_effect(
        state=state,
        source_id=hero_id,
        effect_type=EffectType.ATTACK_IMMUNITY,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_ROUND,
        basic_attacks_only=True,
        is_active=True,
    )


def _invulnerability(state, hero_id: str = "hero_gydion") -> None:
    EffectManager.create_effect(
        state=state,
        source_id=hero_id,
        effect_type=EffectType.ATTACK_IMMUNITY,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_ROUND,
        non_basic_attacks_only=True,
        is_active=True,
    )


def _current_rules(state):
    state.rules_version = CURRENT_RULES_VERSION
    return state


# --- Unit choices made before the attack step -------------------------------


def _onslaught_state():
    """Brogan (RED) adjacent to Gydion and a minion (both BLUE)."""
    return (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (0, 1, -1), (-1, 0, 1)])
        .red_hero("hero_brogan", at=(0, 0, 0), current_card=hero_card("Brogan", "onslaught"))
        .blue_hero("hero_gydion", at=(1, 0, -1))
        .blue_minion("blue_minion", at=(0, 1, -1))
        .with_actor("hero_brogan")
        .build()
    )


def _onslaught_targets(state) -> set:
    run = run_card(state, "hero_brogan")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    return _option_set(run)


@pytest.mark.effect_flow
def test_onslaught_cannot_target_hero_immune_to_basic_attacks() -> None:
    state = _current_rules(_onslaught_state())
    _shield(state)

    targets = _onslaught_targets(state)

    assert "blue_minion" in targets
    assert "hero_gydion" not in targets


@pytest.mark.effect_flow
def test_onslaught_can_target_hero_immune_only_to_non_basic_attacks() -> None:
    state = _current_rules(_onslaught_state())
    _invulnerability(state)

    assert "hero_gydion" in _onslaught_targets(state)


@pytest.mark.effect_flow
def test_games_on_older_rules_keep_their_recorded_targeting() -> None:
    state = _onslaught_state()
    state.rules_version = ATTACK_IMMUNITY_COVERS_WHOLE_ACTION - 1
    _shield(state)

    assert "hero_gydion" in _onslaught_targets(state)


@pytest.mark.effect_flow
def test_noble_blade_cannot_nudge_ally_immune_to_basic_attacks() -> None:
    """Allies' basic attacks are covered too."""
    state = _current_rules(
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, -1, -1), (1, 1, -2), (2, 0, -2), (1, -1, 0)])
        .red_hero("hero_arien", at=(0, 0, 0), current_card=hero_card("Arien", "noble_blade"))
        .blue_minion("enemy_minion", at=(1, 0, -1))
        .red_hero("hero_gydion", at=(2, -1, -1))
        .red_minion("ally_minion", at=(1, 1, -2))
        .with_actor("hero_arien")
        .build()
    )
    _shield(state)

    run = run_card(state, "hero_arien")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("enemy_minion").expect_input(InputRequestType.SELECT_UNIT)

    nudge_options = _option_set(run)
    assert "ally_minion" in nudge_options
    assert "hero_gydion" not in nudge_options


@pytest.mark.effect_flow
def test_basic_skill_can_still_target_hero_immune_to_basic_attacks() -> None:
    state = _current_rules(
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_bain", at=(0, 0, 0), current_card=hero_card("Bain", "get_over_here"))
        .blue_hero("hero_gydion", at=(3, 0, -3))
        .with_actor("hero_bain")
        .build()
    )
    _shield(state)

    run = run_card(state, "hero_bain")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)

    assert "hero_gydion" in _option_set(run)


# --- Area effects created by the attack -------------------------------------


def _bewitch_state():
    """Cordelia (RED) attacks a minion; Gydion and Wasp (BLUE) stand in radius."""
    return _current_rules(
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0)])
        .red_hero("hero_cordelia", at=(0, 0, 0), current_card=hero_card("Cordelia", "bewitch"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .blue_hero("hero_gydion", at=(0, 1, -1))
        .blue_hero("hero_wasp", at=(-1, 1, 0))
        .with_actor("hero_cordelia")
        .build()
    )


def _range(state, hero_id: str) -> int:
    return get_computed_stat(state, UnitID(hero_id), StatType.RANGE, 3)


@pytest.mark.effect_flow
def test_bewitch_range_penalty_skips_hero_immune_to_basic_attacks() -> None:
    state = _bewitch_state()
    _shield(state)

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").finish()

    assert _range(state, "hero_wasp") == 2
    assert _range(state, "hero_gydion") == 3


@pytest.mark.effect_flow
def test_magnetic_dagger_does_not_bind_hero_immune_to_basic_attacks() -> None:
    state = _current_rules(
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0)])
        .red_hero("hero_wasp", at=(0, 0, 0), current_card=hero_card("Wasp", "magnetic_dagger"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .blue_hero("hero_gydion", at=(0, 1, -1))
        .blue_hero("hero_brogan", at=(-1, 1, 0))
        .with_actor("hero_wasp")
        .build()
    )
    _shield(state)

    run = run_card(state, "hero_wasp", finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion")
    run.finish()

    assert not state.validator.can_be_placed(state, "hero_brogan", "hero_gydion").allowed
    assert state.validator.can_be_placed(state, "hero_gydion", "hero_brogan").allowed


def _card(card_id: str, color: CardColor, action: ActionType) -> Card:
    basic = color in (CardColor.GOLD, CardColor.SILVER)
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.UNTIERED if basic else CardTier.I,
        color=color,
        initiative=5,
        primary_action=action,
        primary_action_value=3 if action == ActionType.ATTACK else None,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _range_penalty_from(card: Card, action: ActionType):
    """The actor's card creates a -1 Range area effect during ``action``."""
    state = _current_rules(
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_actor", at=(0, 0, 0), current_card=card)
        .blue_hero("hero_gydion", at=(1, 0, -1))
        .with_actor("hero_actor")
        .build()
    )
    state.execution_context["current_action_type"] = action
    CreateEffectStep(
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS, range=2, origin_id="hero_actor", affects=AffectsFilter.ENEMY_HEROES
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.RANGE,
        stat_value=-1,
        is_active=True,
        use_context_card=False,
    ).resolve(state, state.execution_context)
    return state


def test_basic_skill_area_effect_still_applies_under_shield() -> None:
    state = _range_penalty_from(
        _card("gold_skill", CardColor.GOLD, ActionType.SKILL), ActionType.SKILL
    )
    _shield(state)

    assert _range(state, "hero_gydion") == 2


def test_non_basic_attack_area_effect_respects_invulnerability_not_shield() -> None:
    state = _range_penalty_from(
        _card("red_attack", CardColor.RED, ActionType.ATTACK), ActionType.ATTACK
    )

    _shield(state)
    assert _range(state, "hero_gydion") == 2

    _invulnerability(state)
    assert _range(state, "hero_gydion") == 3
