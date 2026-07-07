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


def create_nebkher() -> Hero:
    """
    NebKher
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="what_the_hell_are_you",
        name="What the Hell Are You?",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        radius_value=5,
        effect_id="what_the_hell_are_you",
        effect_text="Each time after you laugh diabolically as part of performing an action, all enemy heroes in radius discard a card, or are defeated.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="an_illusion_of_choice",
            name="An Illusion of Choice",
            image_id="BlueIIIA",  # Evolution of Imbue Doubt -> Time to Reconsider
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.MOVEMENT,
            effect_id="an_illusion_of_choice",
            effect_text="Name a color. Next turn, after playing cards:\nUp to two enemy heroes in radius each discard a card of that color, if able.",
        ),
        Card(
            id="shift_reality",
            name="Shift Reality",
            image_id="BlueIIIB",  # Evolution of Crack in Reality
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            item=StatType.RANGE,
            effect_id="shift_reality",
            effect_text="Split the board into two sides with a straight line of spaces drawn through your space.\nThis turn: Units on either side of the line cannot interact with you, nor with objects and spaces on the other side of the line, as if they did not exist.",
        ),
        Card(
            id="master_of_illusions",
            name="Master of Illusions",
            image_id="GreenIIIA",  # Evolution of Fleeting Image -> Multiple Projections
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="master_of_illusions",
            effect_text="Place up to 3 :illusion_token: Illusion tokens in radius.\nYou may swap with an Illusion token in play.",
        ),
        Card(
            id="illusionary_army",
            name="Illusionary Army",
            image_id="GreenIIIB",  # Evolution of Illusionary Force
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="illusionary_army",
            effect_text="Place up to 3 :illusion_token: Illusion tokens in radius.\nThis round: While you are performing actions, all Illusion tokens count as both tokens and friendly melee minions.",
        ),
        Card(
            id="phantasmal_champion",
            name="Phantasmal Champion",
            image_id="RedIIIA",  # Evolution of Phantasmal Sentry -> Phantasmal Warrior
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=5,
            item=StatType.RADIUS,
            effect_id="phantasmal_champion",
            effect_text="Choose one —\n• Before the attack: Move an :illusion_token: Illusion token in range up to 2 spaces to a space adjacent to an enemy hero in range. Target that hero.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="devious_scheme",
            name="Devious Scheme",
            image_id="RedIIIB",  # Evolution of Twist Fate
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=2,
            item=StatType.DEFENSE,
            effect_id="devious_scheme",
            effect_text="Target a unit in range. After the attack:\nYou may swap an enemy unit in range with an :illusion_token: Illusion token in range.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="time_to_reconsider",
            name="Time to Reconsider",
            image_id="BlueIIA",  # Evolution of Imbue Doubt
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="time_to_reconsider",
            effect_text="Name a color. Next turn, after playing cards:\nAn enemy hero in radius discards a card of that color, if able.",
        ),
        Card(
            id="crack_in_reality",
            name="Crack in Reality",
            image_id="BlueIIB",  # Phase Line Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            item=StatType.DEFENSE,
            effect_id="crack_in_reality",
            effect_text="Split the board into two sides with a straight line of spaces drawn through your space.\nThis turn: Units on either side of the line cannot interact with objects and spaces on the other side of the line, as if they did not exist.\n( This includes movement, placement, radius-based effects, etc. )",
        ),
        Card(
            id="multiple_projections",
            name="Multiple Projections",
            image_id="GreenIIA",  # Evolution of Fleeting Image
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="multiple_projections",
            effect_text="Place up to 2 :illusion_token: Illusion tokens in radius.\nYou may swap with an Illusion token in play.",
        ),
        Card(
            id="illusionary_force",
            name="Illusionary Force",
            image_id="GreenIIB",  # Combat Formation Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="illusionary_force",
            effect_text="Place up to 2 :illusion_token: Illusion tokens in radius.\nThis round: While you are performing actions, all Illusion tokens count as both tokens and friendly melee minions.",
        ),
        Card(
            id="phantasmal_warrior",
            name="Phantasmal Warrior",
            image_id="RedIIA",  # Evolution of Phantasmal Sentry
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=5,
            item=StatType.INITIATIVE,
            effect_id="phantasmal_warrior",
            effect_text="Choose one —\n• Before the attack: Move an :illusion_token: Illusion token in range up to 1 space to a space adjacent to an enemy hero in range. Target that hero.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="twist_fate",
            name="Twist Fate",
            image_id="RedIIB",  # Proximity Swapping Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=2,
            item=StatType.DEFENSE,
            effect_id="twist_fate",
            effect_text="Target a unit in range. After the attack:\nYou may swap an enemy unit in range with an :illusion_token: Illusion token adjacent to you.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="imbue_doubt",
            name="Imbue Doubt",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="imbue_doubt",
            effect_text="Name a color. Next turn, after playing cards:\nAn enemy hero in radius discards a card of that color, if able.",
        ),
        Card(
            id="fleeting_image",
            name="Fleeting Image",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=2,
            effect_id="fleeting_image",
            effect_text="Place an :illusion_token: Illusion token in radius.\nYou may swap with an Illusion token in play.",
        ),
        Card(
            id="phantasmal_sentry",
            name="Phantasmal Sentry",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=4,
            effect_id="phantasmal_sentry",
            effect_text="Choose one —\n• Target a hero in range adjacent to an :illusion_token: Illusion token in range.\n• Target a unit adjacent to you.",
        ),
        Card(
            id="diabolical_laughter",
            name="Diabolical Laughter",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=3,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3},
            radius_value=4,
            effect_id="diabolical_laughter",
            effect_text="Laugh diabolically;\nif you do, choose up to three times —\n• Swap with an :illusion_token: Illusion token in radius.\n• Place an Illusion token in an adjacent space.\n• Swap two resolved cards of an enemy hero in radius, without canceling active effects.",
        ),
        Card(
            id="mind_grip",
            name="Mind Grip",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=9,
            primary_action=ActionType.SKILL,  # Labeled Basic Skill - Ranged Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=5,
            effect_id="mind_grip",
            effect_text="Choose one —\n• Perform an action on the card in the previous turn slot of an enemy hero in range; if you would place any tokens this way, place :illusion_token: Illusion tokens instead; skip giving markers.\n• Defeat a minion adjacent to you.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_nebkher"),
        name="NebKher",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_nebkher())
