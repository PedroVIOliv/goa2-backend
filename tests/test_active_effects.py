from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models.effect import (
    DurationType,
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
)
from goa2.engine.phases import end_turn
from goa2.engine.effect_manager import EffectManager


def test_active_effect_expiry():
    """Test that ActiveEffect with THIS_TURN duration expires at end of turn."""
    state = GameState(board=Board(), teams={})

    # Add an ActiveEffect with THIS_TURN duration
    state.active_effects.append(
        ActiveEffect(
            id="eff_turn",
            source_id="s",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
        )
    )
    # Add an ActiveEffect with THIS_ROUND duration
    state.active_effects.append(
        ActiveEffect(
            id="eff_round",
            source_id="s",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
        )
    )

    assert len(state.active_effects) == 2

    # End Turn
    end_turn(state)
    assert len(state.active_effects) == 1
    assert state.active_effects[0].duration == DurationType.THIS_ROUND

    # End Round (Manually triggering the cleanup logic)
    EffectManager.expire_effects(state, DurationType.THIS_ROUND)
    assert len(state.active_effects) == 0
