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


def create_ignatia() -> Hero:
    """
    Ignatia
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="chaos_incarnate",
        name="Chaos Incarnate",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="chaos_incarnate",
        effect_text="The first time each turn after you perform a primary action, you may flip the Tie Breaker coin; if you do, you may perform that action again, choosing different targets.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="scorching_blaze",
            name="Scorching Blaze",
            image_id="BlueIIIB",  # Evolution of Searing Heat
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.MOVEMENT,
            effect_id="scorching_blaze",
            effect_text=":tiebreaker_blue: : Move a friendly hero in radius 2 or 3 spaces in a straight line.\n:tiebreaker_orange: : Move an enemy hero in radius 2 or 3 spaces in a straight line.",
        ),
        Card(
            id="violent_conflagration",
            name="Violent Conflagration",
            image_id="BlueIIIA",  # Evolution of Abrupt Combustion -> Spontaneous Immolation
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.RANGE,
            effect_id="violent_conflagration",
            effect_text=":tiebreaker_blue: : An enemy hero in radius adjacent to a token or to a minion discards a card, or is defeated.\n:tiebreaker_orange: : Defeat an enemy minion in radius adjacent to an enemy hero.",
        ),
        Card(
            id="path_of_flames",
            name="Path of Flames",
            image_id="GreenIIIA",  # Evolution of Path of Ashes -> Path of Cinders
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="path_of_flames",
            effect_text=":tiebreaker_blue: : Move up to 4 spaces in a straight line. Place a :magma_token: Magma token in each empty space you moved through, or out of.\n:tiebreaker_orange: : Place up to 4 Magma tokens in radius.",
        ),
        Card(
            id="chaos_gate",
            name="Chaos Gate",
            image_id="GreenIIIB",  # Evolution of Unstable Portal
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="chaos_gate",
            effect_text=":tiebreaker_blue: : Swap with a friendly unit in radius. You may move that unit 1 space.\n:tiebreaker_orange: : Swap with an enemy unit in radius. You may move 1 space.",
        ),
        Card(
            id="loosely_aimed_firebolts",
            name="Loosely-Aimed Firebolts",
            image_id="RedIIIA",  # Evolution of Playing with Fire -> Erratic Fireblast
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=3,
            item=StatType.RADIUS,
            effect_id="loosely_aimed_firebolts",
            effect_text=":tiebreaker_blue: : Target a unit in range not in a straight line.\n:tiebreaker_orange: : Target a unit in range in a straight line. May repeat once on a different hero.",
        ),
        Card(
            id="imminent_eruption",
            name="Imminent Eruption",
            image_id="RedIIIB",  # Evolution of Crack of Doom
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=5,
            item=StatType.INITIATIVE,
            effect_id="imminent_eruption",
            effect_text=":tiebreaker_blue: : Target a unit adjacent to you. May repeat once on a minion.\n:tiebreaker_orange: : Target a unit at maximum range.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="searing_heat",
            name="Searing Heat",
            image_id="BlueIIB",  # Linear Movement Base Trail
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="searing_heat",
            effect_text=":tiebreaker_blue: : Move a friendly hero in radius 2 spaces in a straight line.\n:tiebreaker_orange: : Move an enemy hero in radius 2 spaces in a straight line.",
        ),
        Card(
            id="spontaneous_immolation",
            name="Spontaneous Immolation",
            image_id="BlueIIA",  # Evolution of Abrupt Combustion
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="spontaneous_immolation",
            effect_text=":tiebreaker_blue: : An enemy hero in radius adjacent to a token or to a minion discards a card, if able.\n:tiebreaker_orange: : Remove an enemy minion in radius adjacent to an enemy hero.",
        ),
        Card(
            id="path_of_cinders",
            name="Path of Cinders",
            image_id="GreenIIA",  # Evolution of Path of Ashes
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="path_of_cinders",
            effect_text=":tiebreaker_blue: : Move up to 3 spaces in a straight line. Place a :magma_token: Magma token in each empty space you moved through, or out of.\n:tiebreaker_orange: : Place up to 3 Magma tokens in radius.",
        ),
        Card(
            id="unstable_portal",
            name="Unstable Portal",
            image_id="GreenIIB",  # Portal Switch Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="unstable_portal",
            effect_text=":tiebreaker_blue: : Swap with a friendly unit in radius.\n:tiebreaker_orange: : Swap with an enemy unit in radius.",
        ),
        Card(
            id="erratic_fireblast",
            name="Erratic Fireblast",
            image_id="RedIIA",  # Evolution of Playing with Fire
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=3,
            item=StatType.DEFENSE,
            effect_id="erratic_fireblast",
            effect_text=":tiebreaker_blue: : Target a unit in range not in a straight line.\n:tiebreaker_orange: : Target a unit in range in a straight line.",
        ),
        Card(
            id="crack_of_doom",
            name="Crack of Doom",
            image_id="RedIIB",  # Range Extremes Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=5,
            item=StatType.INITIATIVE,
            effect_id="crack_of_doom",
            effect_text=":tiebreaker_blue: : Target a unit adjacent to you.\n:tiebreaker_orange: : Target a unit at maximum range.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="abrupt_combustion",
            name="Abrupt Combustion",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            radius_value=3,
            effect_id="abrupt_combustion",
            effect_text=":tiebreaker_blue: : An enemy hero in radius adjacent to a token or to a minion discards a card, if able.\n:tiebreaker_orange: : Remove an enemy minion in radius adjacent to an enemy hero.",
        ),
        Card(
            id="path_of_ashes",
            name="Path of Ashes",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="path_of_ashes",
            effect_text=":tiebreaker_blue: : Move up to 2 spaces in a straight line. Place a :magma_token: Magma token in each empty space you moved through, or out of.\n:tiebreaker_orange: : Place up to 2 Magma tokens in radius.",
        ),
        Card(
            id="playing_with_fire",
            name="Playing with Fire",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=2,
            effect_id="playing_with_fire",
            effect_text=":tiebreaker_blue: : Target a unit in range not in a straight line.\n:tiebreaker_orange: : Target a unit in range in a straight line.",
        ),
        Card(
            id="equilibrium",
            name="Equilibrium",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=1,
            primary_action=ActionType.SKILL,  # Labeled Basic Skill on frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7},
            effect_id="equilibrium",
            effect_text="This round: Each time you perform or repeat a primary action, you may apply either :tiebreaker_blue: or :tiebreaker_orange: card text, regardless of the Tie Breaker coin.",
        ),
        Card(
            id="chaos_bolt",
            name="Chaos Bolt",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,  # Labeled Basic Attack - Ranged on frame
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=3,
            effect_id="chaos_bolt",
            effect_text=":tiebreaker_blue: : Target a minion adjacent to you.\n:tiebreaker_orange: : Target a hero in range.\n( Apply the text matching the symbol on the Tie Breaker coin. )",
        ),
    ]

    h = Hero(
        id=HeroID("hero_ignatia"),
        name="Ignatia",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_ignatia())
