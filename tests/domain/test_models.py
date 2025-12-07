import pytest
from goa2.domain.models import Hero, Card, Team, TeamColor, ActionType, CardColor, CardTier

@pytest.fixture
def basic_card():
    return Card(
        id="c1",
        name="Strike",
        tier=CardTier.UNTIERED, # Updated from I
        color=CardColor.GOLD,
        initiative=5,
        primary_action=ActionType.ATTACK,
        effect_id="strike_effect",
        effect_text="Deal 2 damage"
    )

def test_card_defaults(basic_card):
    # Ensure HOLD action is present and 0
    assert ActionType.HOLD in basic_card.secondary_actions
    assert basic_card.secondary_actions[ActionType.HOLD] == 0

def test_card_secondary_actions_init():
    c = Card(
        id="c2",
        name="Defend",
        tier=CardTier.UNTIERED, # Silver is UNTIERED
        color=CardColor.SILVER,
        initiative=1,
        primary_action=ActionType.DEFENSE,
        effect_id="def",
        effect_text="Block",
        secondary_actions={ActionType.ATTACK: 1} # Explicit setup
    )
    assert c.secondary_actions[ActionType.ATTACK] == 1
    # HOLD should still be added by validator
    assert ActionType.HOLD in c.secondary_actions

def test_card_validation():
    # Valid Cases
    Card(id="c", name="G", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")
    Card(id="c", name="R", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")
    Card(id="c", name="P", tier=CardTier.IV, color=CardColor.PURPLE, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")

    # Invalid Cases
    with pytest.raises(ValueError, match="must be UNTIERED"):
        Card(id="c", name="G", tier=CardTier.I, color=CardColor.GOLD, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")
    
    with pytest.raises(ValueError, match="must be Tier I, II or III"):
        Card(id="c", name="R", tier=CardTier.UNTIERED, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")

    with pytest.raises(ValueError, match="must be Tier IV"):
        Card(id="c", name="P", tier=CardTier.III, color=CardColor.PURPLE, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")

def test_hero_defaults(basic_card):
    h = Hero(
        id="h1",
        name="Knight",
        team=TeamColor.RED,
        deck=[basic_card]
    )
    assert h.level == 1
    assert h.gold == 0
    assert h.deck == [basic_card]
    assert h.team_obj is None

def test_team_hero_link(basic_card):
    h = Hero(id="h1", name="Knight", team=TeamColor.RED, deck=[basic_card])
    t = Team(color=TeamColor.RED, heroes=[h])
    
    # Check aggregation
    assert t.heroes[0] == h
    assert t.life_counters == 5 # Default
    
    # Check circular reference assignment
    h.team_obj = t
    assert h.team_obj is t

def test_hero_serialization_safety(basic_card):
    h = Hero(id="h1", name="Knight", team=TeamColor.RED, deck=[basic_card])
    t = Team(color=TeamColor.RED, heroes=[h])
    h.team_obj = t
    
    # Should not raise recursion error
    json_str = h.model_dump_json()
    assert "team_obj" not in json_str # Excluded field
