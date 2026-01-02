from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, StatType
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.engine import stats
from goa2.engine.phases import end_turn, expire_modifiers

def test_computed_stats_with_modifiers():
    # Setup
    hero = Hero(id="hero_1", name="Test Hero", deck=[], hand=[], items={StatType.ATTACK: 1})
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[])}
    )
    
    # Base check (Attack: 0 base + 1 item = 1)
    assert stats.get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=0) == 1
    
    # Add Modifier
    mod = Modifier(
        id="mod_1",
        source_id="test_card",
        target_id="hero_1",
        stat_type=StatType.ATTACK,
        value_mod=2,
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1
    )
    state.add_modifier(mod)
    
    # Check updated stat (1 + 2 = 3)
    assert stats.get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=0) == 3
    
    # Add Negative Modifier
    state.add_modifier(Modifier(
        id="mod_2",
        source_id="debuff",
        target_id="hero_1",
        stat_type=StatType.ATTACK,
        value_mod=-5,
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1
    ))
    
    # Check updated stat (3 - 5 = -2, NO LONGER clamped)
    assert stats.get_computed_stat(state, "hero_1", StatType.ATTACK, base_value=0) == -2

def test_status_tags():
    state = GameState(board=Board(), teams={})
    state.add_modifier(Modifier(
        id="mod_tag",
        source_id="card",
        target_id="unit_1",
        status_tag="IGNORE_OBSTACLES",
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1
    ))
    
    assert stats.has_status(state, "unit_1", "IGNORE_OBSTACLES") is True
    assert stats.has_status(state, "unit_1", "FLYING") is False

def test_modifier_expiry():
    state = GameState(board=Board(), teams={})
    state.add_modifier(Modifier(
        id="mod_turn",
        source_id="s",
        target_id="t",
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1
    ))
    state.add_modifier(Modifier(
        id="mod_round",
        source_id="s",
        target_id="t",
        duration=DurationType.THIS_ROUND,
        created_at_turn=1,
        created_at_round=1
    ))
    
    assert len(state.active_modifiers) == 2
    
    # End Turn
    end_turn(state)
    assert len(state.active_modifiers) == 1
    assert state.active_modifiers[0].duration == DurationType.THIS_ROUND
    
    # End Round (Manually triggering the cleanup logic)
    expire_modifiers(state, DurationType.THIS_ROUND)
    assert len(state.active_modifiers) == 0
