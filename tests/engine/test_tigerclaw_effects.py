"""
Tests for Tigerclaw card effects.

Cards covered:
- Dodge: Block ranged attack
- Hit and Run: Attack adjacent + move 1 after
- Sidestep: Block ranged + move 1 after
- Parry: Block non-ranged + attacker discards
- Riposte: Block non-ranged + attacker discards or is defeated
- Leaping Strike: Move 1 + attack adjacent + move 1
- Backstab: Attack adjacent + conditional +2 if friendly adjacent to target
- Backstab with a Ballista: Same as Backstab but ranged + block primary defense
- Combat Reflexes: Optional pre-move + attack + conditional post-move
- Evade: Block ranged + move 1 + retrieve discarded card
- Light-Fingered: Move 1 + steal 1 coin + conditional move 1
- Pick Pocket: Move 2 + steal 1 coin + conditional move 1
- Master Thief: Move 2 + steal 1-2 coins + conditional move 2
- Blend Into Shadows: Terrain-conditional placement + next-turn immunity
- Blink Strike: Straight-line pass-through attack
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_resolution_stack, push_steps

# Register tigerclaw effects
import goa2.scripts.tigerclaw_effects  # noqa: F401


# =============================================================================
# Card Factories
# =============================================================================


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id, name="Filler", tier=CardTier.UNTIERED, color=color,
        initiative=1, primary_action=ActionType.ATTACK, secondary_actions={},
        is_ranged=False, range_value=0, primary_action_value=1,
        effect_id="filler", effect_text="", is_facedown=False,
    )


def make_dodge_card():
    return Card(
        id="dodge", name="Dodge", tier=CardTier.I, color=CardColor.BLUE,
        initiative=10, primary_action=ActionType.DEFENSE,
        primary_action_value=None, secondary_actions={ActionType.MOVEMENT: 3},
        effect_id="dodge", effect_text="Block a ranged attack.",
        is_facedown=False,
    )


def make_hit_and_run_card():
    return Card(
        id="hit_and_run", name="Hit and Run", tier=CardTier.I,
        color=CardColor.RED, initiative=9, primary_action=ActionType.ATTACK,
        primary_action_value=3, secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 4},
        effect_id="hit_and_run",
        effect_text="Target a unit adjacent to you. After the attack: You may move 1 space.",
        is_facedown=False,
    )


def make_sidestep_card():
    return Card(
        id="sidestep", name="Sidestep", tier=CardTier.II, color=CardColor.BLUE,
        initiative=11, primary_action=ActionType.DEFENSE,
        primary_action_value=None, secondary_actions={ActionType.MOVEMENT: 3},
        effect_id="sidestep",
        effect_text="Block a ranged attack. You may move 1 space.",
        is_facedown=False,
    )


def make_parry_card():
    return Card(
        id="parry", name="Parry", tier=CardTier.II, color=CardColor.BLUE,
        initiative=11, primary_action=ActionType.DEFENSE,
        primary_action_value=None, secondary_actions={ActionType.MOVEMENT: 3},
        effect_id="parry",
        effect_text="Block a non-ranged attack. The attacker discards a card, if able.",
        is_facedown=False,
    )


def make_riposte_card():
    return Card(
        id="riposte", name="Riposte", tier=CardTier.III, color=CardColor.BLUE,
        initiative=11, primary_action=ActionType.DEFENSE,
        primary_action_value=None, secondary_actions={ActionType.MOVEMENT: 3},
        effect_id="riposte",
        effect_text="Block a non-ranged attack. The attacker discards a card, or is defeated.",
        is_facedown=False,
    )


def make_leaping_strike_card():
    return Card(
        id="leaping_strike", name="Leaping Strike", tier=CardTier.III,
        color=CardColor.RED, initiative=10, primary_action=ActionType.ATTACK,
        primary_action_value=4, secondary_actions={ActionType.DEFENSE: 4, ActionType.MOVEMENT: 4},
        effect_id="leaping_strike",
        effect_text="Before the attack: You may move 1 space. Target a unit adjacent to you. After the attack: You may move 1 space.",
        is_facedown=False,
    )


def make_backstab_card():
    return Card(
        id="backstab", name="Backstab", tier=CardTier.II,
        color=CardColor.RED, initiative=9, primary_action=ActionType.ATTACK,
        primary_action_value=5, secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 5},
        effect_id="backstab",
        effect_text='Target a unit adjacent to you; if a friendly unit is adjacent to the target, +2 Attack.',
        is_facedown=False,
    )


def make_backstab_with_a_ballista_card():
    return Card(
        id="backstab_with_a_ballista", name="Backstab with a Ballista",
        tier=CardTier.III, color=CardColor.RED, initiative=10,
        primary_action=ActionType.ATTACK, primary_action_value=5,
        secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 5},
        is_ranged=True, range_value=1,
        effect_id="backstab_with_a_ballista",
        effect_text='Target a unit in range; if a friendly unit is adjacent to the target +2 Attack, and the target cannot perform a primary action to defend.',
        is_facedown=False,
    )


def make_combat_reflexes_card():
    return Card(
        id="combat_reflexes", name="Combat Reflexes", tier=CardTier.II,
        color=CardColor.RED, initiative=9, primary_action=ActionType.ATTACK,
        primary_action_value=4, secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 4},
        effect_id="combat_reflexes",
        effect_text="Before the attack: You may move 1 space. Target a unit adjacent to you. After the attack: If you did not move before the attack, you may move 1 space.",
        is_facedown=False,
    )


def make_evade_card():
    return Card(
        id="evade", name="Evade", tier=CardTier.III, color=CardColor.BLUE,
        initiative=11, primary_action=ActionType.DEFENSE,
        primary_action_value=None, secondary_actions={ActionType.MOVEMENT: 3},
        effect_id="evade",
        effect_text="Block a ranged attack. You may move 1 space. You may retrieve your resolved or discarded basic skill card.",
        is_facedown=False,
    )


def make_blend_into_shadows_card():
    return Card(
        id="blend_into_shadows", name="Blend Into Shadows",
        tier=CardTier.UNTIERED, color=CardColor.SILVER,
        initiative=8, primary_action=ActionType.SKILL,
        primary_action_value=None, secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
        effect_id="blend_into_shadows",
        effect_text="If you are adjacent to a terrain hex, you may be placed on an empty space within 2 spaces. If you do, you are immune to attacks next turn.",
        is_facedown=False,
        radius_value=2,
    )


def make_blink_strike_card():
    return Card(
        id="blink_strike", name="Blink Strike",
        tier=CardTier.UNTIERED, color=CardColor.GOLD,
        initiative=9, primary_action=ActionType.ATTACK,
        primary_action_value=4, secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 3},
        effect_id="blink_strike",
        effect_text="Target a unit adjacent to you in a straight line; move to the space directly behind it, then attack it.",
        is_facedown=False,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tigerclaw_state():
    """
    Basic state with Tigerclaw and enemies at various positions.

    Tigerclaw at (0,0,0), enemy at (1,0,-1) (adjacent).
    """
    board = Board()
    hexes = set()
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            if abs(s) <= 3:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    enemy.hand = [_make_filler_card("enemy_card")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "tigerclaw"
    return state


# =============================================================================
# Dodge Tests
# =============================================================================


class TestDodgeEffect:

    def test_dodge_effect_registered(self):
        effect = CardEffectRegistry.get("dodge")
        assert effect is not None

    def test_dodge_blocks_ranged(self, tigerclaw_state):
        effect = CardEffectRegistry.get("dodge")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_dodge_card()

        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert steps is not None
        assert len(steps) == 1
        assert steps[0].key == "auto_block"
        assert steps[0].value is True

    def test_dodge_fails_on_melee(self, tigerclaw_state):
        effect = CardEffectRegistry.get("dodge")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_dodge_card()

        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert steps is not None
        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"
        assert steps[0].value is True


# =============================================================================
# Hit and Run Tests
# =============================================================================


class TestHitAndRunEffect:

    def test_hit_and_run_registered(self):
        effect = CardEffectRegistry.get("hit_and_run")
        assert effect is not None

    def test_hit_and_run_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("hit_and_run")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_hit_and_run_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "AttackSequenceStep"
        assert steps[1].__class__.__name__ == "SelectStep"      # post-move hex select
        assert steps[2].__class__.__name__ == "MoveUnitStep"    # post-move

    def test_hit_and_run_attack_is_adjacent(self, tigerclaw_state):
        effect = CardEffectRegistry.get("hit_and_run")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_hit_and_run_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert steps[0].range_val == 1
        assert steps[0].damage == 3  # primary_action_value

    def test_hit_and_run_post_move_is_optional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("hit_and_run")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_hit_and_run_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        select_step = steps[1]
        assert select_step.is_mandatory is False
        move_step = steps[2]
        assert move_step.range_val == 1
        assert move_step.is_movement_action is False


# =============================================================================
# Sidestep Tests
# =============================================================================


class TestSidestepEffect:

    def test_sidestep_registered(self):
        effect = CardEffectRegistry.get("sidestep")
        assert effect is not None

    def test_sidestep_blocks_ranged(self, tigerclaw_state):
        effect = CardEffectRegistry.get("sidestep")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_sidestep_card()

        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "auto_block"

    def test_sidestep_fails_on_melee(self, tigerclaw_state):
        effect = CardEffectRegistry.get("sidestep")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_sidestep_card()

        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"

    def test_sidestep_on_block_move(self, tigerclaw_state):
        effect = CardEffectRegistry.get("sidestep")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_sidestep_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[0].is_mandatory is False
        assert steps[1].__class__.__name__ == "MoveUnitStep"
        assert steps[1].range_val == 1
        assert steps[1].is_movement_action is False


# =============================================================================
# Parry Tests
# =============================================================================


class TestParryEffect:

    def test_parry_registered(self):
        effect = CardEffectRegistry.get("parry")
        assert effect is not None

    def test_parry_blocks_melee(self, tigerclaw_state):
        effect = CardEffectRegistry.get("parry")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_parry_card()

        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "auto_block"
        assert steps[0].value is True

    def test_parry_fails_on_ranged(self, tigerclaw_state):
        effect = CardEffectRegistry.get("parry")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_parry_card()

        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"

    def test_parry_on_block_force_discard(self, tigerclaw_state):
        effect = CardEffectRegistry.get("parry")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_parry_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].__class__.__name__ == "ForceDiscardStep"
        assert steps[0].victim_key == "attacker_id"


# =============================================================================
# Riposte Tests
# =============================================================================


class TestRiposteEffect:

    def test_riposte_registered(self):
        effect = CardEffectRegistry.get("riposte")
        assert effect is not None

    def test_riposte_blocks_melee(self, tigerclaw_state):
        effect = CardEffectRegistry.get("riposte")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_riposte_card()

        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "auto_block"

    def test_riposte_fails_on_ranged(self, tigerclaw_state):
        effect = CardEffectRegistry.get("riposte")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_riposte_card()

        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"

    def test_riposte_on_block_discard_or_defeat(self, tigerclaw_state):
        effect = CardEffectRegistry.get("riposte")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_riposte_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].__class__.__name__ == "ForceDiscardOrDefeatStep"
        assert steps[0].victim_key == "attacker_id"


# =============================================================================
# Leaping Strike Tests
# =============================================================================


class TestLeapingStrikeEffect:

    def test_leaping_strike_registered(self):
        effect = CardEffectRegistry.get("leaping_strike")
        assert effect is not None

    def test_leaping_strike_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("leaping_strike")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_leaping_strike_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 5
        assert steps[0].__class__.__name__ == "SelectStep"       # pre-move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # pre-move
        assert steps[2].__class__.__name__ == "AttackSequenceStep"
        assert steps[3].__class__.__name__ == "SelectStep"       # post-move hex
        assert steps[4].__class__.__name__ == "MoveUnitStep"     # post-move

    def test_leaping_strike_moves_are_optional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("leaping_strike")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_leaping_strike_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert steps[0].is_mandatory is False  # pre-move select
        assert steps[1].range_val == 1         # pre-move unit
        assert steps[3].is_mandatory is False  # post-move select
        assert steps[4].range_val == 1         # post-move unit

    def test_leaping_strike_attack_is_adjacent(self, tigerclaw_state):
        effect = CardEffectRegistry.get("leaping_strike")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_leaping_strike_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert steps[2].range_val == 1
        assert steps[2].damage == 4


# =============================================================================
# Backstab Tests
# =============================================================================


class TestBackstabEffect:

    def test_backstab_registered(self):
        effect = CardEffectRegistry.get("backstab")
        assert effect is not None

    def test_backstab_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        # Select target, count friendlies, check condition, set bonus, attack
        assert len(steps) == 5
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "CountStep"
        assert steps[2].__class__.__name__ == "CheckContextConditionStep"
        assert steps[3].__class__.__name__ == "SetContextFlagStep"
        assert steps[4].__class__.__name__ == "AttackSequenceStep"

    def test_backstab_select_filters(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        select = steps[0]

        # Must be adjacent + enemy
        has_range_1 = any(
            f.__class__.__name__ == "RangeFilter" and f.max_range == 1
            for f in select.filters
        )
        has_enemy = any(
            f.__class__.__name__ == "TeamFilter" and f.relation == "ENEMY"
            for f in select.filters
        )
        assert has_range_1
        assert has_enemy

    def test_backstab_count_friendlies_adjacent_to_target(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        count_step = steps[1]

        # Should count friendly units adjacent to victim_id, excluding self
        has_adjacency = any(
            f.__class__.__name__ == "AdjacencyToContextFilter"
            and f.target_key == "victim_id"
            for f in count_step.filters
        )
        has_friendly = any(
            f.__class__.__name__ == "TeamFilter" and f.relation == "FRIENDLY"
            for f in count_step.filters
        )
        has_exclude_self = any(
            f.__class__.__name__ == "ExcludeIdentityFilter"
            and f.exclude_self is True
            for f in count_step.filters
        )
        assert has_adjacency
        assert has_friendly
        assert has_exclude_self

    def test_backstab_bonus_is_2(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        # SetContextFlagStep sets atk_bonus=2, only if has_flanking
        set_bonus = steps[3]
        assert set_bonus.key == "atk_bonus"
        assert set_bonus.value == 2
        assert set_bonus.active_if_key == "has_flanking"

    def test_backstab_attack_uses_bonus_key(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        attack = steps[4]

        assert attack.damage_bonus_key == "atk_bonus"
        assert attack.target_id_key == "victim_id"
        assert attack.range_val == 1

    def test_backstab_bonus_applied_with_friendly_adjacent(self, tigerclaw_state):
        """Integration test: bonus is set when a friendly minion is adjacent to target."""
        # Place a friendly minion adjacent to the enemy
        minion = Minion(
            id="friendly_minion", name="Ally Minion",
            team=TeamColor.RED, type=MinionType.MELEE,
        )
        tigerclaw_state.teams[TeamColor.RED].minions.append(minion)
        tigerclaw_state.place_entity("friendly_minion", Hex(q=2, r=0, s=-2))

        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        count_step = steps[1]

        # Simulate context with victim selected
        context = {"victim_id": "enemy", "current_actor_id": "tigerclaw"}
        tigerclaw_state.execution_context = context
        result = count_step.resolve(tigerclaw_state, context)

        # Should count 1 friendly adjacent to enemy (the minion at (2,0,-2) is adjacent to (1,0,-1))
        assert context["friendly_adjacent_count"] >= 1

    def test_backstab_no_bonus_without_friendly(self, tigerclaw_state):
        """Integration test: no bonus when no friendly adjacent to target."""
        effect = CardEffectRegistry.get("backstab")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        count_step = steps[1]

        # Simulate context - no friendly adjacent to enemy
        context = {"victim_id": "enemy", "current_actor_id": "tigerclaw"}
        tigerclaw_state.execution_context = context
        result = count_step.resolve(tigerclaw_state, context)

        # Tigerclaw itself is adjacent to enemy but should be excluded (exclude_self)
        assert context["friendly_adjacent_count"] == 0


# =============================================================================
# Backstab with a Ballista Tests
# =============================================================================


class TestBackstabWithABallistaEffect:

    def test_backstab_ballista_registered(self):
        effect = CardEffectRegistry.get("backstab_with_a_ballista")
        assert effect is not None

    def test_backstab_ballista_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab_with_a_ballista")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_with_a_ballista_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        # Select, count, check, set bonus, set defense block, attack
        assert len(steps) == 6
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "CountStep"
        assert steps[2].__class__.__name__ == "CheckContextConditionStep"
        assert steps[3].__class__.__name__ == "SetContextFlagStep"  # atk_bonus
        assert steps[4].__class__.__name__ == "SetContextFlagStep"  # block_primary_defense
        assert steps[5].__class__.__name__ == "AttackSequenceStep"

    def test_backstab_ballista_uses_range(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab_with_a_ballista")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_with_a_ballista_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        # Select uses card range
        select = steps[0]
        has_range = any(
            f.__class__.__name__ == "RangeFilter" and f.max_range == 1
            for f in select.filters
        )
        assert has_range

        # Attack uses card range
        attack = steps[5]
        assert attack.range_val == 1

    def test_backstab_ballista_blocks_primary_defense_on_flank(self, tigerclaw_state):
        effect = CardEffectRegistry.get("backstab_with_a_ballista")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_backstab_with_a_ballista_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        block_defense_step = steps[4]
        assert block_defense_step.key == "block_primary_defense"
        assert block_defense_step.value is True
        assert block_defense_step.active_if_key == "has_flanking"


# =============================================================================
# Combat Reflexes Tests
# =============================================================================


class TestCombatReflexesEffect:

    def test_combat_reflexes_registered(self):
        effect = CardEffectRegistry.get("combat_reflexes")
        assert effect is not None

    def test_combat_reflexes_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("combat_reflexes")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_combat_reflexes_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 5
        assert steps[0].__class__.__name__ == "SelectStep"       # pre-move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # pre-move
        assert steps[2].__class__.__name__ == "AttackSequenceStep"
        assert steps[3].__class__.__name__ == "SelectStep"       # post-move hex
        assert steps[4].__class__.__name__ == "MoveUnitStep"     # post-move

    def test_combat_reflexes_pre_move_optional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("combat_reflexes")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_combat_reflexes_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        pre_select = steps[0]
        assert pre_select.is_mandatory is False
        pre_move = steps[1]
        assert pre_move.range_val == 1

    def test_combat_reflexes_post_move_conditional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("combat_reflexes")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_combat_reflexes_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        # Post-move select skips if pre-move was taken
        post_select = steps[3]
        assert post_select.is_mandatory is False
        assert post_select.skip_if_key == "pre_move_hex"
        post_move = steps[4]
        assert post_move.range_val == 1

    def test_combat_reflexes_pre_move_stores_key(self, tigerclaw_state):
        effect = CardEffectRegistry.get("combat_reflexes")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_combat_reflexes_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        pre_select = steps[0]
        assert pre_select.output_key == "pre_move_hex"

    def test_combat_reflexes_attack_adjacent(self, tigerclaw_state):
        effect = CardEffectRegistry.get("combat_reflexes")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_combat_reflexes_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        attack = steps[2]
        assert attack.range_val == 1
        assert attack.damage == 4


# =============================================================================
# Evade Tests
# =============================================================================


class TestEvadeEffect:

    def test_evade_registered(self):
        effect = CardEffectRegistry.get("evade")
        assert effect is not None

    def test_evade_blocks_ranged(self, tigerclaw_state):
        effect = CardEffectRegistry.get("evade")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_evade_card()

        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "auto_block"

    def test_evade_fails_on_melee(self, tigerclaw_state):
        effect = CardEffectRegistry.get("evade")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_evade_card()

        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"

    def test_evade_on_block_steps(self, tigerclaw_state):
        effect = CardEffectRegistry.get("evade")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_evade_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        assert len(steps) == 4
        assert steps[0].__class__.__name__ == "SelectStep"       # move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # move
        assert steps[2].__class__.__name__ == "SelectStep"       # card select
        assert steps[3].__class__.__name__ == "RetrieveCardStep"

    def test_evade_on_block_move_is_optional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("evade")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_evade_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        assert steps[0].is_mandatory is False
        assert steps[1].range_val == 1
        assert steps[1].is_movement_action is False

    def test_evade_on_block_retrieve_is_optional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("evade")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_evade_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(tigerclaw_state, tc, card, context)

        # SelectStep for card is optional
        card_select = steps[2]
        assert card_select.is_mandatory is False
        assert card_select.output_key == "retrieved_card"

        # RetrieveCardStep only runs if card was selected
        retrieve = steps[3]
        assert retrieve.active_if_key == "retrieved_card"


# =============================================================================
# Card Factories for Steal Cards
# =============================================================================


def make_light_fingered_card():
    return Card(
        id="light_fingered", name="Light-Fingered", tier=CardTier.I,
        color=CardColor.GREEN, initiative=2, primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 3},
        effect_id="light_fingered",
        effect_text="You may move 1 space. Take 1 coin from an enemy hero adjacent to you; if you do, you may move 1 space.",
        is_facedown=False,
    )


def make_pick_pocket_card():
    return Card(
        id="pick_pocket", name="Pick Pocket", tier=CardTier.II,
        color=CardColor.GREEN, initiative=2, primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 1, ActionType.MOVEMENT: 3},
        effect_id="pick_pocket",
        effect_text="Move up to 2 spaces. Take 1 coin from an enemy hero adjacent to you; if you do, you may move 1 space.",
        is_facedown=False,
    )


def make_master_thief_card():
    return Card(
        id="master_thief", name="Master Thief", tier=CardTier.III,
        color=CardColor.GREEN, initiative=1, primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 3},
        effect_id="master_thief",
        effect_text="Move up to 2 spaces. Take 1 or 2 coins from an enemy hero adjacent to you; if you do, you may move up to 2 spaces.",
        is_facedown=False,
    )


# =============================================================================
# Light-Fingered Tests
# =============================================================================


class TestLightFingeredEffect:

    def test_light_fingered_registered(self):
        effect = CardEffectRegistry.get("light_fingered")
        assert effect is not None

    def test_light_fingered_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("light_fingered")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_light_fingered_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 6
        assert steps[0].__class__.__name__ == "SelectStep"       # pre-move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # pre-move
        assert steps[2].__class__.__name__ == "SelectStep"       # select victim
        assert steps[3].__class__.__name__ == "StealCoinsStep"   # steal
        assert steps[4].__class__.__name__ == "SelectStep"       # post-move hex
        assert steps[5].__class__.__name__ == "MoveUnitStep"     # post-move

    def test_light_fingered_pre_move_optional_range_1(self, tigerclaw_state):
        effect = CardEffectRegistry.get("light_fingered")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_light_fingered_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        assert steps[0].is_mandatory is False
        assert steps[1].range_val == 1

    def test_light_fingered_select_adjacent_enemy_hero(self, tigerclaw_state):
        effect = CardEffectRegistry.get("light_fingered")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_light_fingered_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        select = steps[2]

        assert select.is_mandatory is False
        has_hero = any(
            f.__class__.__name__ == "UnitTypeFilter" and f.unit_type == "HERO"
            for f in select.filters
        )
        has_enemy = any(
            f.__class__.__name__ == "TeamFilter" and f.relation == "ENEMY"
            for f in select.filters
        )
        has_range_1 = any(
            f.__class__.__name__ == "RangeFilter" and f.max_range == 1
            for f in select.filters
        )
        assert has_hero
        assert has_enemy
        assert has_range_1

    def test_light_fingered_steal_1_coin(self, tigerclaw_state):
        effect = CardEffectRegistry.get("light_fingered")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_light_fingered_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        steal = steps[3]

        assert steal.victim_key == "steal_victim"
        assert steal.amount == 1
        assert steal.output_key == "stole_coins"
        assert steal.active_if_key == "steal_victim"

    def test_light_fingered_post_move_conditional(self, tigerclaw_state):
        effect = CardEffectRegistry.get("light_fingered")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_light_fingered_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        post_select = steps[4]
        post_move = steps[5]

        assert post_select.is_mandatory is False
        assert post_select.active_if_key == "stole_coins"
        assert post_move.range_val == 1
        assert post_move.active_if_key == "post_move_hex"

    def test_light_fingered_steal_integration(self, tigerclaw_state):
        """Integration test: steal transfers coins from enemy to actor."""
        from goa2.engine.steps import StealCoinsStep

        enemy = tigerclaw_state.get_hero("enemy")
        enemy.gold = 5
        tc = tigerclaw_state.get_hero("tigerclaw")
        tc.gold = 0

        step = StealCoinsStep(
            victim_key="steal_victim", amount=1, output_key="stole_coins"
        )
        context = {"steal_victim": "enemy", "current_actor_id": "tigerclaw"}
        result = step.resolve(tigerclaw_state, context)

        assert result.is_finished
        assert enemy.gold == 4
        assert tc.gold == 1
        assert context["stole_coins"] is True
        assert len(result.events) == 1
        assert result.events[0].metadata["amount"] == 1
        assert result.events[0].metadata["reason"] == "steal"

    def test_steal_coins_capped_by_victim_gold(self, tigerclaw_state):
        """Integration test: cannot steal more coins than victim has."""
        from goa2.engine.steps import StealCoinsStep

        enemy = tigerclaw_state.get_hero("enemy")
        enemy.gold = 1
        tc = tigerclaw_state.get_hero("tigerclaw")
        tc.gold = 0

        step = StealCoinsStep(
            victim_key="steal_victim", amount=3, output_key="stole_coins"
        )
        context = {"steal_victim": "enemy", "current_actor_id": "tigerclaw"}
        result = step.resolve(tigerclaw_state, context)

        assert enemy.gold == 0
        assert tc.gold == 1
        assert context["stole_coins"] is True

    def test_steal_coins_no_gold_no_flag(self, tigerclaw_state):
        """Integration test: no flag set when victim has 0 gold."""
        from goa2.engine.steps import StealCoinsStep

        enemy = tigerclaw_state.get_hero("enemy")
        enemy.gold = 0

        step = StealCoinsStep(
            victim_key="steal_victim", amount=1, output_key="stole_coins"
        )
        context = {"steal_victim": "enemy", "current_actor_id": "tigerclaw"}
        result = step.resolve(tigerclaw_state, context)

        assert "stole_coins" not in context
        assert len(result.events) == 0


# =============================================================================
# Pick Pocket Tests
# =============================================================================


class TestPickPocketEffect:

    def test_pick_pocket_registered(self):
        effect = CardEffectRegistry.get("pick_pocket")
        assert effect is not None

    def test_pick_pocket_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("pick_pocket")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_pick_pocket_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 6
        assert steps[0].__class__.__name__ == "SelectStep"       # pre-move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # pre-move
        assert steps[2].__class__.__name__ == "SelectStep"       # select victim
        assert steps[3].__class__.__name__ == "StealCoinsStep"
        assert steps[4].__class__.__name__ == "SelectStep"       # post-move hex
        assert steps[5].__class__.__name__ == "MoveUnitStep"     # post-move

    def test_pick_pocket_pre_move_range_2(self, tigerclaw_state):
        effect = CardEffectRegistry.get("pick_pocket")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_pick_pocket_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        assert steps[1].range_val == 2
        assert steps[0].is_mandatory is False

    def test_pick_pocket_post_move_range_1(self, tigerclaw_state):
        effect = CardEffectRegistry.get("pick_pocket")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_pick_pocket_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        post_move = steps[5]

        assert post_move.range_val == 1
        assert post_move.active_if_key == "post_move_hex"

    def test_pick_pocket_steals_1_coin(self, tigerclaw_state):
        effect = CardEffectRegistry.get("pick_pocket")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_pick_pocket_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        steal = steps[3]

        assert steal.amount == 1


# =============================================================================
# Master Thief Tests
# =============================================================================


class TestMasterThiefEffect:

    def test_master_thief_registered(self):
        effect = CardEffectRegistry.get("master_thief")
        assert effect is not None

    def test_master_thief_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("master_thief")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_master_thief_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 7
        assert steps[0].__class__.__name__ == "SelectStep"       # pre-move hex
        assert steps[1].__class__.__name__ == "MoveUnitStep"     # pre-move
        assert steps[2].__class__.__name__ == "SelectStep"       # select victim
        assert steps[3].__class__.__name__ == "SelectStep"       # choose amount
        assert steps[4].__class__.__name__ == "StealCoinsStep"   # steal
        assert steps[5].__class__.__name__ == "SelectStep"       # post-move hex
        assert steps[6].__class__.__name__ == "MoveUnitStep"     # post-move

    def test_master_thief_pre_move_range_2(self, tigerclaw_state):
        effect = CardEffectRegistry.get("master_thief")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_master_thief_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        assert steps[1].range_val == 2

    def test_master_thief_amount_choice_1_or_2(self, tigerclaw_state):
        effect = CardEffectRegistry.get("master_thief")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_master_thief_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        amount_select = steps[3]

        from goa2.domain.models import TargetType
        assert amount_select.target_type == TargetType.NUMBER
        assert amount_select.number_options == [1, 2]
        assert amount_select.output_key == "steal_amount"
        assert amount_select.active_if_key == "steal_victim"

    def test_master_thief_steal_uses_amount_key(self, tigerclaw_state):
        effect = CardEffectRegistry.get("master_thief")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_master_thief_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        steal = steps[4]

        assert steal.amount_key == "steal_amount"
        assert steal.victim_key == "steal_victim"
        assert steal.output_key == "stole_coins"

    def test_master_thief_post_move_range_2(self, tigerclaw_state):
        effect = CardEffectRegistry.get("master_thief")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_master_thief_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        post_move = steps[6]

        assert post_move.range_val == 2
        assert post_move.active_if_key == "post_move_hex"

    def test_master_thief_steal_dynamic_amount(self, tigerclaw_state):
        """Integration test: StealCoinsStep reads amount from context."""
        from goa2.engine.steps import StealCoinsStep

        enemy = tigerclaw_state.get_hero("enemy")
        enemy.gold = 10
        tc = tigerclaw_state.get_hero("tigerclaw")
        tc.gold = 0

        step = StealCoinsStep(
            victim_key="steal_victim", amount_key="steal_amount",
            output_key="stole_coins",
        )
        context = {
            "steal_victim": "enemy",
            "steal_amount": 2,
            "current_actor_id": "tigerclaw",
        }
        result = step.resolve(tigerclaw_state, context)

        assert enemy.gold == 8
        assert tc.gold == 2
        assert context["stole_coins"] is True
        assert result.events[0].metadata["amount"] == 2


# =============================================================================
# Blend Into Shadows Tests
# =============================================================================


class TestBlendIntoShadowsEffect:

    def test_blend_registered(self):
        effect = CardEffectRegistry.get("blend_into_shadows")
        assert effect is not None

    def test_blend_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("blend_into_shadows")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_blend_into_shadows_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 5
        assert steps[0].__class__.__name__ == "CountStep"
        assert steps[1].__class__.__name__ == "CheckContextConditionStep"
        assert steps[2].__class__.__name__ == "SelectStep"
        assert steps[3].__class__.__name__ == "PlaceUnitStep"
        assert steps[4].__class__.__name__ == "CreateEffectStep"

    def test_blend_happy_path(self):
        """Hero adjacent to terrain → select hex → place → get immunity."""
        from goa2.engine.steps import (
            CountStep, CheckContextConditionStep, PlaceUnitStep, CreateEffectStep,
        )

        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        # Make (1,0,-1) a terrain hex
        board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blend_into_shadows")
        card = make_blend_into_shadows_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # CountStep counts terrain adjacent → should find 1
        req = process_resolution_stack(state)
        # CheckContextConditionStep runs automatically
        # SelectStep asks for destination hex
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        # Select destination hex
        dest = Hex(q=0, r=1, s=-1)
        state.execution_stack[-1].pending_input = {
            "selection": {"q": dest.q, "r": dest.r, "s": dest.s}
        }

        # Process remaining steps (PlaceUnitStep + CreateEffectStep)
        req = process_resolution_stack(state)
        assert req is None  # All done

        # Hero moved to destination
        assert state.entity_locations["tigerclaw"] == dest

        # Has ATTACK_IMMUNITY effect
        from goa2.domain.models.effect import EffectType, DurationType
        immunity_effects = [
            e for e in state.active_effects
            if e.effect_type == EffectType.ATTACK_IMMUNITY
            and e.duration == DurationType.NEXT_TURN
        ]
        assert len(immunity_effects) == 1

    def test_blend_no_terrain_adjacent(self):
        """Hero not adjacent to terrain → effect does nothing (skips)."""
        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()
        # No terrain hexes at all

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blend_into_shadows")
        card = make_blend_into_shadows_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # All steps should run and skip (no input requested)
        req = process_resolution_stack(state)
        assert req is None

        # Hero didn't move
        assert state.entity_locations["tigerclaw"] == Hex(q=0, r=0, s=0)

        # No immunity effects
        from goa2.domain.models.effect import EffectType
        immunity_effects = [
            e for e in state.active_effects
            if e.effect_type == EffectType.ATTACK_IMMUNITY
        ]
        assert len(immunity_effects) == 0

    def test_blend_terrain_adjacent_but_all_hexes_occupied_aborts(self):
        """Adjacent to terrain but no valid destination → abort_action."""
        board = Board()
        # Minimal board: just hero hex and terrain hex and a couple destinations
        hexes_list = [
            Hex(q=0, r=0, s=0),   # hero
            Hex(q=1, r=0, s=-1),  # terrain
            Hex(q=-1, r=0, s=1),  # occupied
            Hex(q=0, r=-1, s=1),  # occupied
            Hex(q=0, r=1, s=-1),  # occupied
            Hex(q=-1, r=1, s=0),  # occupied
            Hex(q=1, r=-1, s=0),  # occupied
        ]
        z1 = Zone(id="z1", hexes=set(hexes_list), neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()
        board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        # Create blockers for all non-terrain hexes within range 2
        blockers = []
        for i, h in enumerate(hexes_list[2:]):
            blocker = Hero(
                id=f"blocker_{i}", name=f"Blocker{i}",
                team=TeamColor.BLUE, deck=[], level=1,
            )
            blockers.append(blocker)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=blockers, minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        for i, h in enumerate(hexes_list[2:]):
            state.place_entity(f"blocker_{i}", h)
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blend_into_shadows")
        card = make_blend_into_shadows_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # SelectStep is mandatory → no valid options → abort_action
        req = process_resolution_stack(state)
        assert req is None  # Aborted, no input needed

        # Hero didn't move
        assert state.entity_locations["tigerclaw"] == Hex(q=0, r=0, s=0)


# =============================================================================
# Blink Strike Tests
# =============================================================================


class TestBlinkStrikeEffect:

    def test_blink_strike_registered(self):
        effect = CardEffectRegistry.get("blink_strike")
        assert effect is not None

    def test_blink_strike_structure(self, tigerclaw_state):
        effect = CardEffectRegistry.get("blink_strike")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_blink_strike_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)

        assert len(steps) == 4
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "ComputeHexStep"
        assert steps[2].__class__.__name__ == "PlaceUnitStep"
        assert steps[3].__class__.__name__ == "AttackSequenceStep"

    def test_blink_strike_select_has_space_behind_filter(self, tigerclaw_state):
        effect = CardEffectRegistry.get("blink_strike")
        tc = tigerclaw_state.get_hero("tigerclaw")
        card = make_blink_strike_card()

        steps = effect.get_steps(tigerclaw_state, tc, card)
        select = steps[0]
        has_sbf = any(
            f.__class__.__name__ == "SpaceBehindEmptyFilter"
            for f in select.filters
        )
        assert has_sbf

    def test_blink_strike_happy_path(self):
        """Hero at (0,0,0), enemy at (1,-1,0), empty behind at (2,-2,0) →
        hero blinks to (2,-2,0) and attacks enemy."""
        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
        enemy.hand = [_make_filler_card("enemy_card")]

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.place_entity("enemy", Hex(q=1, r=-1, s=0))
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blink_strike")
        card = make_blink_strike_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # SelectStep: select enemy to blink through
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"

        state.execution_stack[-1].pending_input = {"selection": "enemy"}

        # ComputeHexStep + PlaceUnitStep run, then AttackSequenceStep asks for target
        # (target_id_key is set, so it skips target selection and goes to reaction)
        req = process_resolution_stack(state)

        # Hero should now be at (2,-2,0) - behind enemy
        assert state.entity_locations["tigerclaw"] == Hex(q=2, r=-2, s=0)

        # The attack sequence is now running (reaction window for enemy)
        # Skip defense
        if req is not None and req.get("type") == "SELECT_CARD":
            state.execution_stack[-1].pending_input = {"selection": "SKIP"}
            req = process_resolution_stack(state)

        # Attack resolved - stack should be empty
        assert req is None or req.get("type") != "SELECT_UNIT"

    def test_blink_strike_hex_behind_blocked(self):
        """Enemy adjacent but hex behind is occupied → no valid targets, abort."""
        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
        blocker = Hero(id="blocker", name="Blocker", team=TeamColor.BLUE, deck=[], level=1)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy, blocker], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.place_entity("enemy", Hex(q=1, r=-1, s=0))
        state.place_entity("blocker", Hex(q=2, r=-2, s=0))  # blocks the hex behind enemy
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blink_strike")
        card = make_blink_strike_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # SelectStep is mandatory, but no valid targets → abort_action
        req = process_resolution_stack(state)
        assert req is None  # Aborted

        # Hero didn't move
        assert state.entity_locations["tigerclaw"] == Hex(q=0, r=0, s=0)

    def test_blink_strike_no_adjacent_enemy(self):
        """No enemy at range 1 → abort (mandatory)."""
        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.place_entity("enemy", Hex(q=3, r=-3, s=0))  # Far away
        state.current_actor_id = "tigerclaw"

        effect = CardEffectRegistry.get("blink_strike")
        card = make_blink_strike_card()
        steps = effect.get_steps(state, tc, card)
        push_steps(state, steps)

        # SelectStep mandatory, no valid targets → abort
        req = process_resolution_stack(state)
        assert req is None

        # Hero didn't move
        assert state.entity_locations["tigerclaw"] == Hex(q=0, r=0, s=0)

    def test_compute_hex_step_integration(self):
        """ComputeHexStep computes correct hex behind target."""
        from goa2.engine.steps import ComputeHexStep

        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.place_entity("enemy", Hex(q=1, r=-1, s=0))
        state.current_actor_id = "tigerclaw"

        step = ComputeHexStep(target_key="blink_victim", scale=1, output_key="blink_dest")
        context = {"blink_victim": "enemy"}
        result = step.resolve(state, context)

        assert result.is_finished
        assert context["blink_dest"] == Hex(q=2, r=-2, s=0)

    def test_space_behind_empty_filter(self):
        """SpaceBehindEmptyFilter passes when hex behind is empty, fails when occupied."""
        from goa2.engine.filters import SpaceBehindEmptyFilter

        board = Board()
        hexes = set()
        for q in range(-3, 4):
            for r in range(-3, 4):
                s = -q - r
                if abs(s) <= 3:
                    hexes.add(Hex(q=q, r=r, s=s))
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        tc = Hero(id="tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=1)
        enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[tc], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("tigerclaw", Hex(q=0, r=0, s=0))
        state.place_entity("enemy", Hex(q=1, r=-1, s=0))
        state.current_actor_id = "tigerclaw"

        f = SpaceBehindEmptyFilter(origin_id="tigerclaw")
        context = {}

        # Behind enemy at (1,-1,0) from (0,0,0) is (2,-2,0) — empty
        assert f.apply("enemy", state, context) is True

        # Place a blocker behind
        blocker = Hero(id="blocker", name="Blocker", team=TeamColor.BLUE, deck=[], level=1)
        state.teams[TeamColor.BLUE].heroes.append(blocker)
        state.place_entity("blocker", Hex(q=2, r=-2, s=0))

        assert f.apply("enemy", state, context) is False
