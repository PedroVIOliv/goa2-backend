from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID, CardID
from .registry import HeroRegistry

def create_rogue() -> Hero:
    """
    Rogue: Fast Assassin. 
    Standardized Test Loadout: 5 Cards.
    """
    name = "Rogue"
    title = "Shadow Walker"
    
    # Shared Stats for Secondaries
    standard_secondaries = {
        ActionType.DEFENSE: 2,
        ActionType.ATTACK: 2,
        ActionType.MOVEMENT: 2
    }
    
    deck = [
        # 1. Gold (Untiered) - Init 8
        Card(
            id=CardID("rogue_gold"),
            name="Shadow Step",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="rogue_skill_gold",
            effect_text="Skill Effect (Gold)",
            secondary_actions=standard_secondaries
        ),
        
        # 2. Silver (Untiered) - Init 7
        Card(
            id=CardID("rogue_silver"),
            name="Smoke Bomb",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=7,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="rogue_skill_silver",
            effect_text="Skill Effect (Silver)",
            secondary_actions=standard_secondaries
        ),
        
        # 3. Red (Tier I) - Init 6
        Card(
            id=CardID("rogue_red_1"),
            name="Crimson Strike",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="rogue_skill_red",
            effect_text="Skill Effect (Red)",
            secondary_actions=standard_secondaries
        ),
        
        # 4. Blue (Tier I) - Init 5
        Card(
            id=CardID("rogue_blue_1"),
            name="Azure Dash",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="rogue_skill_blue",
            effect_text="Skill Effect (Blue)",
            secondary_actions=standard_secondaries
        ),
        
        # 5. Green (Tier I) - Init 4
        Card(
            id=CardID("rogue_green_1"),
            name="Emerald Cloak",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="rogue_skill_green",
            effect_text="Skill Effect (Green)",
            secondary_actions=standard_secondaries
        )
    ]
    
    h = Hero(
        id=HeroID("hero_rogue"),
        name="Rogue",
        deck=deck,
        hand=[],
        items={}
    )
    return h

HeroRegistry.register(create_rogue())