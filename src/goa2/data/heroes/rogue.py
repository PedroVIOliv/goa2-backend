from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, StatType
from goa2.domain.types import HeroID, CardID
from .registry import HeroRegistry

def create_rogue() -> Hero:
    """
    Rogue: Fast Assassin. High initiative, ranged options.
    """
    name = "Rogue"
    title = "Fast Assassin"
    deck = [
        Card(
            id=CardID("rogue_gold_1"),
            name="Backstab",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=12,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            effect_id="rogue_backstab",
            effect_text="Attack 5 (Melee).",
            secondary_actions={}
        ),
        Card(
            id=CardID("rogue_gold_2"),
            name="Teleport",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=10,
            primary_action=ActionType.FAST_TRAVEL,
            primary_action_value=0,
            effect_id="rogue_teleport",
            effect_text="Fast Travel.",
            secondary_actions={}
        ),
        Card(
             id=CardID("rogue_silver_1"),
             name="Dagger Throw",
             tier=CardTier.UNTIERED,
             color=CardColor.SILVER,
             initiative=5,
             primary_action=ActionType.ATTACK,
             primary_action_value=3,
             is_ranged=True,
             range_value=3,
             effect_id="rogue_dagger",
             effect_text="Ranged Attack 3.",
             secondary_actions={}
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
