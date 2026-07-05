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


def create_emmitt() -> Hero:
    """
    Emmitt
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="alternative_timelines",
        name="Alternative Timelines",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="alternative_timelines",
        effect_text="You may play two cards each turn; if you do, after the cards are revealed, retrieve one of your unresolved cards.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="time_warp",
            name="Time Warp",
            image_id="BlueIIIB",
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.RADIUS,
            effect_id="time_warp",
            effect_text="Choose one —\n• Swap with an enemy hero in range who has already resolved a card this turn.\n• An enemy hero in range swaps their unresolved card with one of their resolved cards of their choice.",
        ),
        Card(
            id="time_bomb",
            name="Time Bomb",
            image_id="BlueIIIA",  # Evolution of Time Trap
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            item=StatType.MOVEMENT,
            effect_id="time_bomb",
            effect_text="An enemy hero in range who has already resolved a card this turn discards a card, or is defeated.",
        ),
        Card(
            id="back_to_the_future",
            name="Back to the Future",
            image_id="GreenIIIA",  # Evolution of Time Walk -> Fast Forward
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="back_to_the_future",
            effect_text="Choose one —\n• Place a unit in range into the space where that unit was at the start of this turn.\n• Move an enemy hero in range, who remained in the same space since the last turn, 2 spaces in a straight line.",
        ),
        Card(
            id="future_proof",
            name="Future Proof",
            image_id="GreenIIIB",  # Evolution of Time Capsule
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="future_proof",
            effect_text="Choose one —\n• You, and friendly heroes in radius, may retrieve all cards discarded this turn.\n• This turn: Friendly heroes in radius are immune to enemy actions.",
        ),
        Card(
            id="temporal_judgment",
            name="Temporal Judgment",
            image_id="RedIIIA",  # Evolution of Temporal Punch -> Temporal Slam
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=12,
            secondary_actions={ActionType.DEFENSE: 8, ActionType.MOVEMENT: 3},
            item=StatType.RANGE,
            effect_id="temporal_judgment",
            effect_text="Target a unit adjacent to you; when defending, the enemy hero must use the :initiative: Initiative value of their card and items instead of the :defense: Defense value of their card and items.",
        ),
        Card(
            id="deja_vu",
            name="Déjà Vu",
            image_id="RedIIIB",  # Evolution of Flashback
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.DEFENSE,
            effect_id="deja_vu",
            effect_text="Target a unit adjacent to you. After the attack: You may place 2 :glitch_token: Glitch tokens in radius, with at least two spaces between each token; if you do, up to 1 enemy hero in radius swaps with a Glitch token of their choice.\nEnd of turn: Remove all Glitch tokens.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="time_loop",
            name="Time Loop",
            image_id="BlueIIB",
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="time_loop",
            effect_text="Swap with an enemy hero in range who has already resolved a card this turn.",
        ),
        Card(
            id="time_trap",
            name="Time Trap",
            image_id="BlueIIA",
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            item=StatType.DEFENSE,
            effect_id="time_trap",
            effect_text="An enemy hero in range who has already resolved a card this turn discards a card, if able.",
        ),
        Card(
            id="fast_forward",
            name="Fast Forward",
            image_id="GreenIIA",  # Evolution of Time Walk
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=4,
            item=StatType.ATTACK,
            effect_id="fast_forward",
            effect_text="Move an enemy hero in range, who remained in the same space since the last turn, 2 spaces in a straight line.",
        ),
        Card(
            id="time_capsule",
            name="Time Capsule",
            image_id="GreenIIB",  # Resource Recovery Path Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            radius_value=4,
            item=StatType.INITIATIVE,
            effect_id="time_capsule",
            effect_text="You, and friendly heroes in radius, may retrieve all cards discarded this turn.",
        ),
        Card(
            id="temporal_slam",
            name="Temporal Slam",
            image_id="RedIIA",  # Evolution of Temporal Punch
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=11,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.INITIATIVE,
            effect_id="temporal_slam",
            effect_text="Target a unit adjacent to you; when defending, the enemy hero must use the :initiative: Initiative value of their card and items instead of the :defense: Defense value of their card and items.",
        ),
        Card(
            id="flashback",
            name="Flashback",
            image_id="RedIIB",  # Glitch Board Disruption Path Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=3,
            item=StatType.DEFENSE,
            effect_id="flashback",
            effect_text="Target a unit adjacent to you. After the attack: You may place 3 :glitch_token: Glitch tokens in radius, with at least two spaces between each token; if you do, up to 1 enemy hero in radius swaps with a Glitch token of their choice.\nEnd of turn: Remove all Glitch tokens.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="time_snare",
            name="Time Snare",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=2,
            effect_id="time_snare",
            effect_text="An enemy hero in range who has already resolved a card this turn discards a card, if able.",
        ),
        Card(
            id="time_walk",
            name="Time Walk",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=6,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            is_ranged=True,
            range_value=3,
            effect_id="time_walk",
            effect_text="Move an enemy hero in range, who remained in the same space since the last turn, 2 spaces in a straight line.",
        ),
        Card(
            id="temporal_punch",
            name="Temporal Punch",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=9,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            effect_id="temporal_punch",
            effect_text="Target a unit adjacent to you; when defending, the enemy hero must use the :initiative: Initiative value of their card and items instead of the :defense: Defense value of their card and items.\n( Minion defense modifiers are applied as normal. )",
        ),
        Card(
            id="unstable_timeline",
            name="Unstable Timeline",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=1,
            primary_action=ActionType.DEFENSE_SKILL,  # Hybrid frame: Basic Defense / Skill
            primary_action_value=6,
            secondary_actions={},
            radius_value=4,
            effect_id="unstable_timeline",
            effect_text="Place 2 :glitch_token: Glitch tokens in radius, with at least two spaces between each token; if used as a defense, place 3 tokens instead.\nAn enemy hero in play chooses one of the Glitch tokens; you swap with that token.\nEnd of turn: Remove all Glitch tokens.",
        ),
        Card(
            id="reverse_time",
            name="Reverse Time",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,  # Basic Attack Frame
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            effect_id="reverse_time",
            effect_text="Target a unit adjacent to you. After the attack:\nNext turn: Heroes with lower initiative act before heroes with higher initiative; this effect ignores immunity.\n( Resolve ties as normal. )",
        ),
    ]

    h = Hero(
        id=HeroID("hero_emmitt"),
        name="Emmitt",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_emmitt())
