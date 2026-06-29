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


def create_mrak() -> Hero:
    """
    Mrak
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="rock_and_a_hard_place",
        name="Rock and a Hard Place",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="rock_and_a_hard_place",
        effect_text="Once per turn, after you place one or more :rock_token: Rock tokens into one or more spaces adjacent to one or more enemy heroes, each of those heroes discards a card, if able.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="avalanche",
            name="Avalanche",
            image_id="GreenIIIA",  # Evolution of Treacherous Ground -> Rockslide
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.RADIUS,
            effect_id="avalanche",
            effect_text="You may move a unit in range 1 space to a space adjacent to terrain, or a :rock_token: Rock token.\nMay repeat once.",
        ),
        Card(
            id="strolling_stone",
            name="Strolling Stone",
            image_id="GreenIIIB",  # Evolution of Rolling Stone
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="strolling_stone",
            effect_text="Move any number of spaces in a straight line, ignoring obstacles, without moving through more than two empty spaces.",
        ),
        Card(
            id="boulderdozer",
            name="Boulderdozer",
            image_id="BlueIIIA",  # Evolution of Boulder Rush -> Boulder Blitz
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 2},
            item=StatType.MOVEMENT,
            effect_id="boulderdozer",
            effect_text="Push a token, or an enemy unit, adjacent to you 1, 2, 3 or 4 spaces, ignoring obstacles; you may move up to 4 spaces in the direction of the push, ignoring obstacles.",
        ),
        Card(
            id="ground_shaker",
            name="Ground Shaker",
            image_id="BlueIIIB",  # Evolution of Stomping Step
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="ground_shaker",
            effect_text="Move a unit in radius which is adjacent to terrain, or to a :rock_token: Rock token, 1 space.\nPlace a Rock token in the space it occupied.\nMay repeat once on a different target.",
        ),
        Card(
            id="epicenter",
            name="Epicenter",
            image_id="RedIIIA",  # Evolution of Seismic Slam -> Seismic Assault
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.ATTACK: 7, ActionType.DEFENSE: 8, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.RANGE,
            effect_id="epicenter",
            effect_text="An enemy hero in radius adjacent to terrain, or to a :rock_token: Rock token, discards a card, or is defeated.\nMay repeat once on a different target.",
        ),
        Card(
            id="rock_solid",
            name="Rock Solid",
            image_id="RedIIIB",  # Evolution of Stone Carapace
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=4,
            secondary_actions={ActionType.ATTACK: 7, ActionType.DEFENSE: 6},
            item=StatType.DEFENSE,
            effect_id="rock_solid",
            effect_text="You may retrieve a discarded card.\nThis round: If you would discard a card from your hand, you may discard this card instead; you may discard this card to perform its defense action, as if it was in your hand.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="rockslide",
            name="Rockslide",
            image_id="GreenIIA",  # Evolution of Treacherous Ground
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="rockslide",
            effect_text="You may move a unit in range 1 space to a space adjacent to terrain, or a :rock_token: Rock token.",
        ),
        Card(
            id="rolling_stone",
            name="Rolling Stone",
            image_id="GreenIIB",  # Movement Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="rolling_stone",
            effect_text="Move any number of spaces in a straight line, ignoring obstacles, without moving through more than one empty space.\n( The starting space and the destination space do not count. )",
        ),
        Card(
            id="boulder_blitz",
            name="Boulder Blitz",
            image_id="BlueIIA",  # Evolution of Boulder Rush
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 2},
            item=StatType.DEFENSE,
            effect_id="boulder_blitz",
            effect_text="Push a token, or an enemy unit, adjacent to you 1, 2 or 3 spaces, ignoring obstacles; you may move up to 3 spaces in the direction of the push, ignoring obstacles.",
        ),
        Card(
            id="stomping_step",
            name="Stomping Step",
            image_id="BlueIIB",  # Terrain Shift Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="stomping_step",
            effect_text="Move a unit in radius which is adjacent to terrain, or to a :rock_token: Rock token, 1 space.\nPlace a Rock token in the space it occupied.",
        ),
        Card(
            id="seismic_assault",
            name="Seismic Assault",
            image_id="RedIIA",  # Evolution of Seismic Slam
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.ATTACK: 7, ActionType.DEFENSE: 8, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="seismic_assault",
            effect_text="An enemy hero in radius adjacent to terrain, or to a :rock_token: Rock token, discards a card, or is defeated.",
        ),
        Card(
            id="stone_carapace",
            name="Stone Carapace",
            image_id="RedIIB",  # Discard Shield Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=4,
            secondary_actions={ActionType.ATTACK: 7, ActionType.DEFENSE: 6},
            item=StatType.DEFENSE,
            effect_id="stone_carapace",
            effect_text="This round: If you would discard a card from your hand, you may discard this card instead; you may discard this card to perform its defense action, as if it was in your hand.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="treacherous_ground",
            name="Treacherous Ground",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            effect_id="treacherous_ground",
            effect_text="You may move a unit in range 1 space to a space adjacent to terrain, or a :rock_token: Rock token.",
        ),
        Card(
            id="boulder_rush",
            name="Boulder Rush",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 2},
            effect_id="boulder_rush",
            effect_text="Push a token, or an enemy unit, adjacent to you 1 or 2 spaces, ignoring obstacles; you may move up to 2 spaces in the direction of the push, ignoring obstacles.",
        ),
        Card(
            id="seismic_slam",
            name="Seismic Slam",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.ATTACK: 6, ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            radius_value=3,
            effect_id="seismic_slam",
            effect_text="An enemy hero in radius adjacent to terrain, or to a :rock_token: Rock token, discards a card, or is defeated.\n( The :attack: secondary Attack action is non-ranged. )",
        ),
        Card(
            id="stone_grip",
            name="Stone Grip",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=12,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4},
            is_ranged=True,
            range_value=3,
            effect_id="stone_grip",
            effect_text="Place exactly 3 :rock_token: Rock tokens into empty spaces adjacent to an enemy hero in range, and as far away from you as possible.",
        ),
        Card(
            id="fissure",
            name="Fissure",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 1},
            effect_id="fissure",
            effect_text="Target a unit adjacent to you. After the attack: Place a :rock_token: Rock token in each of the first three empty spaces in the straight line from you in the direction of the attack.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_mrak"),
        name="Mrak",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_mrak())
