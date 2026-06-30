from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Hero,
    StatType,
)
from goa2.domain.types import HeroID

from .registry import HeroRegistry


def create_cutter() -> Hero:
    """
    Cutter
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="legend_of_the_skies",
        name="Legend of the Skies",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="legend_of_the_skies",
        effect_text="The first time each turn after you perform a primary action, you may perform the primary action of a card in the previous turn slot.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="broadside",
            name="Broadside",
            image_id="BlueIIIA",  # Evolution of Bombardment -> Barrage
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="broadside",
            effect_text="An enemy hero in radius, adjacent to another enemy unit and not adjacent to you, discards a card, if able.\nMay repeat once on a different target.",
        ),
        Card(
            id="a_fistful_of_coins",
            name="A Fistful of Coins",
            image_id="BlueIIIB",  # Evolution of X Marks the Spot
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="a_fistful_of_coins",
            effect_text="An enemy hero in radius chooses one —\n• You place that hero in a space in radius.\n• You gain 3 coins. If you have 13 or more coins, you alone win the game.",
        ),
        Card(
            id="crashland",
            name="Crashland",
            image_id="GreenIIIA",  # Evolution of Brace for Impact -> Ramming Speed
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.RANGE,
            effect_id="crashland",
            effect_text="Move 3, 4 or 5 spaces in a straight line, ignoring obstacles, to a space adjacent to an enemy hero; that hero discards a card, if able.",
        ),
        Card(
            id="outsmart",
            name="Outsmart",
            image_id="GreenIIIB",  # Evolution of Outmaneuver
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.DEFENSE,
            effect_id="outsmart",
            effect_text="Swap with an enemy minion in radius; you may move that minion up to 3 spaces.",
        ),
        Card(
            id="fearless_lunge",
            name="Fearless Lunge",
            image_id="RedIIIA",  # Evolution of Daring Strike -> Bold Thrust
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.MOVEMENT,
            effect_id="fearless_lunge",
            effect_text="Choose one —\n• Before the attack: Move 1, 2 or 3 spaces in a straight line. Target a hero adjacent to you in the direction of the move; +2 :attack: Attack.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="tumble_shot",
            name="Tumble Shot",
            image_id="RedIIIB",  # Evolution of Evasive Shot
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=2,
            item=StatType.RADIUS,
            effect_id="tumble_shot",
            effect_text="Target a unit in range and in a straight line.\nAfter the attack: Move up to 3 spaces in the opposite direction.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="barrage",
            name="Barrage",
            image_id="BlueIIA",  # Evolution of Bombardment
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="barrage",
            effect_text="An enemy hero in radius, adjacent to another enemy unit and not adjacent to you, discards a card, if able.",
        ),
        Card(
            id="x_marks_the_spot",
            name="X Marks the Spot",
            image_id="BlueIIB",  # Choosing Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="x_marks_the_spot",
            effect_text="An enemy hero in radius chooses one —\n• You place that hero in a space in radius.\n• You gain 2 coins.",
        ),
        Card(
            id="ramming_speed",
            name="Ramming Speed",
            image_id="GreenIIA",  # Evolution of Brace for Impact
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            item=StatType.ATTACK,
            effect_id="ramming_speed",
            effect_text="Move 3 or 4 spaces in a straight line, ignoring obstacles, to a space adjacent to an enemy hero; that hero discards a card, if able.",
        ),
        Card(
            id="outmaneuver",
            name="Outmaneuver",
            image_id="GreenIIB",  # Swap Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.DEFENSE,
            effect_id="outmaneuver",
            effect_text="Swap with an enemy minion in radius; you may move that minion up to 2 spaces.",
        ),
        Card(
            id="bold_thrust",
            name="Bold Thrust",
            image_id="RedIIA",  # Evolution of Daring Strike
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            item=StatType.INITIATIVE,
            effect_id="bold_thrust",
            effect_text="Choose one —\n• Before the attack: Move 1 or 2 spaces in a straight line. Target a hero adjacent to you in the direction of the move; +2 :attack: Attack.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="evasive_shot",
            name="Evasive Shot",
            image_id="RedIIB",  # Disengage Combat Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=2,
            item=StatType.DEFENSE,
            effect_id="evasive_shot",
            effect_text="Target a unit in range and in a straight line.\nAfter the attack: Move up to 2 spaces in the opposite direction.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="bombardment",
            name="Bombardment",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=3,
            effect_id="bombardment",
            effect_text="An enemy hero in radius, adjacent to another enemy unit and not adjacent to you, discards a card, if able.",
        ),
        Card(
            id="brace_for_impact",
            name="Brace for Impact",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            effect_id="brace_for_impact",
            effect_text="Move 3 spaces in a straight line, ignoring obstacles, to a space adjacent to an enemy hero; that hero discards a card, if able.",
        ),
        Card(
            id="daring_strike",
            name="Daring Strike",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            effect_id="daring_strike",
            effect_text="Choose one —\n• Before the attack: Move 1 space. Target a hero adjacent to you in the direction of the move; +2 :attack: Attack.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="grappling_bolt",
            name="Grappling Bolt",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=5,
            primary_action=ActionType.SKILL,  # Basic Skill - Ranged Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2},
            is_ranged=True,
            range_value=5,
            effect_id="grappling_bolt",
            effect_text="Target an obstacle in range and in a straight line, with no obstacles between you; ignore immunity. Move in a straight line towards that obstacle until you are adjacent to it.",
        ),
        Card(
            id="walk_the_plank",
            name="Walk the Plank",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=12,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            effect_id="walk_the_plank",
            effect_text="Choose one —\n• Push an enemy hero adjacent to you up to 4 spaces; if that hero is pushed into another zone, that hero discards a card, or is defeated.\n• Defeat a minion adjacent to you.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_cutter"),
        name="Cutter",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_cutter())
