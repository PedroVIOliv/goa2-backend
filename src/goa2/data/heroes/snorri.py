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


def create_snorri() -> Hero:
    """
    Snorri
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="rune_mastery",
        name="Rune Mastery",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="rune_mastery",
        effect_text="Each time you perform an action, choose one inactive rune; that rune counts as a second active rune for this action.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="runeblaster",
            name="Runeblaster",
            image_id="RedIIIB",  # Evolution of Runecaster
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=3,
            item=StatType.MOVEMENT,
            effect_id="runeblaster",
            effect_text="If the :rune_bird: rune is active, target a unit in range, otherwise target a unit at maximum range.\nAfter the attack: If a rune is active:\n• :rune_horn: : Move up to 2 spaces.\n• :rune_axe: : An enemy hero who was adjacent to the target discards a card, or is defeated.",
        ),
        Card(
            id="runic_battleaxe",
            name="Runic Battleaxe",
            image_id="RedIIIA",  # Evolution of Runic Dagger -> Runic Hammer
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.ATTACK,
            primary_action_value=6,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.RADIUS,
            effect_id="runic_battleaxe",
            effect_text="Before the attack: If the :rune_horn: rune is active, you may move 1 space.\nTarget a unit adjacent to you.\nAfter the attack: If a rune is active:\n• :rune_axe: : May repeat once on an enemy minion.\n• :rune_anvil: : You may retrieve a discarded card.",
        ),
        Card(
            id="runebomb",
            name="Runebomb",
            image_id="GreenIIIB",  # Evolution of Runetrap
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="runebomb",
            effect_text="Choose one active rune; depending on that rune, an enemy hero in radius:\n• :rune_horn: : Discards a green card, if able.\n• :rune_axe: : Discards a silver card, if able.\n• :rune_anvil: : Discards a blue card, if able.\n• :rune_bird: : Discards a gold card, if able.",
        ),
        Card(
            id="oath_of_perseverance",
            name="Oath of Perseverance",
            image_id="GreenIIIA",  # Evolution of Oath of Endurance -> Oath of Fortitude
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.DEFENSE,
            primary_action_value=None,
            secondary_actions={ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="oath_of_perseverance",
            effect_text="Choose one active rune:\n• :rune_horn: : Block a basic attack;\n• :rune_axe: : Block a non-ranged attack;\n• :rune_bird: : Block a ranged attack;\n• :rune_anvil: : Block a non-basic attack.\nThis Turn: You are immune to enemy actions.",
        ),
        Card(
            id="ancestral_grace",
            name="Ancestral Grace",
            image_id="BlueIIIB",  # Evolution of Ancestral Boon
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="ancestral_grace",
            effect_text="If a rune is active, a friendly hero in radius may:\n• :rune_axe: : Swap a resolved card with a card in hand.\n• :rune_anvil: : Retrieve all their discarded cards.\n• :rune_bird: : Swap one of their items with an item on their card of the same tier and color.",
        ),
        Card(
            id="deep_passage",
            name="Deep Passage",
            image_id="BlueIIIA",  # Evolution of Safe Passage -> Hidden Passage
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 6},
            item=StatType.RANGE,
            effect_id="deep_passage",
            effect_text="If a rune is active:\n• :rune_bird: : This turn: You may ignore obstacles.\n• :rune_anvil: : This turn: You are immune to enemy actions.\n• :rune_horn: : Gain +2 :movement: Movement.",
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="runecaster",
            name="Runecaster",
            image_id="RedIIB",  # Ranged Sniper Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            is_ranged=True,
            range_value=3,
            item=StatType.DEFENSE,
            effect_id="runecaster",
            effect_text="Target a unit at maximum range.\nAfter the attack: If a rune is active:\n• :rune_horn: : Move up to 2 spaces.\n• :rune_axe: : An enemy hero who was adjacent to the target discards a card, or is defeated.",
        ),
        Card(
            id="runic_hammer",
            name="Runic Hammer",
            image_id="RedIIA",  # Evolution of Runic Dagger
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.INITIATIVE,
            effect_id="runic_hammer",
            effect_text="Before the attack: If the :rune_horn: rune is active, you may move 1 space.\nTarget a unit adjacent to you.\nAfter the attack: If the :rune_anvil: rune is active, you may retrieve a discarded card.",
        ),
        Card(
            id="runetrap",
            name="Runetrap",
            image_id="GreenIIB",  # Discard Injection Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            radius_value=3,
            item=StatType.ATTACK,
            effect_id="runetrap",
            effect_text="If a rune is active, an enemy hero in radius:\n• :rune_horn: : Discards a green card, if able.\n• :rune_axe: : Discards a silver card, if able.\n• :rune_anvil: : Discards a blue card, if able.",
        ),
        Card(
            id="oath_of_fortitude",
            name="Oath of Fortitude",
            image_id="GreenIIA",  # Evolution of Oath of Endurance
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.DEFENSE,
            primary_action_value=None,
            secondary_actions={ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="oath_of_fortitude",
            effect_text="If a rune is active:\n• :rune_horn: : Block a basic attack;\n• :rune_axe: : Block a non-ranged attack;\n• :rune_bird: : Block a ranged attack.\nThis Turn: You are immune to enemy actions.",
        ),
        Card(
            id="ancestral_boon",
            name="Ancestral Boon",
            image_id="BlueIIB",  # Support Resource Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            radius_value=4,
            item=StatType.DEFENSE,
            effect_id="ancestral_boon",
            effect_text="If a rune is active, a friendly hero in radius may:\n• :rune_axe: : Swap a resolved card with a card in hand.\n• :rune_anvil: : Retrieve all their discarded cards.",
        ),
        Card(
            id="hidden_passage",
            name="Hidden Passage",
            image_id="BlueIIA",  # Evolution of Safe Passage
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 6},
            item=StatType.ATTACK,
            effect_id="hidden_passage",
            effect_text="If a rune is active:\n• :rune_bird: : This turn: You may ignore obstacles.\n• :rune_anvil: : This turn: You are immune to enemy actions.",
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="runic_dagger",
            name="Runic Dagger",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            effect_id="runic_dagger",
            effect_text="Target a unit adjacent to you.\nAfter the attack: If the :rune_anvil: rune is active, you may retrieve a discarded card.",
        ),
        Card(
            id="oath_of_endurance",
            name="Oath of Endurance",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.DEFENSE,
            primary_action_value=None,
            secondary_actions={ActionType.MOVEMENT: 2},
            effect_id="oath_of_endurance",
            effect_text="If a rune is active:\n• :rune_horn: : Block a basic attack.\n• :rune_axe: : Block a non-ranged attack.\nThis Turn: You are immune to enemy actions.",
        ),
        Card(
            id="safe_passage",
            name="Safe Passage",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=3,
            secondary_actions={ActionType.DEFENSE: 5},
            effect_id="safe_passage",
            effect_text="If the :rune_bird: rune is active, This turn: You may ignore obstacles.",
        ),
        Card(
            id="inscribe_the_runes",
            name="Inscribe the Runes",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3},
            effect_id="inscribe_the_runes",
            effect_text="Give yourself 4 :rune_axe_marker: :rune_bird_marker: :rune_anvil_marker: :rune_horn_marker: Rune markers and place one below each of your turn slots.\nA rune is active as long as it is below the turn slot matching the current turn.\nRune markers are not removed at the end of round, nor if you are defeated.",
        ),
        Card(
            id="rune_sigils",
            name="Rune Sigils",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=11,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 1},
            is_ranged=True,
            range_value=2,
            effect_id="rune_sigils",
            effect_text="Target a unit adjacent to you; if a rune is active:\n• :rune_bird: : You may target a minion in range instead.\n• :rune_axe: : +3 :attack: Attack.\n• :rune_anvil: : If you target a hero, gain 3 coins.\n• :rune_horn: : Repeat once on a different hero in range.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_snorri"),
        name="Snorri",
        deck=deck,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_snorri())
