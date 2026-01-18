"""
Tests for Wasp's Phase 1 card effects.

Cards covered:
- Shock: Attack + discard in radius (not adjacent)
- Electrocute: Same as Shock with larger radius
- Telekinesis: Place unit not in straight line
- Electroblast: Attack + discard OR defeat
- Reflect Projectiles: Block ranged + on_block discard
- Deflect Projectiles: Block ranged + on_block discard (exclude attacker)
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep, SelectStep, PlaceUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effects import CardEffectRegistry

# Register wasp effects
import goa2.scripts.wasp_effects  # noqa: F401


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def wasp_state():
    """
    Basic state with Wasp and enemies at various positions.

    Layout:
                     (-1,-1,2)   (0,-1,1)   (1,-1,0)
                  (-1,0,1)   [WASP]   (1,0,-1)   (2,0,-2)   (3,0,-3)
                     (-1,1,0)   (0,1,-1)   (1,1,-2)   (2,1,-3)

    Wasp at (0,0,0)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),  # Wasp
        Hex(q=1, r=0, s=-1),  # Adjacent
        Hex(q=2, r=0, s=-2),  # Range 2, straight line
        Hex(q=3, r=0, s=-3),  # Range 3, straight line
        Hex(q=1, r=1, s=-2),  # Range 2, diagonal
        Hex(q=2, r=1, s=-3),  # Range 3, diagonal
        Hex(q=0, r=-1, s=1),  # Adjacent (different axis)
        Hex(q=0, r=1, s=-1),  # Adjacent (different axis)
        Hex(q=-1, r=0, s=1),  # Adjacent (different axis)
        Hex(q=2, r=-1, s=-1),  # Range 2, diagonal
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )

    state.place_entity("wasp", Hex(q=0, r=0, s=0))
    state.current_actor_id = "wasp"
    return state


def make_shock_card():
    """Create a Shock card (Tier I Red Attack with radius 2)."""
    return Card(
        id="shock",
        name="Shock",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        is_ranged=False,
        radius_value=2,
        effect_id="shock",
        effect_text="Target a unit adjacent to you. After the attack: An enemy hero in radius and not adjacent to you discards a card, if able.",
        is_facedown=False,
    )


def make_electrocute_card():
    """Create an Electrocute card (Tier II Red Attack with radius 3)."""
    return Card(
        id="electrocute",
        name="Electrocute",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        is_ranged=False,
        radius_value=3,
        effect_id="electrocute",
        effect_text="Target a unit adjacent to you. After the attack: An enemy hero in radius and not adjacent to you discards a card, if able.",
        is_facedown=False,
    )


def make_telekinesis_card():
    """Create a Telekinesis card (Tier II Green Skill with range 3)."""
    return Card(
        id="telekinesis",
        name="Telekinesis",
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=7,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        is_ranged=False,
        range_value=3,
        effect_id="telekinesis",
        effect_text="Place a unit or a token in range, which is not in a straight line, into a space adjacent to you.",
        is_facedown=False,
    )


def make_electroblast_card():
    """Create an Electroblast card (Tier III Red Attack with radius 3)."""
    return Card(
        id="electroblast",
        name="Electroblast",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        is_ranged=False,
        radius_value=3,
        effect_id="electroblast",
        effect_text="Target a unit adjacent to you. After the attack: An enemy hero in radius and not adjacent to you discards a card, or is defeated.",
        is_facedown=False,
    )


def make_reflect_projectiles_card():
    """Create a Reflect Projectiles card (Tier III Green Defense)."""
    return Card(
        id="reflect_projectiles",
        name="Reflect Projectiles",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=6,
        primary_action=ActionType.DEFENSE,
        primary_action_value=0,
        is_ranged=False,
        range_value=3,
        effect_id="reflect_projectiles",
        effect_text="Block a ranged attack; if you do, an enemy hero in range discards a card, if able.",
        is_facedown=False,
    )


def make_deflect_projectiles_card():
    """Create a Deflect Projectiles card (Tier II Green Defense)."""
    return Card(
        id="deflect_projectiles",
        name="Deflect Projectiles",
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=5,
        primary_action=ActionType.DEFENSE,
        primary_action_value=0,
        is_ranged=False,
        range_value=2,
        effect_id="deflect_projectiles",
        effect_text="Block a ranged attack; if you do, an enemy hero in range, other than the attacker, discards a card, if able.",
        is_facedown=False,
    )


