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


def create_wuk() -> Hero:
    """
    Wuk
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="march_of_nature",
        name="March of Nature",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        radius_value=3,
        effect_id="march_of_nature",
        effect_text="Each time after you resolve a card, you may place a :tree_token: Tree token in radius.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="monstrous_throw",
            name="Monstrous Throw",
            image_id="GreenIIIA",  # Evolution of Toss Away -> Mighty Throw
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="monstrous_throw",
            effect_text="Place a token, or an enemy unit, adjacent to you into a space in range.\nMay repeat once.",
        ),
        Card(
            id="treetop_ride",
            name="Treetop Ride",
            image_id="GreenIIIB",  # Evolution of Into the Canopy
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=2,
            item=StatType.DEFENSE,
            effect_id="treetop_ride",
            effect_text="Choose up to two times —\n• Swap with a :tree_token: Tree token in radius.\n• Swap a friendly unit in radius with a Tree token in radius.",
        ),
        Card(
            id="assert_dominance",
            name="Assert Dominance",
            image_id="BlueIIIB",  # Evolution of Claim Dominance
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 2},
            item=StatType.MOVEMENT,
            effect_id="assert_dominance",
            effect_text="This round: Up to 2 enemy minions adjacent to you do not count towards the minion total during minion battle, regardless of immunity.",
        ),
        Card(
            id="abundance",
            name="Abundance",
            image_id="BlueIIIA",  # Evolution of Gifts of Nature -> Tree of Plenty
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.RANGE,
            effect_id="abundance",
            effect_text="Remove a :tree_token: Tree token in radius.\nChoose one or both —\n• You may retrieve a discarded card.\n• A friendly hero in radius may retrieve a discarded card.",
        ),
        Card(
            id="angry_stampede",
            name="Angry Stampede",
            image_id="RedIIIB",  # Evolution of Trample
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 7},
            item=StatType.RADIUS,
            effect_id="angry_stampede",
            effect_text="If you move in a straight line: You may ignore obstacles; each enemy hero you moved through discards a card, or is defeated; defeat up to two minions you moved through.",
        ),
        Card(
            id="natures_champion",
            name="Nature's Champion",
            image_id="RedIIIA",  # Evolution of Nature's Protector -> Nature's Guardian
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 8, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=3,
            item=StatType.INITIATIVE,
            effect_id="natures_champion",
            effect_text="Choose one, or both, on different targets —\n• Target a hero adjacent to you.\n• Target a unit in range adjacent to a :tree_token: Tree token.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="mighty_throw",
            name="Mighty Throw",
            image_id="GreenIIA",  # Evolution of Toss Away
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="mighty_throw",
            effect_text="Place a token, or an enemy unit, adjacent to you into a space in range.",
        ),
        Card(
            id="into_the_canopy",
            name="Into the Canopy",
            image_id="GreenIIB",  # Canopy Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=2,
            item=StatType.DEFENSE,
            effect_id="into_the_canopy",
            effect_text="Choose one —\n• Swap with a :tree_token: Tree token in radius.\n• Swap a friendly unit in radius with a Tree token in radius.",
        ),
        Card(
            id="claim_dominance",
            name="Claim Dominance",
            image_id="BlueIIB",  # Dominance Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="claim_dominance",
            effect_text="This round: Up to 1 enemy minion adjacent to you does not count towards the minion total during minion battle, regardless of immunity.",
        ),
        Card(
            id="tree_of_plenty",
            name="Tree of Plenty",
            image_id="BlueIIA",  # Evolution of Gifts of Nature
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="tree_of_plenty",
            effect_text="Remove a :tree_token: Tree token in radius.\nChoose one —\n• You may retrieve a discarded card.\n• A friendly hero in radius may retrieve a discarded card.",
        ),
        Card(
            id="trample",
            name="Trample",
            image_id="RedIIB",  # Trample Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 7},
            item=StatType.DEFENSE,
            effect_id="trample",
            effect_text="If you move in a straight line: You may ignore obstacles; each enemy hero you moved through discards a card, or is defeated; defeat up to one minion you moved through.",
        ),
        Card(
            id="natures_guardian",
            name="Nature's Guardian",
            image_id="RedIIA",  # Evolution of Nature's Protector
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 8, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=3,
            item=StatType.INITIATIVE,
            effect_id="natures_guardian",
            effect_text="Choose one —\n• Target a hero adjacent to you.\n• Target a unit in range adjacent to a :tree_token: Tree token.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="toss_away",
            name="Toss Away",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            effect_id="toss_away",
            effect_text="Place a token, or an enemy unit, adjacent to you into a space in range.",
        ),
        Card(
            id="gifts_of_nature",
            name="Gifts of Nature",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="gifts_of_nature",
            effect_text="Remove a :tree_token: Tree token in radius.\nYou may retrieve a discarded card.",
        ),
        Card(
            id="natures_protector",
            name="Nature's Protector",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=2,
            effect_id="natures_protector",
            effect_text="Choose one —\n• Target a hero adjacent to you.\n• Target a unit in range adjacent to a :tree_token: Tree token.",
        ),
        Card(
            id="mystic_saplings",
            name="Mystic Saplings",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4},
            radius_value=3,
            effect_id="mystic_saplings",
            effect_text="Place up to 3 :tree_token: Tree tokens in radius; Tree tokens are not removed at the end of round.",
        ),
        Card(
            id="tree_slam",
            name="Tree Slam",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=2,
            effect_id="tree_slam",
            effect_text="Choose one —\n• Target a minion adjacent to you.\n• Remove a :tree_token: Tree token adjacent to you. Target a unit in range.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_wuk"),
        name="Wuk",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_wuk())
