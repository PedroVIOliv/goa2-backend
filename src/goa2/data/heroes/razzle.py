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


def create_razzle() -> Hero:
    """
    Razzle
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="twin_strike",
        name="Twin Strike",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="twin_strike",
        effect_text="After you perform a basic attack action, another one of you may repeat it once, targeting a different unit.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="team_spirit",
            name="Team Spirit",
            image_id="BlueIIIA",  # Evolution of Alleyoop -> Group Performance
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=4,
            item=StatType.RADIUS,
            effect_id="team_spirit",
            effect_text="Swap with a friendly hero in range.\nMove another one of you up to 3 spaces.",
        ),
        Card(
            id="aaaand_its_gone",
            name="Aaaand It's Gone!",
            image_id="BlueIIIB",  # Evolution of Magic Trick
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            item=StatType.DEFENSE,
            effect_id="aaaand_its_gone",
            effect_text="Push a unit adjacent to you up to 3 spaces; for every space the target moved, move this one of you one space in the opposite direction.",
        ),
        Card(
            id="wire_dancers",
            name="Wire Dancers",
            image_id="GreenIIIA",  # Evolution of Tightrope -> High Wire
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=1,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 2},
            item=StatType.INITIATIVE,
            effect_id="wire_dancers",
            effect_text="After you move, move another one of you up to 3 spaces.",
        ),
        Card(
            id="spectacle",
            name="Spectacle",
            image_id="GreenIIIB",  # Evolution of Theatrics
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=2,
            item=StatType.ATTACK,
            effect_id="spectacle",
            effect_text="Swap with a minion in range.\nMay repeat once by another one of you, targeting a different minion.",
        ),
        Card(
            id="into_thin_air",
            name="Into Thin Air",
            image_id="RedIIIA",  # Evolution of Phantom Strike -> Hit and Gone
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            item=StatType.RANGE,
            effect_id="into_thin_air",
            effect_text="Target a unit adjacent to you.\nAfter the attack: You may remove one or more of you in play, including all of you.\n( If all are removed, you are not defeated. Respawn as normal. )",
        ),
        Card(
            id="ransack",
            name="Ransack",
            image_id="RedIIIB",  # Evolution of Rummage
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=10,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            radius_value=3,
            item=StatType.MOVEMENT,
            effect_id="ransack",
            effect_text="Target a unit adjacent to you.\nAfter the attack: For each other one of you in radius, you may retrieve a discarded card.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="group_performance",
            name="Group Performance",
            image_id="BlueIIA",  # Evolution of Alleyoop
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="group_performance",
            effect_text="Swap with a friendly hero in range.\nMove another one of you up to 2 spaces.",
        ),
        Card(
            id="magic_trick",
            name="Magic Trick",
            image_id="BlueIIB",  # Combat Disengage Path Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=11,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
            item=StatType.DEFENSE,
            effect_id="magic_trick",
            effect_text="Push a unit adjacent to you up to 2 spaces; for every space the target moved, move this one of you one space in the opposite direction.",
        ),
        Card(
            id="high_wire",
            name="High Wire",
            image_id="GreenIIA",  # Evolution of Tightrope
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 2},
            item=StatType.INITIATIVE,
            effect_id="high_wire",
            effect_text="After you move, move another one of you up to 2 spaces.",
        ),
        Card(
            id="theatrics",
            name="Theatrics",
            image_id="GreenIIB",  # Transposition Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=2,
            item=StatType.ATTACK,
            effect_id="theatrics",
            effect_text="Swap with a minion in range.",
        ),
        Card(
            id="hit_and_gone",
            name="Hit and Gone",
            image_id="RedIIA",  # Evolution of Phantom Strike
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            item=StatType.DEFENSE,
            effect_id="hit_and_gone",
            effect_text="Target a unit adjacent to you. After the attack:\nYou may remove one or more of you in play, except the last one of you.",
        ),
        Card(
            id="rummage",
            name="Rummage",
            image_id="RedIIB",  # Recycling Interaction Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
            radius_value=3,
            item=StatType.INITIATIVE,
            effect_id="rummage",
            effect_text="Target a unit adjacent to you.\nAfter the attack: If there is another one of you in radius, you may retrieve a discarded card.\n( All of you share cards in hand, deck, and discard. )",
        ),
        # =========================================================================
        # TIER I
        # =========================================================================
        Card(
            id="alleyoop",
            name="Alleyoop",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=3,
            effect_id="alleyoop",
            effect_text="Swap with a friendly hero in range.\nMove another one of you up to 1 space.",
        ),
        Card(
            id="tightrope",
            name="Tightrope",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=2,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 1},
            effect_id="tightrope",
            effect_text="After you move, you may move another one of you 1 space.",
        ),
        Card(
            id="phantom_strike",
            name="Phantom Strike",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=9,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 4},
            effect_id="phantom_strike",
            effect_text="Target a unit adjacent to you. After the attack:\nIf there is more than one of you in play, you may remove one of you.",
        ),
        Card(
            id="crowd_control",
            name="Crowd Control",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=13,
            primary_action=ActionType.DEFENSE_SKILL,  # Hybrid Frame: labeled Basic Defense/Skill
            primary_action_value=1,
            secondary_actions={},
            radius_value=3,
            effect_id="crowd_control",
            effect_text="When used as a defense action, +2 :defense: Defense for each other one of you in radius.\nWhen used as a skill action, remove all other you in play.",
        ),
        Card(
            id="stunt_doubles",
            name="Stunt Doubles",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=13,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 1},
            radius_value=1,
            effect_id="stunt_doubles",
            effect_text="Target a unit adjacent to you. After the attack:\nSpawn up to 3 more of you in radius; each of you is the same hero, except when actions are performed. If defeated, remove all of you.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_razzle"),
        name="Razzle",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
        piece_supply=4,
    )
    return h


HeroRegistry.register(create_razzle())