# =============================================================================
# Shock Tests
# =============================================================================


class TestShockEffect:
    """Tests for the Shock effect."""

    def test_shock_effect_registered(self):
        """Test that shock effect is properly registered."""
        effect = CardEffectRegistry.get("shock")
        assert effect is not None

    def test_shock_returns_correct_steps(self, wasp_state):
        """Test that shock returns attack + select + discard steps."""
        effect = CardEffectRegistry.get("shock")
        wasp = wasp_state.get_hero("wasp")
        card = make_shock_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 3 steps: AttackSequenceStep, SelectStep, ForceDiscardStep
        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "AttackSequenceStep"
        assert steps[1].__class__.__name__ == "SelectStep"
        assert steps[2].__class__.__name__ == "ForceDiscardStep"

    def test_shock_discard_target_must_not_be_adjacent(self, wasp_state):
        """Test that discard target selection excludes adjacent enemies."""
        # Add enemies
        enemy_adjacent = Hero(
            id="enemy_adjacent", name="Adjacent", team=TeamColor.BLUE, deck=[], level=1
        )
        enemy_distant = Hero(
            id="enemy_distant", name="Distant", team=TeamColor.BLUE, deck=[], level=1
        )
        wasp_state.teams[TeamColor.BLUE].heroes = [enemy_adjacent, enemy_distant]
        wasp_state.place_entity("enemy_adjacent", Hex(q=1, r=0, s=-1))  # Adjacent
        wasp_state.place_entity("enemy_distant", Hex(q=2, r=0, s=-2))  # Range 2

        effect = CardEffectRegistry.get("shock")
        wasp = wasp_state.get_hero("wasp")
        card = make_shock_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Check the SelectStep filters
        select_step = steps[1]
        assert select_step.filters is not None

        # Check that RangeFilter has min_range=2
        range_filter = None
        for f in select_step.filters:
            if f.__class__.__name__ == "RangeFilter":
                range_filter = f
                break

        assert range_filter is not None
        assert range_filter.min_range == 2, (
            "Discard target must not be adjacent (min_range=2)"
        )


# =============================================================================
# Electrocute Tests
# =============================================================================


class TestElectrocuteEffect:
    """Tests for the Electrocute effect."""

    def test_electrocute_effect_registered(self):
        """Test that electrocute effect is properly registered."""
        effect = CardEffectRegistry.get("electrocute")
        assert effect is not None

    def test_electrocute_uses_card_radius(self, wasp_state):
        """Test that electrocute uses the card's radius value."""
        effect = CardEffectRegistry.get("electrocute")
        wasp = wasp_state.get_hero("wasp")
        card = make_electrocute_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        select_step = steps[1]

        # Check RangeFilter max_range matches card radius
        range_filter = None
        for f in select_step.filters:
            if f.__class__.__name__ == "RangeFilter":
                range_filter = f
                break

        assert range_filter is not None
        assert range_filter.max_range == 3, "Should use card's radius_value (3)"


# =============================================================================
# Telekinesis Tests
# =============================================================================


class TestTelekinesisEffect:
    """Tests for the Telekinesis effect."""

    def test_telekinesis_effect_registered(self):
        """Test that telekinesis effect is properly registered."""
        effect = CardEffectRegistry.get("telekinesis")
        assert effect is not None

    def test_telekinesis_returns_correct_steps(self, wasp_state):
        """Test that telekinesis returns select unit, select hex, place steps."""
        effect = CardEffectRegistry.get("telekinesis")
        wasp = wasp_state.get_hero("wasp")
        card = make_telekinesis_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 3 steps: SelectStep (unit), SelectStep (hex), PlaceUnitStep
        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "SelectStep"
        assert steps[2].__class__.__name__ == "PlaceUnitStep"

    def test_telekinesis_target_must_not_be_in_straight_line(self, wasp_state):
        """Test that telekinesis target selection requires not in straight line."""
        effect = CardEffectRegistry.get("telekinesis")
        wasp = wasp_state.get_hero("wasp")
        card = make_telekinesis_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        unit_select_step = steps[0]

        # Check for NotInStraightLineFilter
        has_straight_line_filter = False
        for f in unit_select_step.filters:
            if f.__class__.__name__ == "NotInStraightLineFilter":
                has_straight_line_filter = True
                break

        assert has_straight_line_filter, "Should use NotInStraightLineFilter"

    def test_telekinesis_destination_must_be_adjacent(self, wasp_state):
        """Test that telekinesis destination must be adjacent to Wasp."""
        effect = CardEffectRegistry.get("telekinesis")
        wasp = wasp_state.get_hero("wasp")
        card = make_telekinesis_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        hex_select_step = steps[1]

        # Check RangeFilter max_range = 1
        range_filter = None
        for f in hex_select_step.filters:
            if f.__class__.__name__ == "RangeFilter":
                range_filter = f
                break

        assert range_filter is not None
        assert range_filter.max_range == 1, "Destination must be adjacent (max_range=1)"


