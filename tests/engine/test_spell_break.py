import pytest
from goa2.domain.models import (
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    EffectType,
)
from goa2.domain.types import HeroID, UnitID
from goa2.domain.state import GameState
from goa2.engine.steps import CreateEffectStep
from goa2.scripts.arien_effects import SpellBreakEffect
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor


@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_red",
    )


def test_spell_break_prevention(empty_state: GameState):
    state = empty_state
    # Setup: Arien (Source) and Enemy Hero (Target)
    arien_id = "hero_arien"
    enemy_id = "hero_enemy"

    # Register Heroes in State/Teams
    arien = Hero(id=HeroID(arien_id), name="Arien", deck=[], team=TeamColor.RED)
    enemy = Hero(id=HeroID(enemy_id), name="Enemy", deck=[], team=TeamColor.BLUE)

    state.teams[TeamColor.RED].heroes.append(arien)
    state.teams[TeamColor.BLUE].heroes.append(enemy)

    # Mock Arien and Enemy
    arien_card = Card(
        id="spell_break_card",
        name="Spell Break",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=13,
        primary_action=ActionType.SKILL,
        effect_id="spell_break",
        effect_text="...",
        radius_value=3,
    )

    # Create the effect manually to simulate playing the card
    # (Or use the Effect class directly)
    effect_def = SpellBreakEffect()
    steps = effect_def.get_steps(state, arien, arien_card)

    # Execute the CreateEffectStep
    assert len(steps) == 1
    create_step = steps[0]
    assert isinstance(create_step, CreateEffectStep)

    # Manually resolve the step to register effect
    state.current_actor_id = arien_id
    create_step.resolve(state, {})

    assert len(state.active_effects) == 1
    effect = state.active_effects[0]
    assert effect.effect_type == EffectType.TARGET_PREVENTION
    assert ActionType.SKILL in effect.restrictions
    assert CardColor.GOLD in effect.except_card_colors

    # Test Validation: Enemy Hero uses SKILL (Blue Card) -> Should be Blocked
    # We need to put Enemy in Range.
    # Let's say Arien is at (0,0,0) and Enemy at (1,-1,0). Range 3 covers it.
    from goa2.domain.hex import Hex

    state.entity_locations[UnitID(arien_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(enemy_id)] = Hex(q=1, r=-1, s=0)

    # Enemy tries to use SKILL with BLUE card
    blue_card = Card(
        id="blue_skill",
        name="Blue Skill",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        effect_id="dummy",
        effect_text="dummy",
        is_facedown=False,
    )

    res = state.validator.can_perform_action(
        state, enemy_id, ActionType.SKILL, context={"card": blue_card}
    )
    assert res.allowed is False
    assert "prevented by effect" in res.reason

    # Enemy tries to use ATTACK (Red Card) -> Should be Allowed
    red_card = Card(
        id="red_attack",
        name="Red Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        effect_id="dummy",
        effect_text="dummy",
        is_facedown=False,
    )
    res = state.validator.can_perform_action(
        state, enemy_id, ActionType.ATTACK, context={"card": red_card}
    )
    assert res.allowed is True

    # Enemy tries to use SKILL with GOLD card -> Should be Allowed (Exception)
    gold_card = Card(
        id="gold_skill",
        name="Gold Skill",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=10,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="dummy",
        effect_text="dummy",
        is_facedown=False,
    )
    res = state.validator.can_perform_action(
        state, enemy_id, ActionType.SKILL, context={"card": gold_card}
    )
    assert res.allowed is True
