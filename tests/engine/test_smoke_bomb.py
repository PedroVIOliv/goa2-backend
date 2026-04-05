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
)
from goa2.domain.types import HeroID, UnitID, BoardEntityID
from goa2.domain.hex import Hex
from goa2.engine.effect_manager import EffectManager


@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_attacker",
    )


def test_smoke_bomb_los_blocks_enemy(empty_state: GameState):
    state = empty_state
    attacker_id = "hero_attacker"
    target_id = "hero_target"
    min_id = "hero_min"

    attacker = Hero(
        id=HeroID(attacker_id), name="Attacker", deck=[], team=TeamColor.RED
    )
    target = Hero(id=HeroID(target_id), name="Target", deck=[], team=TeamColor.BLUE)
    min_hero = Hero(id=HeroID(min_id), name="Min", deck=[], team=TeamColor.BLUE)

    state.teams[TeamColor.RED].heroes.append(attacker)
    state.teams[TeamColor.BLUE].heroes.append(target)
    state.teams[TeamColor.BLUE].heroes.append(min_hero)

    state.entity_locations[UnitID(attacker_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(target_id)] = Hex(q=2, r=-2, s=0)

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True

    EffectManager.create_effect(
        state,
        source_id=min_id,
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-1, s=0)),
        duration=DurationType.THIS_TURN,
    )

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason

    state.active_effects.clear()

    EffectManager.create_effect(
        state,
        source_id=min_id,
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-2, s=1)),
        duration=DurationType.THIS_TURN,
    )

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True


def test_smoke_bomb_los_does_not_block_friendly(empty_state: GameState):
    state = empty_state
    enemy_id = "hero_enemy"
    ally_id = "hero_ally"
    target_id = "hero_target"
    min_id = "hero_min"

    enemy = Hero(id=HeroID(enemy_id), name="Enemy", deck=[], team=TeamColor.RED)
    ally = Hero(id=HeroID(ally_id), name="Ally", deck=[], team=TeamColor.BLUE)
    target = Hero(id=HeroID(target_id), name="Target", deck=[], team=TeamColor.BLUE)
    min_hero = Hero(id=HeroID(min_id), name="Min", deck=[], team=TeamColor.BLUE)

    state.teams[TeamColor.RED].heroes.append(enemy)
    state.teams[TeamColor.BLUE].heroes.append(ally)
    state.teams[TeamColor.BLUE].heroes.append(target)
    state.teams[TeamColor.BLUE].heroes.append(min_hero)

    state.entity_locations[UnitID(enemy_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(ally_id)] = Hex(q=-1, r=1, s=0)
    state.entity_locations[UnitID(target_id)] = Hex(q=2, r=-2, s=0)

    EffectManager.create_effect(
        state,
        source_id=min_id,
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-1, s=0)),
        duration=DurationType.THIS_TURN,
    )

    res = state.validator.can_be_targeted(state, ally_id, target_id)
    assert res.allowed is True

    res = state.validator.can_be_targeted(state, enemy_id, target_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason


def test_smoke_bomb_moving(empty_state: GameState):
    """
    Verify that if the token moves (entity location updates),
    the LOS blocking logic updates automatically if using origin_id.
    """
    state = empty_state
    attacker_id = "hero_attacker"
    target_id = "hero_target"
    token_id = "token_smoke_bomb"
    min_id = "hero_min"

    attacker = Hero(
        id=HeroID(attacker_id), name="Attacker", deck=[], team=TeamColor.RED
    )
    target = Hero(id=HeroID(target_id), name="Target", deck=[], team=TeamColor.BLUE)
    min_hero = Hero(id=HeroID(min_id), name="Min", deck=[], team=TeamColor.BLUE)
    state.teams[TeamColor.RED].heroes.append(attacker)
    state.teams[TeamColor.BLUE].heroes.append(target)
    state.teams[TeamColor.BLUE].heroes.append(min_hero)

    state.entity_locations[UnitID(attacker_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(target_id)] = Hex(q=2, r=-2, s=0)

    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-1, s=0)

    EffectManager.create_effect(
        state,
        source_id=min_id,
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(
            shape=Shape.POINT,
            origin_id=token_id,
        ),
        duration=DurationType.THIS_TURN,
    )

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason

    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-2, s=1)

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True

    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-1, s=0)

    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
