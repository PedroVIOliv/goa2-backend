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


def create_takahide() -> Hero:
    """
    Takahide
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="ready_for_war",
        name="Ready for War",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="ready_for_war",
        effect_text="Return your silver card to your deck and take two gold cards from your deck into your hand.\n( You now have a total hand size of 6 cards. )",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="the_right_hand",
            name="The Right Hand",
            image_id="BlueIIIA",  # Evolution of Proven Warrior -> Chosen Champion
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="the_right_hand",
            effect_text="Choose a card in the discard of a friendly hero in radius. Up to two enemy heroes in radius discard a card of the same color, if able.",
        ),
        Card(
            id="tactical_gambit",
            name="Tactical Gambit",
            image_id="BlueIIIB",  # Evolution of Calculated Risk
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="tactical_gambit",
            effect_text="A friendly hero in radius may discard an attack card. If that hero has a card in the discard, that hero may move up to 2 spaces, ignoring obstacles.",
        ),
        Card(
            id="commit_reserves",
            name="Commit Reserves",
            image_id="GreenIIIA",  # Evolution of Come to Aid -> Bring the Relief
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.RADIUS,
            effect_id="commit_reserves",
            effect_text="A friendly hero in range may discard a card. If that hero has a card in the discard, you may move up to 4 spaces, ignoring obstacles.",
        ),
        Card(
            id="loyal_retainer",
            name="Loyal Retainer",
            image_id="GreenIIIB",  # Evolution of Pledge of Allegiance
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.DEFENSE,
            effect_id="loyal_retainer",
            effect_text="A friendly hero in range may discard a card. If that hero has a card in the discard, both you and that hero gain 2 coins and you may retrieve a discarded card.",
        ),
        Card(
            id="hold_my_sake",
            name="Hold My Saké",
            image_id="RedIIIA",  # Evolution of Set an Example -> Lead from the Front
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=12,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            radius_value=4,
            item=StatType.MOVEMENT,
            effect_id="hold_my_sake",
            effect_text="Target a unit adjacent to you. After the attack: A friendly hero in radius may swap their unresolved card with a card in their hand, or in their discard.",
        ),
        Card(
            id="blade_helix",
            name="Blade Helix",
            image_id="RedIIIB",  # Evolution of Spinning Blade
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=12,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            radius_value=1,
            item=StatType.RANGE,
            effect_id="blade_helix",
            effect_text="Target a unit adjacent to you. After the attack: This turn: Empty spaces in radius count as obstacles for enemy units.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="chosen_champion",
            name="Chosen Champion",
            image_id="BlueIIA",  # Evolution of Proven Warrior
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="chosen_champion",
            effect_text="Choose a card in the discard of a friendly hero in radius. An enemy hero in radius discards a card of the same color, if able.",
        ),
        Card(
            id="calculated_risk",
            name="Calculated Risk",
            image_id="BlueIIB",  # Tactical Maneuver Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="calculated_risk",
            effect_text="A friendly hero in radius may discard an attack card. If that hero has a card in the discard, that hero may move up to 2 spaces.",
        ),
        Card(
            id="bring_the_relief",
            name="Bring the Relief",
            image_id="GreenIIA",  # Evolution of Come to Aid
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="bring_the_relief",
            effect_text="A friendly hero in range may discard a card. If that hero has a card in the discard, you may move up to 4 spaces.",
        ),
        Card(
            id="pledge_of_allegiance",
            name="Pledge of Allegiance",
            image_id="GreenIIB",  # Alliance Economy Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.DEFENSE,
            effect_id="pledge_of_allegiance",
            effect_text="A friendly hero in range may discard a card. If that hero has a card in the discard, both you and that hero gain 1 coin and you may retrieve a discarded card.",
        ),
        Card(
            id="lead_from_the_front",
            name="Lead from the Front",
            image_id="RedIIA",  # Evolution of Set an Example
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=11,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="lead_from_the_front",
            effect_text="Target a unit adjacent to you. After the attack: A friendly hero in radius may swap their unresolved card with a card in their hand.",
        ),
        Card(
            id="spinning_blade",
            name="Spinning Blade",
            image_id="RedIIB",  # Spatial Denial Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=11,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            item=StatType.DEFENSE,
            effect_id="spinning_blade",
            effect_text="Target a unit adjacent to you. After the attack: This turn: Empty spaces adjacent to you count as obstacles for enemy units.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="proven_warrior",
            name="Proven Warrior",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="proven_warrior",
            effect_text="Choose a card in the discard of a friendly hero in radius. An enemy hero in radius discards a card of the same color, if able.",
        ),
        Card(
            id="come_to_aid",
            name="Come to Aid",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            effect_id="come_to_aid",
            effect_text="A friendly hero in range may discard a card. If that hero has a card in the discard, you may move up to 3 spaces.",
        ),
        Card(
            id="set_an_example",
            name="Set an Example",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=11,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 1},
            radius_value=3,
            effect_id="set_an_example",
            effect_text="Target a unit adjacent to you. After the attack: A friendly hero in radius may swap their unresolved card with a card in their hand.",
        ),
        Card(
            id="bushido",
            name="Bushido",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=5,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6},
            effect_id="bushido",
            effect_text="Swap your gold card with a different gold card in your deck; if you swap a resolved or discarded card this way, place the new card facedown.",
        ),
        Card(
            id="float_like_a_butterfly",
            name="Float Like a Butterfly",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=8,
            primary_action=ActionType.MOVEMENT,  # Basic Movement Frame
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 8},
            effect_id="float_like_a_butterfly",
            effect_text="Swap this card with a different gold card in your deck.\n( This card starts the game in your hand. )",
        ),
        Card(
            id="sting_like_a_bee",
            name="Sting Like a Bee",
            image_id="Extra1",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=7,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=3,
            starts_in_deck=True,
            effect_id="sting_like_a_bee",
            effect_text="Target a unit at maximum range.\nAfter the attack: Swap this card with a different gold card in your deck.\n( This card starts the game in your deck. )",
        ),
        Card(
            id="strike_like_a_tiger",
            name="Strike Like a Tiger",
            image_id="Extra2",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=9,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=7,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            starts_in_deck=True,
            effect_id="strike_like_a_tiger",
            effect_text="Target a unit adjacent to you.\nAfter the attack: Swap this card with a different gold card in your deck.\n( This card starts the game in your deck. )",
        ),
    ]

    h = Hero(
        id=HeroID("hero_takahide"),
        name="Takahide",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_takahide())
