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


def create_cordelia() -> Hero:
    """
    Cordelia
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="witching_hour",
        name="Witching Hour",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        radius_value=4,
        effect_id="witching_hour",
        effect_text="Enemy heroes in radius cannot perform attack actions if their Attack value is below zero.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="this_is_my_broomstick",
            name="This Is My Broomstick!",
            image_id="RedIIIA",  # Evolution of Broom for Improvement -> Broomstick Beatdown
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            item=StatType.RADIUS,
            effect_id="this_is_my_broomstick",
            effect_text="Target a unit adjacent to you. After the attack: This round: Your basic actions gain +3 :movement: Movement, +3 :initiative: Initiative, +3 :attack: Attack, +3 :defense: Defense.",
        ),
        Card(
            id="fatal_bonds",
            name="Fatal Bonds",
            image_id="RedIIIB",  # Evolution of Collateral Misfortune
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=3,
            item=StatType.MOVEMENT,
            effect_id="fatal_bonds",
            effect_text="Choose one, or both on different targets —\n• Target a unit adjacent to you.\n• Target a unit in range adjacent to an enemy hero.",
        ),
        Card(
            id="toxic_tranquility",
            name="Toxic Tranquility",
            image_id="BlueIIIA",  # Evolution of Healing Spores -> Fungal Favor
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="toxic_tranquility",
            effect_text="A friendly hero in radius may retrieve a discarded card. If they do, each enemy hero in radius loses 1 coin.",
        ),
        Card(
            id="potion_explosion",
            name="Potion Explosion",
            image_id="BlueIIIB",  # Evolution of Vile Vial
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.RANGE,
            effect_id="potion_explosion",
            effect_text="An enemy hero in radius reveals a card from their hand; gain coins equal to that card's tier; if you gain less than 3 coins, discard that card.",
        ),
        Card(
            id="enchanted_path",
            name="Enchanted Path",
            image_id="GreenIIIA",  # Evolution of Charmed Step -> Candy Trail
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            item=StatType.ATTACK,
            effect_id="enchanted_path",
            effect_text="Place yourself into a space adjacent to an enemy hero in range. Push that hero 1 or 2 spaces.",
        ),
        Card(
            id="recipe_for_disaster",
            name="Recipe for Disaster",
            image_id="GreenIIIB",  # Evolution of Trouble Brewing
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.INITIATIVE,
            effect_id="recipe_for_disaster",
            effect_text="Place an enemy minion in range into a space adjacent to you. You may retrieve a discarded basic card.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="broomstick_beatdown",
            name="Broomstick Beatdown",
            image_id="RedIIA",  # Evolution of Broom for Improvement
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            item=StatType.INITIATIVE,
            effect_id="broomstick_beatdown",
            effect_text="Target a unit adjacent to you. After the attack: This round: Your basic actions gain +2 :movement: Movement, +2 :initiative: Initiative, +2 :attack: Attack, +2 :defense: Defense.",
        ),
        Card(
            id="collateral_misfortune",
            name="Collateral Misfortune",
            image_id="RedIIB",  # Adjacent Hero Combat Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=3,
            item=StatType.DEFENSE,
            effect_id="collateral_misfortune",
            effect_text="Choose one —\n• Target a unit adjacent to you.\n• Target a unit in range adjacent to an enemy hero.",
        ),
        Card(
            id="fungal_favor",
            name="Fungal Favor",
            image_id="BlueIIA",  # Evolution of Healing Spores
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="fungal_favor",
            effect_text="A friendly hero in radius may retrieve a discarded card. If they do, an enemy hero in radius loses 1 coin.",
        ),
        Card(
            id="vile_vial",
            name="Vile Vial",
            image_id="BlueIIB",  # Card Reveal Plunder Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="vile_vial",
            effect_text="An enemy hero in radius reveals a card from their hand; gain coins equal to that card's tier; if you gain less than 2 coins, discard that card.",
        ),
        Card(
            id="candy_trail",
            name="Candy Trail",
            image_id="GreenIIA",  # Evolution of Charmed Step
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            item=StatType.ATTACK,
            effect_id="candy_trail",
            effect_text="Place yourself into a space adjacent to an enemy hero in range. Push that hero 1 space.",
        ),
        Card(
            id="trouble_brewing",
            name="Trouble Brewing",
            image_id="GreenIIB",  # Minion Drag Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.INITIATIVE,
            effect_id="trouble_brewing",
            effect_text="Place an enemy minion in range into a space adjacent to you.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="broom_for_improvement",
            name="Broom for Improvement",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 4},
            effect_id="broom_for_improvement",
            effect_text="Target a unit adjacent to you. After the attack: This round: Your basic actions gain +1 :movement: Movement, +1 :initiative: Initiative, +1 :attack: Attack, +1 :defense: Defense.",
        ),
        Card(
            id="healing_spores",
            name="Healing Spores",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=3,
            effect_id="healing_spores",
            effect_text="A friendly hero in radius may retrieve a discarded card. If they do, an enemy hero in radius loses 1 coin.",
        ),
        Card(
            id="charmed_step",
            name="Charmed Step",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=2,
            effect_id="charmed_step",
            effect_text="Place yourself into a space adjacent to an enemy hero in range. Push that hero 1 space.",
        ),
        Card(
            id="bewitch",
            name="Bewitch",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 1},
            radius_value=4,
            effect_id="bewitch",
            effect_text="Target a unit adjacent to you. Before the attack: This turn: Enemy heroes in radius have -1 :range: Range (to a minimum of 1).",
        ),
        Card(
            id="jinx",
            name="Jinx",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=13,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2},
            radius_value=4,
            effect_id="jinx",
            effect_text="This turn: Enemy heroes in radius have -10 :attack: Attack; each time after you discard a card, you may move 1 space.\n( Negative attack value still defeats heroes, unless defended. )",
        ),
    ]

    h = Hero(
        id=HeroID("hero_cordelia"),
        name="Cordelia",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_cordelia(), is_playtest=True)
