import pytest
from goa2.domain.models import Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.types import CardID

def test_facedown_masking():
    # 1. Create a card (Defaults to IS_FACEDOWN=True)
    c = Card(
        id=CardID("c1"),
        name="Test",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        effect_id="eff",
        effect_text="Text"
    )
    
    # Verify Default State
    assert c.is_facedown is True
    
    # Verify Masking
    assert c.tier == CardTier.UNTIERED
    assert c.color is None
    assert c.primary_action is None
    assert c.secondary_actions == {}
    assert c.effect_id is None
    assert c.effect_text == ""
    
    # Verify Raw Access via Private/Alias (Implementation Detail Check)
    # We use the raw property names we defined (real_tier, etc)
    # This assumes we implemented it using `real_` prefix in the previous step.
    assert c.real_tier == CardTier.I
    assert c.real_color == CardColor.RED
    
    # 2. Flip to Faceup
    c.is_facedown = False
    
    # Verify Unmasked
    assert c.tier == CardTier.I
    assert c.color == CardColor.RED
    assert c.primary_action == ActionType.ATTACK
    assert c.effect_id == "eff"
