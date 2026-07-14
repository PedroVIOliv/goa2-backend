from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Hero,
    SpellCard,
    StatType,
)
from goa2.domain.types import HeroID

from .registry import HeroRegistry


def create_gydion() -> Hero:
    """
    Gydion
    """

    # =========================================================================
    # ULTIMATE (Purple/Tier IV) - Stored separately, not in deck
    # =========================================================================
    ultimate = Card(
        id="the_archwizard",
        name="The Archwizard",
        image_id="Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="the_archwizard",
        effect_text='Whenever you would add cards to the spellbook, you may cast the "Wish" spell in the spellbook instead.',
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    spells = [
        # =========================================================================
        # RANK 0 (Cantrips)
        # =========================================================================
        SpellCard.define(
            id="shocking_grasp",
            name="Shocking Grasp",
            image_id="GoldI",
            spell_rank=0,
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_text=(
                "Target a unit adjacent to you. After the attack: " "Move the target up to 1 space."
            ),
        ),
        SpellCard.define(
            id="magic_missile",
            name="Magic Missile",
            image_id="GoldII",
            spell_rank=0,
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            is_ranged=True,
            range_value=3,
            effect_text="Target a unit in range and not adjacent to you.",
        ),
        SpellCard.define(
            id="expeditious_retreat",
            name="Expeditious Retreat",
            image_id="GoldIII",
            spell_rank=0,
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=5,
            effect_text="Move only in a straight line.",
        ),
        # =========================================================================
        # RANK 1 (Tier I Spells)
        # =========================================================================
        SpellCard.define(
            id="burning_hands",
            name="Burning Hands",
            image_id="RedIA",
            spell_rank=1,
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            effect_text=(
                "Target a unit adjacent to you. Before the attack: Up to 1 enemy hero "
                "adjacent to the target discards a card, if able."
            ),
        ),
        SpellCard.define(
            id="suggestion",
            name="Suggestion",
            image_id="BlueIA",
            spell_rank=1,
            tier=CardTier.I,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text="If able, an enemy hero in radius moves 3 spaces in a straight line.",
        ),
        SpellCard.define(
            id="shield",
            name="Shield",
            image_id="GreenIA",
            spell_rank=1,
            tier=CardTier.I,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            effect_text=(
                "This round: You are immune to basic attacks. "
                "(Cancelled if the spell is returned to the spellbook.)"
            ),
        ),
        # =========================================================================
        # RANK 2 (Tier II Spells)
        # =========================================================================
        SpellCard.define(
            id="vampiric_touch",
            name="Vampiric Touch",
            image_id="RedIIB",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            effect_text="Target a unit adjacent to you. After the attack: You may retrieve a discarded card.",
        ),
        SpellCard.define(
            id="fireball",
            name="Fireball",
            image_id="RedIIA",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            is_ranged=True,
            range_value=3,
            effect_text="Target a unit in range, not adjacent to you or to your friendly unit.",
        ),
        SpellCard.define(
            id="create_undead",
            name="Create Undead",
            image_id="RedIIB2",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.RED,
            primary_action=ActionType.SKILL,
            is_ranged=True,
            range_value=3,
            effect_text="Respawn a friendly minion in an empty friendly spawn point in range in the battle zone.",
        ),
        SpellCard.define(
            id="midas_touch",
            name="Midas' Touch",
            image_id="BlueIIB",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            effect_text="Gain 1 coin for every two other spell cards removed from the spellbook.",
        ),
        SpellCard.define(
            id="disintegrate",
            name="Disintegrate",
            image_id="BlueIIB2",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            effect_text="Remove a token or an enemy non-heavy minion adjacent to you.",
        ),
        SpellCard.define(
            id="dominate_person",
            name="Dominate Person",
            image_id="BlueIIA",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text="Target an enemy hero in radius. Defeat an enemy minion in radius adjacent to the target.",
        ),
        SpellCard.define(
            id="find_familiar",
            name="Find Familiar",
            image_id="GreenIIB",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text=(
                "Place a :familiar_token: Familiar token in radius. "
                "You may remove up to three other spell cards from the spellbook faceup."
            ),
        ),
        SpellCard.define(
            id="dimension_door",
            name="Dimension Door",
            image_id="GreenIIB2",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            radius_value=0,
            effect_text=(
                "Place yourself into a space at maximum radius. "
                "+1 Radius for each other spell card removed from the spellbook."
            ),
        ),
        SpellCard.define(
            id="banishment",
            name="Banishment",
            image_id="GreenIIA",
            spell_rank=2,
            tier=CardTier.II,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text="Place a unit or a token adjacent to you into a space in radius.",
        ),
        # =========================================================================
        # RANK 3 (Tier III Spells)
        # =========================================================================
        SpellCard.define(
            id="sunburst",
            name="Sunburst",
            image_id="RedIIIA",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=0,
            is_ranged=True,
            range_value=0,
            effect_text=(
                "Target a unit at maximum range. +1 :attack: Attack and +1 Range "
                "for each other spell card removed from the spellbook."
            ),
        ),
        SpellCard.define(
            id="energy_drain",
            name="Energy Drain",
            image_id="RedIIIB",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.RED,
            primary_action=ActionType.SKILL,
            is_ranged=True,
            range_value=3,
            effect_text=(
                "An enemy hero in range discards a non-basic card, if able. "
                "Your team regains 1 spent :life_counter: Life counter."
            ),
        ),
        SpellCard.define(
            id="cloud_kill",
            name="Cloud Kill",
            image_id="GreenIIIB",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text="An enemy hero in radius discards a basic card, if able.",
        ),
        SpellCard.define(
            id="invulnerability",
            name="Invulnerability",
            image_id="GreenIIIA",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.GREEN,
            primary_action=ActionType.SKILL,
            effect_text="This Round: You are immune to non-basic attacks.",
        ),
        SpellCard.define(
            id="power_word_kill",
            name="Power Word Kill",
            image_id="BlueIIIA",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text="Defeat an enemy hero in radius with no cards in hand.",
        ),
        SpellCard.define(
            id="polymorph",
            name="Polymorph",
            image_id="BlueIIIB",
            spell_rank=3,
            tier=CardTier.III,
            color=CardColor.BLUE,
            primary_action=ActionType.SKILL,
            radius_value=3,
            effect_text=(
                "Swap an enemy hero in radius with a token in radius "
                "or with an enemy minion in radius."
            ),
        ),
        # =========================================================================
        # RANK 4 (Tier IV / Ultimate Spell)
        # =========================================================================
        SpellCard.define(
            id="wish",
            name="Wish",
            image_id="Ultimate",
            spell_rank=4,
            tier=CardTier.IV,
            color=CardColor.PURPLE,
            primary_action=ActionType.SKILL,
            effect_text=(
                "Cast any spell in the Spellbook. After you cast the "
                '"Wish" spell three times your team wins the game.'
            ),
        ),
    ]

    deck = [
        # =========================================================================
        # TIER III
        # =========================================================================
        Card(
            id="greater_evocation",
            name="Greater Evocation",
            image_id="RedIIIA",  # Evolution of Elementary Evocation -> Lesser Evocation
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.DEFENSE,
            effect_id="greater_evocation",
            effect_text='Choose and cast one spell in the spellbook —\n• "Burning Hands"\n• "Fireball"\n• "Sunburst"\n( Sunburst\'s reach and power grows with every cast spell. )',
        ),
        Card(
            id="greater_necromancy",
            name="Greater Necromancy",
            image_id="RedIIIB",  # Evolution of Lesser Necromancy
            tier=CardTier.III,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 7, ActionType.MOVEMENT: 3},
            item=StatType.RADIUS,
            effect_id="greater_necromancy",
            effect_text='Choose and cast one spell in the spellbook —\n• "Vampiric Touch"\n• "Create Undead"\n• "Energy Drain"\n( Drain energy from a foe in sight to restore your vitality. )',
        ),
        Card(
            id="greater_abjuration",
            name="Greater Abjuration",
            image_id="GreenIIIA",  # Evolution of Elementary Abjuration -> Lesser Abjuration
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="greater_abjuration",
            effect_text='Choose and cast one spell in the spellbook —\n• "Shield"\n• "Banishment"\n• "Invulnerability"\n( Invulnerability makes you impervious to deadly perils. )',
        ),
        Card(
            id="greater_conjuration",
            name="Greater Conjuration",
            image_id="GreenIIIB",  # Evolution of Lesser Conjuration
            tier=CardTier.III,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            item=StatType.MOVEMENT,
            effect_id="greater_conjuration",
            effect_text='Choose and cast one spell in the spellbook —\n• "Find Familiar"\n• "Dimension Door"\n• "Cloud Kill"\n( Create a deadly cloud within distance to weaken your foe. )',
        ),
        Card(
            id="greater_enchantment",
            name="Greater Enchantment",
            image_id="BlueIIIA",  # Evolution of Elementary Enchantment -> Lesser Enchantment
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.RANGE,
            effect_id="greater_enchantment",
            effect_text='Choose and cast one spell in the spellbook —\n• "Suggestion"\n• "Dominate Person"\n• "Power Word Kill"\n( Command a weakened foe within earshot to perish instantly. )',
        ),
        Card(
            id="greater_transmutation",
            name="Greater Transmutation",
            image_id="BlueIIIB",  # Evolution of Lesser Transmutation
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.ATTACK,
            effect_id="greater_transmutation",
            effect_text='Choose and cast one spell in the spellbook —\n• "Midas Touch"\n• "Disintegrate"\n• "Polymorph"\n( Polymorph enemies into creatures or objects and vice versa. )',
        ),
        # =========================================================================
        # TIER II
        # =========================================================================
        Card(
            id="lesser_evocation",
            name="Lesser Evocation",
            image_id="RedIIA",  # Evolution of Elementary Evocation
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            item=StatType.DEFENSE,
            effect_id="lesser_evocation",
            effect_text='Choose and cast one spell in the spellbook —\n• "Burning Hands"\n• "Fireball"\n( Wait for your allies to clear the area before hurling a fireball! )',
        ),
        Card(
            id="lesser_necromancy",
            name="Lesser Necromancy",
            image_id="RedIIB",  # Necromancy School Branch Starter
            tier=CardTier.II,
            color=CardColor.RED,
            initiative=8,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            item=StatType.INITIATIVE,
            effect_id="lesser_necromancy",
            effect_text='Choose and cast one spell in the spellbook —\n• "Vampiric Touch"\n• "Create Undead"\n( Harm your foe to heal yourself. Raise an undead servant. )',
        ),
        Card(
            id="lesser_abjuration",
            name="Lesser Abjuration",
            image_id="GreenIIA",  # Evolution of Elementary Abjuration
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            item=StatType.INITIATIVE,
            effect_id="lesser_abjuration",
            effect_text='Choose and cast one spell in the spellbook —\n• "Shield"\n• "Banishment"\n( Touch anything to have it banished where you please. )',
        ),
        Card(
            id="lesser_conjuration",
            name="Lesser Conjuration",
            image_id="GreenIIB",  # Conjuration School Branch Starter
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=4,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            item=StatType.ATTACK,
            effect_id="lesser_conjuration",
            effect_text='Choose and cast one spell in the spellbook —\n• "Find Familiar"\n• "Dimension Door"\n( Summon a familiar to assist you. Travel to a faraway place. )',
        ),
        Card(
            id="lesser_enchantment",
            name="Lesser Enchantment",
            image_id="BlueIIA",  # Evolution of Elementary Enchantment
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.DEFENSE,
            effect_id="lesser_enchantment",
            effect_text='Choose and cast one spell in the spellbook —\n• "Suggestion"\n• "Dominate Person"\n( Turn the dominated person against their own troops. )',
        ),
        Card(
            id="lesser_transmutation",
            name="Lesser Transmutation",
            image_id="BlueIIB",  # Transmutation School Branch Starter
            tier=CardTier.II,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 2},
            item=StatType.ATTACK,
            effect_id="lesser_transmutation",
            effect_text='Choose and cast one spell in the spellbook —\n• "Midas Touch"\n• "Disintegrate"\n( Create gold. Turn objects and lesser creatures into dust. )',
        ),
        # =========================================================================
        # UNTIERED / TIER I
        # =========================================================================
        Card(
            id="elementary_evocation",
            name="Elementary Evocation",
            image_id="RedIA",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=7,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
            effect_id="elementary_evocation",
            effect_text='Cast the "Burning Hands" spell in the spellbook.\n( Burn multiple opponents in near vicinity. )',
        ),
        Card(
            id="elementary_abjuration",
            name="Elementary Abjuration",
            image_id="GreenIA",
            tier=CardTier.I,
            color=CardColor.GREEN,
            initiative=5,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
            effect_id="elementary_abjuration",
            effect_text='Cast the "Shield" spell in the spellbook.\n( The magic shield protects against mundane threats. )',
        ),
        Card(
            id="elementary_enchantment",
            name="Elementary Enchantment",
            image_id="BlueIA",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=9,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
            effect_id="elementary_enchantment",
            effect_text='Cast the "Suggestion" spell in the spellbook.\n( Compel the opposing champion to take a few extra steps. )',
        ),
        Card(
            id="cantrip",
            name="Cantrip",
            image_id="Silver",
            tier=CardTier.UNTIERED,
            color=CardColor.SILVER,
            initiative=11,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 1},
            effect_id="cantrip",
            effect_text='Choose and cast one spell in the spellbook —\n• "Shocking Grasp" ( To repel a foe! )\n• "Magic Missile" ( To blast at range! )\n• "Expeditious Retreat" ( To dart a great distance! )',
        ),
        Card(
            id="prepare_spells",
            name="Prepare Spells",
            image_id="Gold",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=13,
            primary_action=ActionType.SKILL,  # Basic Skill Frame
            primary_action_value=None,
            secondary_actions={ActionType.DEFENSE: 2},
            effect_id="prepare_spells",
            effect_text="Add all spell cards to the spellbook. Only Gydion can look at the cards in the spellbook.\nAs each spell is cast, remove it from the spellbook faceup. The action on the spell card is performed by the hero casting the spell.",
        ),
    ]

    h = Hero(
        id=HeroID("hero_gydion"),
        name="Gydion",
        deck=deck,
        spells=spells,
        hand=[],
        items={},
        ultimate_card=ultimate,
    )
    return h


HeroRegistry.register(create_gydion())
