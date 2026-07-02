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


def create_hanu() -> Hero:
    """
    Hanu
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="the_ultimate_trick",
        name="The Ultimate Trick",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="the_ultimate_trick",
        effect_text='You choose the next action, and how it is performed, for a hero you target with the "Hurry Up!".',
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="safe_travels",
            name="Safe Travels",
            image_id="BlueIIIA",  # Evolution of Unexpected Journey -> There and Back Again
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="safe_travels",
            effect_text="Swap with an enemy hero in radius.\nThis turn: That hero is immune.\nEnd of turn: Swap with that hero, regardless of radius and immunity. You may move 1 space.",
        ),
        Card(
            id="that_way",
            name="That Way!",
            image_id="BlueIIIB",  # Evolution of This Way!
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="that_way",
            effect_text="A friendly hero in radius chooses a distance of 1, 2 or 3; move both of you that number of spaces in the same direction of your choice.",
        ),
        Card(
            id="see_nothing",
            name="See Nothing",
            image_id="GreenIIIB",  # Evolution of Hear Nothing
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.RANGE,
            effect_id="see_nothing",
            effect_text="Swap with an enemy hero in radius.\nYou may move 1 space.",
        ),
        Card(
            id="monkey_business",
            name="Monkey Business",
            image_id="GreenIIIA",  # Evolution of Monkey Trick -> Monkey Twist
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=2,
            item=StatType.DEFENSE,
            effect_id="monkey_business",
            effect_text="Swap two friendly units in radius.\nYou may move 1 space.",
        ),
        Card(
            id="trusted_sidekick",
            name="Trusted Sidekick",
            image_id="RedIIIA",  # Evolution of Helping Hand -> Even the Odds
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 5},
            is_ranged=True,
            range_value=4,
            item=StatType.MOVEMENT,
            effect_id="trusted_sidekick",
            effect_text="Choose one, or both, in any order —\n• Target a unit adjacent to you.\n• Target a hero in range, adjacent to your friendly hero and not adjacent to you.",
        ),
        Card(
            id="pile_on",
            name="Pile On",
            image_id="RedIIIB",  # Evolution of Outnumber
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 5},
            is_ranged=True,
            range_value=4,
            item=StatType.RADIUS,
            effect_id="pile_on",
            effect_text="Choose one, or both, in any order —\n• Target a unit adjacent to you.\n• Target a minion in range, adjacent to your friendly hero.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="there_and_back_again",
            name="There and Back Again",
            image_id="BlueIIA",  # Evolution of Unexpected Journey
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="there_and_back_again",
            effect_text="Swap with an enemy hero in radius.\nThis turn: That hero is immune.\nEnd of turn: Swap with that hero, regardless of radius and immunity.",
        ),
        Card(
            id="this_way",
            name="This Way!",
            image_id="BlueIIB",  # Symmetrical Guidance Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="this_way",
            effect_text="A friendly hero in radius chooses a distance of 1 or 2; move both of you that number of spaces in the same direction of your choice.\n( Both must be moved the full distance, or neither one moves. )",
        ),
        Card(
            id="monkey_twist",
            name="Monkey Twist",
            image_id="GreenIIA",  # Evolution of Monkey Trick
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=2,
            item=StatType.DEFENSE,
            effect_id="monkey_twist",
            effect_text="Swap two friendly units in radius.",
        ),
        Card(
            id="hear_nothing",
            name="Hear Nothing",
            image_id="GreenIIB",  # Enemy Swap Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="hear_nothing",
            effect_text="Swap with an enemy hero in radius.",
        ),
        Card(
            id="even_the_odds",
            name="Even the Odds",
            image_id="RedIIA",  # Evolution of Helping Hand (Hero Target)
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 5},
            is_ranged=True,
            range_value=4,
            item=StatType.INITIATIVE,
            effect_id="even_the_odds",
            effect_text="Choose one —\n• Target a unit adjacent to you.\n• Target a hero in range, adjacent to your friendly hero.",
        ),
        Card(
            id="outnumber",
            name="Outnumber",
            image_id="RedIIB",  # Minion Proximity Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 5},
            is_ranged=True,
            range_value=4,
            item=StatType.DEFENSE,
            effect_id="outnumber",
            effect_text="Choose one —\n• Target a unit adjacent to you.\n• Target a minion in range, adjacent to your friendly hero.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="unexpected_journey",
            name="Unexpected Journey",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=2,
            effect_id="unexpected_journey",
            effect_text="Swap with an enemy hero in radius.\nThis turn: That hero is immune.\nEnd of turn: Swap with that hero, regardless of radius and immunity.",
        ),
        Card(
            id="monkey_trick",
            name="Monkey Trick",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 2},
            radius_value=1,
            effect_id="monkey_trick",
            effect_text="Swap two friendly units in radius.",
        ),
        Card(
            id="helping_hand",
            name="Helping Hand",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 5},
            is_ranged=True,
            range_value=3,
            effect_id="helping_hand",
            effect_text="Choose one —\n• Target a unit adjacent to you.\n• Target a hero in range, adjacent to your friendly hero.",
        ),
        Card(
            id="hurry_up",
            name="Hurry Up!",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=12,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 1},
            is_ranged=True,
            range_value=4,
            effect_id="hurry_up",
            effect_text="Set the printed :initiative: Initiative value of an unresolved card of a hero in range to 11, until it is resolved, or otherwise changes state.\n( This may change the initiative order and tie breakers. )",
        ),
        Card(
            id="fight_and_flight",
            name="Fight and Flight",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=13,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 2},
            effect_id="fight_and_flight",
            effect_text="Target a unit adjacent to you. If the target is not defeated, After the attack: If able, move 3 spaces in a straight line.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_hanu"),
        name="Hanu",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_hanu())
