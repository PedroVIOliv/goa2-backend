from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, StatType
from goa2.domain.types import HeroID, CardID
from .registry import HeroRegistry

def create_knight() -> Hero:
    """
    Knight: Melee Tank. High defense, slow movement.
    """
    name = "Knight"
    title = "Melee Tank"
    deck = [
        Card(
            id=CardID("knight_gold_1"),
            name="Shield Bash",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            effect_id="knight_shield_bash",
            effect_text="Attack 4. Push 1.",
            secondary_actions={ActionType.HOLD: 0, ActionType.MOVEMENT: 0}
        ),
        Card(
            id=CardID("knight_gold_2"),
            name="March",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=3,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=3,
            effect_id="knight_march",
            effect_text="Move 3.",
            secondary_actions={}
        ),
        Card(
             id=CardID("knight_silver_1"),
             name="Defend",
             tier=CardTier.UNTIERED,
             color=CardColor.SILVER,
             initiative=10, 
             primary_action=ActionType.SKILL,
             # Skill value usually defined by effect, but let's say 2 for +2 Defense
             primary_action_value=None,
             effect_id="knight_defend",
             effect_text="Gain +2 Defense this round.",
             secondary_actions={}
        )
    ]
    
    h = Hero(
        id=HeroID("hero_knight"),
        name="Knight",
        deck=deck,
        hand=[],
        items={StatType.DEFENSE: 1} # Passive +1 Defense
    )
    return h

HeroRegistry.register(create_knight())
