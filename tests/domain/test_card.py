import pytest
from goa2.domain.models.card import Card
from goa2.domain.models.enums import CardTier, CardColor, ActionType

def test_card_masking():
    c = Card(
        id="c1", 
        name="Test", 
        tier=CardTier.I, 
        color=CardColor.RED, 
        initiative=10, 
        primary_action=ActionType.ATTACK, 
        effect_id="e1", 
        effect_text="text", 
        is_facedown=True
    )
    
    # Check Masked Values
    assert c.current_tier == CardTier.UNTIERED
    assert c.current_color is None
    assert c.current_primary_action is None
    assert c.current_initiative == 0
    
    # Unmask
    c.is_facedown = False
    assert c.current_tier == CardTier.I
    assert c.current_color == CardColor.RED
    assert c.current_primary_action == ActionType.ATTACK
    assert c.current_initiative == 10

def test_tier_color_validation_gold():
    # Valid
    Card(id="g1", name="Gold", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=1, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", is_facedown=False)
    
    # Invalid
    with pytest.raises(ValueError, match="must be UNTIERED"):
        Card(id="g2", name="Gold", tier=CardTier.I, color=CardColor.GOLD, initiative=1, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", is_facedown=False)

def test_tier_color_validation_red():
    # Valid
    Card(id="r1", name="Red", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", is_facedown=False)
    
    # Invalid
    with pytest.raises(ValueError, match="must be Tier I, II or III"):
        Card(id="r2", name="Red", tier=CardTier.UNTIERED, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", is_facedown=False)

def test_tier_color_validation_purple():
    # Valid
    Card(id="p1", name="Ult", tier=CardTier.IV, color=CardColor.PURPLE, initiative=0, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", is_facedown=False)
    
    # Invalid
    with pytest.raises(ValueError, match="must be Tier IV"):
        Card(id="p2", name="Ult", tier=CardTier.III, color=CardColor.PURPLE, initiative=0, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", is_facedown=False)

def test_automatic_secondary_actions():
    # Test ensure_hold_action
    c = Card(id="c1", name="T", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", is_facedown=False)
    assert ActionType.HOLD in c.secondary_actions
    
    # Test ensure_fast_travel (Movement -> Fast Travel)
    c_move = Card(id="m1", name="Move", tier=CardTier.I, color=CardColor.BLUE, initiative=1, primary_action=ActionType.MOVEMENT, effect_id="e", effect_text="t", is_facedown=False)
    assert ActionType.FAST_TRAVEL in c_move.secondary_actions
    
    # Test ensure_clear (Attack -> Clear)
    c_atk = Card(id="a1", name="Atk", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", is_facedown=False)
    assert ActionType.CLEAR in c_atk.secondary_actions

def test_card_range_radius_exclusivity():
    # Valid: Range Only
    Card(id="c1", name="R", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", range_value=2, is_facedown=False)
    
    # Valid: Radius Only
    Card(id="c2", name="R", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", radius_value=1, is_facedown=False)
    
    # Invalid: Both
    with pytest.raises(ValueError, match="Card cannot have both"):
        Card(id="c3", name="R", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t", range_value=2, radius_value=1, is_facedown=False)