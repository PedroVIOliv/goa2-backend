from goa2.domain.models import Hero, Card, CardTier, CardColor, ActionType, StatType
from goa2.domain.types import HeroID
from .registry import HeroRegistry

def create_arien() -> Hero:
    """
    Arien
    """
    name = "Arien"
    title = "The Tidemaster"
    deck = [
    # =========================================================================
    # TIER IV (Ultimate)
    # =========================================================================
    Card(
        id="living_tsunami",
        name="Living Tsunami",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0, 
        primary_action=ActionType.SKILL,
        primary_action_value=None, # Ultimates often lack a standard value
        secondary_actions={},
        effect_id="effect_ultimate_move_before_attack",
        effect_text="Once per turn, before performing an Attack action, you may move 1 space."
    ),

    # =========================================================================
    # TIER III
    # =========================================================================
    Card(
        id="ebb_and_flow",
        name="Ebb and Flow",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        secondary_actions={
            ActionType.DEFENSE: 4,
            ActionType.MOVEMENT: 2
        },
        is_ranged=True,
        range_value=4,
        item=StatType.DEFENSE,
        effect_id="effect_swap_enemy_minion_repeat",
        effect_text="Swap with an enemy minion in range; if it was adjacent to you, may repeat once."
    ),
    Card(
        id="stranger_tide",
        name="Stranger Tide",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        primary_action_value=3,
        secondary_actions={
            ActionType.DEFENSE: 4,
            ActionType.MOVEMENT: 2
        },
        is_ranged=True,
        range_value=3,
        item=StatType.RADIUS,
        effect_id="effect_teleport_no_spawn",
        effect_text="Place yourself into a space in range without a spawn point."
    ),
    Card(
        id="deluge",
        name="Deluge",
        tier=CardTier.III,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        secondary_actions={
            ActionType.DEFENSE: 6
            # Corrected: Removed Attack from secondary actions
        },
        radius_value=1,
        item=StatType.ATTACK,
        effect_id="effect_slow_radius",
        effect_text="This turn: Enemy heroes in radius cannot fast travel, or move more than 1 space with a movement action."
    ),
    Card(
        id="master_duelist",
        name="Master Duelist",
        tier=CardTier.III,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.DEFENSE,
        primary_action_value=6,
        secondary_actions={
            ActionType.MOVEMENT: 3 # Corrected from Defense to Movement
        },
        item=StatType.RANGE,
        effect_id="effect_ignore_minion_defense_immune_others",
        effect_text="Ignore all minion defense modifiers. This round: You are immune to attack actions of all enemy heroes, except this attacker."
    ),
    Card(
        id="violent_torrent",
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        secondary_actions={
            ActionType.DEFENSE: 7,
            ActionType.MOVEMENT: 4
        },
        item=StatType.INITIATIVE,
        effect_id="effect_attack_discard_behind_repeat",
        effect_text="Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 5 spaces in a straight line directly behind the target discards a card, or is defeated. May repeat once on a different unit."
    ),
    Card(
        id="tidal_blast",
        name="Tidal Blast",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={
            ActionType.DEFENSE: 4,
            ActionType.MOVEMENT: 4
        },
        is_ranged=True,
        range_value=2,
        item=StatType.MOVEMENT,
        effect_id="effect_push_adjacent",
        effect_text="Target a unit in range. After the attack: You may push an enemy unit adjacent to you up to 3 spaces."
    ),

    # =========================================================================
    # TIER II
    # =========================================================================
    Card(
        id="arcane_whirlpool",
        name="Arcane Whirlpool",
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        primary_action_value=4,
        secondary_actions={
            ActionType.DEFENSE: 3,
            ActionType.MOVEMENT: 2
        },
        is_ranged=True,
        range_value=4,
        item=StatType.DEFENSE,
        effect_id="effect_swap_enemy_minion",
        effect_text="Swap with an enemy minion in range."
    ),
    Card(
        id="magical_current",
        name="Magical Current",
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        primary_action_value=3,
        secondary_actions={
            ActionType.DEFENSE: 3,
            ActionType.MOVEMENT: 2
        },
        is_ranged=True,
        range_value=3,
        item=StatType.ATTACK,
        effect_id="effect_teleport_no_spawn_no_adj",
        effect_text="Place yourself into a space in range without a spawn point and not adjacent to an empty spawn point."
    ),
    Card(
        id="expert_duelist",
        name="Expert Duelist",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.DEFENSE,
        primary_action_value=6,
        secondary_actions={
            ActionType.MOVEMENT: 3 # Corrected from Defense to Movement
        },
        item=StatType.INITIATIVE,
        effect_id="effect_ignore_minion_defense_immune_others_turn",
        effect_text="Ignore all minion defense modifiers. This turn: You are immune to attack actions of all enemy heroes, except this attacker."
    ),
    Card(
        id="slippery_ground",
        name="Slippery Ground",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        secondary_actions={
            ActionType.DEFENSE: 6
        },
        item=StatType.ATTACK,
        effect_id="effect_slow_adjacent",
        effect_text="This turn: Enemy heroes adjacent to you cannot fast travel, or move more than 1 space with a movement action."
    ),
    Card(
        id="rogue_wave",
        name="Rogue Wave",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={
            ActionType.DEFENSE: 4,
            ActionType.MOVEMENT: 4
        },
        is_ranged=True,
        range_value=2,
        item=StatType.DEFENSE,
        effect_id="effect_push_adjacent_lesser",
        effect_text="Target a unit in range. After the attack: You may push an enemy unit adjacent to you up to 2 spaces."
    ),
    Card(
        id="raging_stream",
        name="Raging Stream",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        secondary_actions={
            ActionType.DEFENSE: 7,
            ActionType.MOVEMENT: 4
        },
        item=StatType.INITIATIVE,
        effect_id="effect_attack_discard_behind_lesser",
        effect_text="Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 3 spaces in a straight line directly behind the target discards a card, or is defeated."
    ),

    # =========================================================================
    # UNTIERED / TIER I
    # =========================================================================
    Card(
        id="spell_break",
        name="Spell Break",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=13,
        primary_action=ActionType.SKILL,
        primary_action_value=3,
        secondary_actions={
            ActionType.DEFENSE: 3
        },
        radius_value=3,
        effect_id="effect_silence_heroes_radius",
        effect_text="This turn: Enemy heroes in radius cannot perform skill actions, except on gold cards."
    ),
    Card(
        id="noble_blade",
        name="Noble Blade",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=11,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={
            ActionType.DEFENSE: 2,
            ActionType.MOVEMENT: 1
        },
        effect_id="effect_attack_move_ally",
        effect_text="Target a unit adjacent to you. Before the attack: You may move another unit that is adjacent to the target 1 space."
    ),
    Card(
        id="aspiring_duelist",
        name="Aspiring Duelist",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=9,
        primary_action=ActionType.DEFENSE,
        primary_action_value=5,
        secondary_actions={
            ActionType.MOVEMENT: 3
        },
        effect_id="effect_ignore_minion_defense",
        effect_text="Ignore all minion defense modifiers."
    ),
    Card(
        id="dangerous_current",
        name="Dangerous Current",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=6,
        secondary_actions={
            ActionType.DEFENSE: 6,
            ActionType.MOVEMENT: 4
        },
        effect_id="effect_attack_discard_behind",
        effect_text="Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 2 spaces in a straight line directly behind the target discards a card, or is defeated."
    ),
    Card(
        id="liquid_leap",
        name="Liquid Leap",
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        primary_action_value=2,
        secondary_actions={
            ActionType.DEFENSE: 3,
            ActionType.MOVEMENT: 2
        },
        is_ranged=True,
        range_value=2,
        effect_id="effect_teleport_strict",
        effect_text="Place yourself into a space in range without a spawn point and not adjacent to an empty spawn point."
    )
    ]
    
    h = Hero(
        id=HeroID("hero_arien"),
        name="Arien",
        deck=deck,
        hand=[],
        items={} 
    )
    return h

HeroRegistry.register(create_arien())
