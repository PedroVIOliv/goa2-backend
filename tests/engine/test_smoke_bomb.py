import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    EffectType,
    EffectScope,
    Shape,
    DurationType,
)
from goa2.domain.types import HeroID, UnitID
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


def test_smoke_bomb_los(empty_state: GameState):
    state = empty_state
    attacker_id = "hero_attacker"
    target_id = "hero_target"

    # Setup Entities
    attacker = Hero(
        id=HeroID(attacker_id), name="Attacker", deck=[], team=TeamColor.RED
    )
    target = Hero(id=HeroID(target_id), name="Target", deck=[], team=TeamColor.BLUE)

    state.teams[TeamColor.RED].heroes.append(attacker)
    state.teams[TeamColor.BLUE].heroes.append(target)

    # 1. Position: Distance 2, Straight Line
    # Attacker at (0,0,0) -> Target at (2,-2,0)
    # Midpoint is (1,-1,0)
    state.entity_locations[UnitID(attacker_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(target_id)] = Hex(q=2, r=-2, s=0)

    # Verify LOS is clear initially
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True

    # 2. Place Smoke Bomb at (1,-1,0) - DIRECTLY BETWEEN
    EffectManager.create_effect(
        state,
        source_id="dummy",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-1, s=0)),
        duration=DurationType.THIS_TURN,
    )

    # Verify LOS is blocked
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason

    # 4. Move Smoke Bomb to (1, -2, 1) - OFF LINE
    # Clear effects
    state.active_effects.clear()

    EffectManager.create_effect(
        state,
        source_id="dummy",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-2, s=1)),
        duration=DurationType.THIS_TURN,
    )

    # Verify LOS is clear
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True


def test_smoke_bomb_moving(empty_state: GameState):
    """
    Verify that if the token moves (entity location updates),
    the LOS blocking logic updates automatically if using origin_id.
    """
    state = empty_state
    attacker_id = "hero_attacker"
    target_id = "hero_target"
    token_id = "token_smoke_bomb"

    # Setup Entities
    attacker = Hero(
        id=HeroID(attacker_id), name="Attacker", deck=[], team=TeamColor.RED
    )
    target = Hero(id=HeroID(target_id), name="Target", deck=[], team=TeamColor.BLUE)
    state.teams[TeamColor.RED].heroes.append(attacker)
    state.teams[TeamColor.BLUE].heroes.append(target)

    # 1. Position Entities: Straight Line, Distance 2
    # Attacker (0,0,0) -> Target (2,-2,0)
    state.entity_locations[UnitID(attacker_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(target_id)] = Hex(q=2, r=-2, s=0)

    # 2. Register Token Location at Midpoint (1,-1,0)
    # Ideally use PlaceTokenStep/Token model, but manual registry works for engine test
    from goa2.domain.types import BoardEntityID

    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-1, s=0)

    # 3. Create Effect linked to Token ID (Dynamic Origin)
    EffectManager.create_effect(
        state,
        source_id="dummy",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(
            shape=Shape.POINT,
            origin_id=token_id,  # Linking to ID, not Hex
        ),
        duration=DurationType.THIS_TURN,
    )

    # 4. Verify LOS Blocked (Token is between)
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
    assert "Line of sight blocked" in res.reason

    # 5. Move Token Away (1, -2, 1)
    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-2, s=1)

    # 6. Verify LOS Clear (Token moved)
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is True

    # 7. Move Token Back (1, -1, 0)
    state.entity_locations[BoardEntityID(token_id)] = Hex(q=1, r=-1, s=0)

    # 8. Verify LOS Blocked Again
    res = state.validator.can_be_targeted(state, attacker_id, target_id)
    assert res.allowed is False
