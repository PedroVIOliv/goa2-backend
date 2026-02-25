import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    EffectType,
    EffectScope,
    Shape,
    DurationType,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.types import HeroID, UnitID
from goa2.domain.hex import Hex
from goa2.engine.effect_manager import EffectManager
from goa2.engine.steps import SelectStep, AttackSequenceStep
from goa2.scripts.arien_effects import RogueWaveEffect


@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_arien",
    )


def test_arien_rogue_wave_blocked_by_smoke(empty_state: GameState):
    state = empty_state
    arien_id = "hero_arien"
    enemy_id = "hero_enemy"

    # Setup Entities
    arien = Hero(id=HeroID(arien_id), name="Arien", deck=[], team=TeamColor.RED)
    enemy = Hero(id=HeroID(enemy_id), name="Enemy", deck=[], team=TeamColor.BLUE)

    state.teams[TeamColor.RED].heroes.append(arien)
    state.teams[TeamColor.BLUE].heroes.append(enemy)

    # Positions: Distance 2, Straight Line
    # Arien (0,0,0) -> Enemy (2,-2,0)
    state.entity_locations[UnitID(arien_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(enemy_id)] = Hex(q=2, r=-2, s=0)
    state.rebuild_occupancy_cache()

    # Setup Rogue Wave Card (Range 2)
    card = Card(
        id="rogue_wave",
        name="Rogue Wave",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        is_ranged=True,
        range_value=2,
        effect_id="rogue_wave",
        effect_text="...",
        is_facedown=False,
    )

    # 1. Place Smoke Bomb BETWEEN them at (1,-1,0)
    EffectManager.create_effect(
        state,
        source_id="dummy",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-1, s=0)),
        duration=DurationType.THIS_TURN,
    )

    # 2. Get Steps from Card Effect
    effect = RogueWaveEffect()
    steps = effect.get_steps(state, arien, card)

    # 3. Resolve steps to reach SelectTarget
    # RogueWave -> [AttackSequenceStep, SelectStep(push)...]
    # AttackSequenceStep expands -> [SelectStep(target), Reaction, Combat]

    # We resolve the first step manually to expand the macro
    assert isinstance(steps[0], AttackSequenceStep)
    res = steps[0].resolve(state, {})
    assert res.is_finished is True
    expanded_steps = res.new_steps

    # The first step of expanded sequence should be SelectStep for target
    select_step = expanded_steps[0]
    assert isinstance(select_step, SelectStep)
    assert select_step.target_type == "UNIT"

    # 4. Check Filters + Validation

    # We simulate what SelectStep does internally now:
    # 1. Check can_be_targeted (Intrinsic)
    # 2. Check filters

    # Verify Validation Fails (LOS)
    res = state.validator.can_be_targeted(state, arien_id, enemy_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason

    # Verify Filters Pass (Range/Team are fine)
    # Note: LineOfSightFilter is GONE from the step
    for f in select_step.filters:
        assert f.apply(enemy_id, state, {}) is True

    # 5. Move Smoke Bomb Away
    state.active_effects.clear()
    EffectManager.create_effect(
        state,
        source_id="dummy",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-2, s=1)),
        duration=DurationType.THIS_TURN,
    )

    # 6. Verify Target is now valid
    res = state.validator.can_be_targeted(state, arien_id, enemy_id)
    assert res.allowed is True

    for f in select_step.filters:
        assert f.apply(enemy_id, state, {}) is True
