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


def create_swift() -> Hero:
    """
    Swift
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="bullet_time",
        name="Bullet Time",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="bullet_time",
        effect_text="After you resolve a basic card, you may perform the primary action on that card; you cannot target the same enemy hero twice in the same turn this way.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="drop_trooper",
            name="Drop Trooper",
            image_id="BlueIIIA",  # Evolution of Steam Jump -> Assault Jump
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="drop_trooper",
            effect_text="Place yourself into a space in a straight line in radius. Push up to two enemy units adjacent to you up to 2 spaces.",
        ),
        Card(
            id="mobile_scout",
            name="Mobile Scout",
            image_id="BlueIIIB",  # Evolution of Delayed Jump
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 1},
            radius_value=2,
            item=StatType.MOVEMENT,
            effect_id="mobile_scout",
            effect_text="End of turn: Place yourself into a space in radius not in a straight line from you. You may then fast travel, if able.",
        ),
        Card(
            id="killing_ground",
            name="Killing Ground",
            image_id="GreenIIIA",  # Evolution of Suppress -> Pin Down
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.RANGE,
            effect_id="killing_ground",
            effect_text="An enemy hero in radius who is not adjacent to terrain discards a card, or is defeated.",
        ),
        Card(
            id="hunting_season",
            name="Hunting Season",
            image_id="GreenIIIB",  # Evolution of Mark for Death
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="hunting_season",
            effect_text="Move up to two enemy minions in radius, up to 3 spaces each, to spaces in radius.\nNext turn: The first two times an enemy minion in radius is defeated, gain 1 coin.",
        ),
        Card(
            id="killshot",
            name="Killshot",
            image_id="RedIIIA",  # Evolution of Snipe -> Prepared Shot
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=5,
            item=StatType.DEFENSE,
            effect_id="killshot",
            effect_text="Target a unit in range, in a straight line, and not adjacent to you.",
        ),
        Card(
            id="super_shotgun",
            name="Super-Shotgun",
            image_id="RedIIIB",  # Evolution of Shotgun
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=2,
            item=StatType.RADIUS,
            effect_id="super_shotgun",
            effect_text="Target a unit in range. Before the attack: An enemy hero adjacent to the target discards a card, or is defeated.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="assault_jump",
            name="Assault Jump",
            image_id="BlueIIA",  # Evolution of Steam Jump
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="assault_jump",
            effect_text="Place yourself into a space in a straight line in radius. Push an enemy unit adjacent to you up to 2 spaces.",
        ),
        Card(
            id="delayed_jump",
            name="Delayed Jump",
            image_id="BlueIIB",  # Jump Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 1},
            radius_value=2,
            item=StatType.DEFENSE,
            effect_id="delayed_jump",
            effect_text="End of turn: Place yourself into a space in radius not in a straight line from you.",
        ),
        Card(
            id="pin_down",
            name="Pin Down",
            image_id="GreenIIA",  # Evolution of Suppress
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="pin_down",
            effect_text="An enemy hero in radius who is not adjacent to terrain discards a card, if able.",
        ),
        Card(
            id="mark_for_death",
            name="Mark for Death",
            image_id="GreenIIB",  # Mark Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="mark_for_death",
            effect_text="Move an enemy minion in radius up to 3 spaces to a space in radius.\nNext turn: The first time an enemy minion in radius is defeated, gain 1 coin.",
        ),
        Card(
            id="prepared_shot",
            name="Prepared Shot",
            image_id="RedIIA",  # Evolution of Snipe
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=4,
            item=StatType.DEFENSE,
            effect_id="prepared_shot",
            effect_text="Target a unit in range, in a straight line, and not adjacent to you.",
        ),
        Card(
            id="shotgun",
            name="Shotgun",
            image_id="RedIIB",  # Shotgun Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=2,
            item=StatType.INITIATIVE,
            effect_id="shotgun",
            effect_text="Target a unit in range. Before the attack: An enemy hero adjacent to the target discards a card, if able.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="steam_jump",
            name="Steam Jump",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="steam_jump",
            effect_text="Place yourself into a space in a straight line in radius. Push an enemy unit adjacent to you up to 1 space.",
        ),
        Card(
            id="suppress",
            name="Suppress",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="suppress",
            effect_text="An enemy hero in radius who is not adjacent to terrain discards a card, if able.",
        ),
        Card(
            id="snipe",
            name="Snipe",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=4,
            effect_id="snipe",
            effect_text="Target a unit at maximum range, and in a straight line.",
        ),
        Card(
            id="bounce",
            name="Bounce",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=12,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2},
            effect_id="bounce",
            effect_text="Move 2 spaces in a straight line, ignoring obstacles; if this card is already resolved as you perform this action, may repeat once.",
        ),
        Card(
            id="reload",
            name="Reload!",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 1},
            effect_id="reload",
            effect_text="Choose one —\n• Perform the primary action of your rightmost resolved card.\n• Defeat a minion adjacent to you.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_swift"),
        name="Swift",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_swift())