# =============================================================================
# Electroblast Tests
# =============================================================================


class TestElectroblastEffect:
    """Tests for the Electroblast effect."""

    def test_electroblast_effect_registered(self):
        """Test that electroblast effect is properly registered."""
        effect = CardEffectRegistry.get("electroblast")
        assert effect is not None

    def test_electroblast_uses_discard_or_defeat(self, wasp_state):
        """Test that electroblast uses ForceDiscardOrDefeatStep."""
        effect = CardEffectRegistry.get("electroblast")
        wasp = wasp_state.get_hero("wasp")
        card = make_electroblast_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        assert len(steps) == 3
        assert steps[2].__class__.__name__ == "ForceDiscardOrDefeatStep"


# =============================================================================
# Reflect Projectiles Tests
# =============================================================================


class TestReflectProjectilesEffect:
    """Tests for the Reflect Projectiles effect."""

    def test_reflect_projectiles_effect_registered(self):
        """Test that reflect_projectiles effect is properly registered."""
        effect = CardEffectRegistry.get("reflect_projectiles")
        assert effect is not None

    def test_reflect_projectiles_blocks_ranged(self, wasp_state):
        """Test that reflect projectiles blocks ranged attacks."""
        from goa2.engine.stats import CardStats

        effect = CardEffectRegistry.get("reflect_projectiles")
        wasp = wasp_state.get_hero("wasp")
        card = make_reflect_projectiles_card()

        # Ranged attack context
        context = {"attack_is_ranged": True}
        steps = effect.get_defense_steps(wasp_state, wasp, card, context)

        assert steps is not None
        assert len(steps) == 1
        assert steps[0].key == "auto_block"
        assert steps[0].value is True

    def test_reflect_projectiles_fails_on_melee(self, wasp_state):
        """Test that reflect projectiles fails against melee attacks."""
        effect = CardEffectRegistry.get("reflect_projectiles")
        wasp = wasp_state.get_hero("wasp")
        card = make_reflect_projectiles_card()

        # Melee attack context
        context = {"attack_is_ranged": False}
        steps = effect.get_defense_steps(wasp_state, wasp, card, context)

        assert steps is not None
        assert len(steps) == 1
        assert steps[0].key == "defense_invalid"
        assert steps[0].value is True

    def test_reflect_projectiles_on_block_steps(self, wasp_state):
        """Test that on_block triggers discard selection."""
        effect = CardEffectRegistry.get("reflect_projectiles")
        wasp = wasp_state.get_hero("wasp")
        card = make_reflect_projectiles_card()

        context = {"block_succeeded": True}
        steps = effect.get_on_block_steps(wasp_state, wasp, card, context)

        assert steps is not None
        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "ForceDiscardStep"


# =============================================================================
# Deflect Projectiles Tests
# =============================================================================


class TestDeflectProjectilesEffect:
    """Tests for the Deflect Projectiles effect."""

    def test_deflect_projectiles_effect_registered(self):
        """Test that deflect_projectiles effect is properly registered."""
        effect = CardEffectRegistry.get("deflect_projectiles")
        assert effect is not None

    def test_deflect_projectiles_excludes_attacker(self, wasp_state):
        """Test that deflect projectiles on_block excludes the attacker."""
        effect = CardEffectRegistry.get("deflect_projectiles")
        wasp = wasp_state.get_hero("wasp")
        card = make_deflect_projectiles_card()

        context = {"block_succeeded": True, "attacker_id": "enemy_archer"}
        steps = effect.get_on_block_steps(wasp_state, wasp, card, context)

        assert steps is not None
        select_step = steps[0]

        # Check for ExcludeIdentityFilter
        exclude_filter = None
        for f in select_step.filters:
            if f.__class__.__name__ == "ExcludeIdentityFilter":
                exclude_filter = f
                break

        assert exclude_filter is not None
        assert "attacker_id" in exclude_filter.exclude_keys
