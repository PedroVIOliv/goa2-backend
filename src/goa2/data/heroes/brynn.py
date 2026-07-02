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


def create_brynn() -> Hero:
    """
    Brynn
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="over the top",
        name="Over the Top",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="over_the_top",
        effect_text="While you are performing actions, all enemy heroes in play count as being adjacent to 3 or more obstacles.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="hide_traces",
            name="Hide Traces",
            image_id="BlueIIIA",  # Evolution of Tread Lightly -> Cover Tracks
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.RANGE,
            effect_id="hide_traces",
            effect_text="Swap with either a unit adjacent to you, or with an enemy hero in radius who is adjacent to 3 or more obstacles.\nMove up to 2 spaces.",
        ),
        Card(
            id="expedition_leader",
            name="Expedition Leader",
            image_id="BlueIIIB",  # Evolution of Mountain Guide
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="expedition_leader",
            effect_text="You may move a friendly unit, which is adjacent to you, up to 3 spaces. If an enemy hero in radius is adjacent to 3 or more obstacles, move a different friendly unit in radius up to 3 spaces.",
        ),
        Card(
            id="deadfall_trap",
            name="Deadfall Trap",
            image_id="GreenIIIA",  # Evolution of Bear Trap -> Log Trap
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="deadfall_trap",
            effect_text="Choose one —\n• An enemy hero adjacent to you discards a card, or is defeated.\n• An enemy hero in radius who is adjacent to 3 or more obstacles discards a card, or is defeated.",
        ),
        Card(
            id="die_hard",
            name="Die Hard",
            image_id="GreenIIIB",  # Evolution of True Grit
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.MOVEMENT,
            effect_id="die_hard",
            effect_text="You may retrieve a discarded attack card. If an enemy hero in radius is adjacent to 3 or more obstacles, move up to 4 spaces.",
        ),
        Card(
            id="peak_precision",
            name="Peak Precision",
            image_id="RedIIIA",  # Evolution of High Ground -> Elevated Ambush
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 4},
            item=StatType.RADIUS,
            effect_id="peak_precision",
            effect_text="Target a unit adjacent to you. If you target a hero adjacent to 3 or more obstacles, +2 :attack: attack and After the attack: You may retrieve this card.",
        ),
        Card(
            id="split_throw",
            name="Split Throw",
            image_id="RedIIIB",  # Evolution of Split Attack
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=2,
            item=StatType.DEFENSE,
            effect_id="split_throw",
            effect_text="Target a unit in range. If you target a hero who is adjacent to 3 or more obstacles, may repeat once on a different unit.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="cover_tracks",
            name="Cover Tracks",
            image_id="BlueIIA",  # Evolution of Tread Lightly
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.DEFENSE,
            effect_id="cover_tracks",
            effect_text="Swap with either a unit adjacent to you, or with an enemy hero in radius who is adjacent to 3 or more obstacles.\nYou may move 1 space.",
        ),
        Card(
            id="mountain_guide",
            name="Mountain Guide",
            image_id="BlueIIB",  # Relocation Support Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="mountain_guide",
            effect_text="You may move a friendly unit, which is adjacent to you, up to 2 spaces. If an enemy hero in radius is adjacent to 3 or more obstacles, move a different friendly unit in radius up to 2 spaces.",
        ),
        Card(
            id="log_trap",
            name="Log Trap",
            image_id="GreenIIA",  # Evolution of Bear Trap
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="log_trap",
            effect_text="Choose one —\n• An enemy hero adjacent to you discards a card, if able.\n• An enemy hero in radius who is adjacent to 3 or more obstacles discards a card, if able.",
        ),
        Card(
            id="true_grit",
            name="True Grit",
            image_id="GreenIIB",  # Card Recovery Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.ATTACK,
            effect_id="true_grit",
            effect_text="You may retrieve a discarded attack card. If an enemy hero in radius is adjacent to 3 or more obstacles, move up to 3 spaces.",
        ),
        Card(
            id="elevated_ambush",
            name="Elevated Ambush",
            image_id="RedIIA",  # Evolution of High Ground
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            item=StatType.INITIATIVE,
            effect_id="elevated_ambush",
            effect_text="Target a unit adjacent to you. If you target a hero adjacent to 3 or more obstacles, +2 :attack: attack.",
        ),
        Card(
            id="split_attack",
            name="Split Attack",
            image_id="RedIIB",  # Ranged Ramping Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 4},
            is_ranged=True,
            range_value=2,
            item=StatType.DEFENSE,
            effect_id="split_attack",
            effect_text="Target a unit in range. If you target a hero who is adjacent to 3 or more obstacles, may repeat once on a different unit adjacent to you.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="tread_lightly",
            name="Tread Lightly",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
            radius_value=2,
            effect_id="tread_lightly",
            effect_text="Swap with either a unit adjacent to you, or with an enemy hero in radius who is adjacent to 3 or more obstacles.",
        ),
        Card(
            id="bear_trap",
            name="Bear Trap",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=3,
            effect_id="bear_trap",
            effect_text="Choose one —\n• An enemy hero adjacent to you discards a card, if able.\n• An enemy hero in radius who is adjacent to 3 or more obstacles discards a card, if able.",
        ),
        Card(
            id="brynn_high_ground",
            name="High Ground",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 4},
            effect_id="brynn_high_ground",
            effect_text="Target a unit adjacent to you. If you target a hero adjacent to 3 or more obstacles, +2 :attack: attack.",
        ),
        Card(
            id="decoy",
            name="Decoy",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=1,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2},
            radius_value=4,
            effect_id="decoy",
            effect_text="Choose up to two times, on different targets —\n• Move an enemy minion in radius 1 space.\n• Move an enemy hero in radius who is adjacent to 3 or more obstacles 1 space.",
        ),
        Card(
            id="familiar_ground",
            name="Familiar Ground",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=12,
            primary_action=ActionType.ATTACK,  # Basic Attack - Ranged Frame
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=3,
            effect_id="familiar_ground",
            effect_text="Choose one —\n• Target a unit adjacent to you.\n• Target a hero in range who is adjacent to 3 or more obstacles.\n( You, other heroes, minions, tokens, and terrain are obstacles. )",
        ),
    ]

    h = Hero(
        id=HeroID("hero_brynn"),
        name="Brynn",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_brynn())
