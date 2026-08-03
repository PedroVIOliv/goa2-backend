import pytest

import goa2.data.heroes.tigerclaw
import goa2.scripts.tigerclaw_effects  # noqa: F401 - register effects
from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.engine.effect_manager import EffectManager

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if getattr(option, "metadata", None) and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        else:
            options.add(option.id)
    return options


def _melee_attack() -> Card:
    return Card(
        id="enemy_attack",
        name="Enemy Attack",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        range_value=1,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _add_self_immunity(state, hero_id: str) -> None:
    EffectManager.create_effect(
        state=state,
        source_id=hero_id,
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(
            shape=Shape.POINT,
            origin_id=hero_id,
            affects=AffectsFilter.SELF,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )


@pytest.mark.effect_flow
@pytest.mark.parametrize("card_id", ["poisoned_dagger", "poisoned_dart"])
def test_poison_can_target_any_hero_except_self(card_id):
    """Poison "a hero in range" — unlike defeat/attack effects, a friendly hero
    (ally) is a legal target (counter-intuitive but per the rules). Tigerclaw
    himself is excluded (default self-exclusion)."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)])
        .red_hero(
            "hero_tigerclaw",
            at=(0, 0, 0),
            current_card=hero_card("Tigerclaw", card_id),
        )
        .red_hero("hero_ally", at=(1, 0, -1))
        .blue_hero("hero_enemy", at=(2, 0, -2))
        .with_actor("hero_tigerclaw")
        .build()
    )

    run = run_card(state, "hero_tigerclaw")
    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_UNIT")

    options = _option_set(run)
    assert "hero_ally" in options  # friendly hero IS a legal poison target
    assert "hero_enemy" in options  # enemy hero still a legal target
    assert "hero_tigerclaw" not in options  # self excluded by default


@pytest.mark.effect_flow
@pytest.mark.parametrize("defense_id", ["parry", "riposte"])
def test_counterattack_defenses_do_not_affect_immune_attacker(defense_id: str) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero("hero_tigerclaw", at=(1, 0, -1))
        .blue_hero("hero_attacker", at=(0, 0, 0), current_card=_melee_attack())
        .with_actor("hero_attacker")
        .build()
    )
    defense = hero_card("Tigerclaw", defense_id)
    defense.state = CardState.HAND
    tigerclaw = state.get_hero("hero_tigerclaw")
    tigerclaw.hand = [defense]

    attacker = state.get_hero("hero_attacker")
    if defense_id == "parry":
        spare = hero_card("Tigerclaw", "dodge")
        spare.state = CardState.HAND
        attacker.hand = [spare]
    _add_self_immunity(state, "hero_attacker")

    run = run_card(state, "hero_attacker")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK")
    run.expect_input("SELECT_UNIT").choose("hero_tigerclaw")
    run.expect_input("SELECT_CARD_OR_PASS").choose(defense_id)
    run.finish()

    assert state.get_position("hero_attacker") is not None
    if defense_id == "parry":
        assert [card.id for card in attacker.hand] == ["dodge"]
