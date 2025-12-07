from goa2.domain.models import Card, CardTier, CardColor, ActionType
from goa2.domain.types import CardID

def test_fast_travel_added_to_movement():
    c = Card(
        id=CardID("c1"), name="Dash", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        initiative=5, primary_action=ActionType.MOVEMENT, 
        effect_id="1", effect_text="Move"
    )
    assert ActionType.FAST_TRAVEL in c.secondary_actions
    assert ActionType.HOLD in c.secondary_actions

def test_clear_added_to_attack():
    c = Card(
        id=CardID("c2"), name="Strike", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        initiative=5, primary_action=ActionType.ATTACK, 
        effect_id="2", effect_text="Attack"
    )
    assert ActionType.CLEAR in c.secondary_actions
    assert ActionType.HOLD in c.secondary_actions

def test_no_extra_actions_for_skill():
    c = Card(
        id=CardID("c3"), name="Think", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        initiative=5, primary_action=ActionType.SKILL, 
        effect_id="3", effect_text="Think"
    )
    assert ActionType.FAST_TRAVEL not in c.secondary_actions
    assert ActionType.CLEAR not in c.secondary_actions
    assert ActionType.HOLD in c.secondary_actions
