"""
Tests for Wasp's Phase 1 card effects.

Cards covered:
- Shock: Attack + discard in radius (not adjacent)
- Electrocute: Same as Shock with larger radius
- Telekinesis: Place unit not in straight line
- Mass Telekinesis: Telekinesis + May Repeat Once
- Electroblast: Attack + discard OR defeat
- Reflect Projectiles: Block ranged + on_block discard
- Deflect Projectiles: Block ranged + on_block discard (exclude attacker)
- Lift Up: Orbit movement (radius preserved)
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
from goa2.engine.steps import (
    ResolveCardStep,
    SelectStep,
    PlaceUnitStep,
    MayRepeatOnceStep,
    MayRepeatNTimesStep,
)
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


def make_mass_telekinesis_card():
    """Create a Mass Telekinesis card (Tier III Green Skill with range 3)."""
    return Card(
        id="mass_telekinesis",
        name="Mass Telekinesis",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=2,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        is_ranged=False,
        range_value=3,
        effect_id="mass_telekinesis",
        effect_text="Place a unit or a token in range, which is not in a straight line, into a space adjacent to you. May repeat once.",
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


def make_lift_up_card():
    """Create a Lift Up card (Tier I Blue Skill with radius 2)."""
    return Card(
        id="lift_up",
        name="Lift Up",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        radius_value=2,
        effect_id="lift_up",
        effect_text="Move a unit, or a token, in radius 1 space, without moving it away from you or closer to you. May repeat once on the same target.",
        is_facedown=False,
    )


def make_control_gravity_card():
    """Create a Control Gravity card (Tier II Blue Skill with radius 3)."""
    return Card(
        id="control_gravity",
        name="Control Gravity",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        radius_value=3,
        effect_id="control_gravity",
        effect_text="Move a unit, or a token, in radius 1 space, without moving it away from you or closer to you. May repeat once on the same target.",
        is_facedown=False,
    )


def make_center_of_mass_card():
    """Create a Center of Mass card (Tier III Blue Skill with radius 3)."""
    return Card(
        id="center_of_mass",
        name="Center of Mass",
        tier=CardTier.III,
        color=CardColor.BLUE,
        initiative=3,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        radius_value=3,
        effect_id="center_of_mass",
        effect_text="Move a unit, or a token, in radius 1 space, without moving it away from you or closer to you. May repeat up to two times on the same target.",
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
# Mass Telekinesis Tests
# =============================================================================


class TestMassTelekinesisEffect:
    """Tests for the Mass Telekinesis effect."""

    def test_mass_telekinesis_effect_registered(self):
        """Test that mass_telekinesis effect is properly registered."""
        effect = CardEffectRegistry.get("mass_telekinesis")
        assert effect is not None

    def test_mass_telekinesis_structure(self, wasp_state):
        """
        Test that mass_telekinesis returns:
        1. Select Unit
        2. Select Destination
        3. Place Unit
        4. MayRepeatOnceStep containing the same logic
        """
        effect = CardEffectRegistry.get("mass_telekinesis")
        wasp = wasp_state.get_hero("wasp")
        card = make_mass_telekinesis_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 4 steps total
        assert len(steps) == 4
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "SelectStep"
        assert steps[2].__class__.__name__ == "PlaceUnitStep"
        assert steps[3].__class__.__name__ == "MayRepeatOnceStep"

        repeat_step = steps[3]
        # Verify the repeat template contains the same steps
        template = repeat_step.steps_template
        assert len(template) == 3
        assert template[0].__class__.__name__ == "SelectStep"
        assert template[1].__class__.__name__ == "SelectStep"
        assert template[2].__class__.__name__ == "PlaceUnitStep"

    def test_mass_telekinesis_filters(self, wasp_state):
        """Test that filters are correctly applied to the initial steps."""
        effect = CardEffectRegistry.get("mass_telekinesis")
        wasp = wasp_state.get_hero("wasp")
        card = make_mass_telekinesis_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        unit_select = steps[0]
        hex_select = steps[1]

        # Verify unit selection filter (Not in straight line)
        has_sl_filter = any(
            f.__class__.__name__ == "NotInStraightLineFilter"
            for f in unit_select.filters
        )
        assert has_sl_filter, "Must filter out units in straight line"

        # Verify destination filter (Adjacent, Range 1)
        range_filter = next(
            (f for f in hex_select.filters if f.__class__.__name__ == "RangeFilter"),
            None,
        )
        assert range_filter is not None
        assert range_filter.max_range == 1, "Destination must be adjacent"


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


# =============================================================================
# Lift Up Tests
# =============================================================================


class TestLiftUpEffect:
    """Tests for the Lift Up effect."""

    def test_lift_up_effect_registered(self):
        """Test that lift_up effect is properly registered."""
        effect = CardEffectRegistry.get("lift_up")
        assert effect is not None

    def test_lift_up_structure(self, wasp_state):
        """
        Test that lift_up returns:
        1. Select Unit
        2. Select Destination
        3. Place Unit
        4. MayRepeatOnceStep (repeating Steps 2 & 3 only)
        """
        effect = CardEffectRegistry.get("lift_up")
        wasp = wasp_state.get_hero("wasp")
        card = make_lift_up_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 4 steps total
        assert len(steps) == 4
        assert steps[0].__class__.__name__ == "SelectStep"  # Select Unit
        assert steps[1].__class__.__name__ == "SelectStep"  # Select Hex
        assert steps[2].__class__.__name__ == "PlaceUnitStep"  # Place
        assert steps[3].__class__.__name__ == "MayRepeatOnceStep"  # Repeat

        # Verify initial target selection filters
        unit_select = steps[0]
        # Range 2
        assert any(
            f.__class__.__name__ == "RangeFilter" and f.max_range == 2
            for f in unit_select.filters
        )

        # Verify destination selection filters
        hex_select = steps[1]
        # 1. AdjacencyToContextFilter (adjacent to target unit)
        assert any(
            f.__class__.__name__ == "AdjacencyToContextFilter"
            and f.target_key == "lift_target"
            for f in hex_select.filters
        )
        # 2. PreserveDistanceFilter (preserve distance to Wasp/origin)
        assert any(
            f.__class__.__name__ == "PreserveDistanceFilter"
            and f.target_key == "lift_target"
            for f in hex_select.filters
        )

        # Verify repeat template only contains move steps (2 & 3), not target selection (1)
        repeat_step = steps[3]
        template = repeat_step.steps_template
        assert len(template) == 2
        assert template[0].__class__.__name__ == "SelectStep"
        assert template[1].__class__.__name__ == "PlaceUnitStep"

        # Verify keys are consistent
        assert template[0].output_key == "lift_dest"
        assert template[1].unit_key == "lift_target"


# =============================================================================
# Control Gravity Tests
# =============================================================================


class TestControlGravityEffect:
    """Tests for the Control Gravity effect."""

    def test_control_gravity_effect_registered(self):
        """Test that control_gravity effect is properly registered."""
        effect = CardEffectRegistry.get("control_gravity")
        assert effect is not None

    def test_control_gravity_inherits_from_lift_up(self):
        """Test that ControlGravityEffect inherits from LiftUpEffect."""
        from goa2.scripts.wasp_effects import ControlGravityEffect, LiftUpEffect

        assert issubclass(ControlGravityEffect, LiftUpEffect)

    def test_control_gravity_uses_card_radius(self, wasp_state):
        """Test that control_gravity uses the card's radius value (3)."""
        effect = CardEffectRegistry.get("control_gravity")
        wasp = wasp_state.get_hero("wasp")
        card = make_control_gravity_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Check unit select filter uses radius 3
        unit_select = steps[0]
        range_filter = next(
            (f for f in unit_select.filters if f.__class__.__name__ == "RangeFilter"),
            None,
        )
        assert range_filter is not None
        assert range_filter.max_range == 3, "Should use card's radius_value (3)"

    def test_control_gravity_structure_same_as_lift_up(self, wasp_state):
        """Test that control_gravity has same structure as lift_up."""
        effect = CardEffectRegistry.get("control_gravity")
        wasp = wasp_state.get_hero("wasp")
        card = make_control_gravity_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 4 steps: Select Unit, Select Hex, Place, MayRepeatOnce
        assert len(steps) == 4
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "SelectStep"
        assert steps[2].__class__.__name__ == "PlaceUnitStep"
        assert steps[3].__class__.__name__ == "MayRepeatOnceStep"


# =============================================================================
# Center of Mass Tests
# =============================================================================


class TestCenterOfMassEffect:
    """Tests for the Center of Mass effect."""

    def test_center_of_mass_effect_registered(self):
        """Test that center_of_mass effect is properly registered."""
        effect = CardEffectRegistry.get("center_of_mass")
        assert effect is not None

    def test_center_of_mass_inherits_from_lift_up(self):
        """Test that CenterOfMassEffect inherits from LiftUpEffect."""
        from goa2.scripts.wasp_effects import CenterOfMassEffect, LiftUpEffect

        assert issubclass(CenterOfMassEffect, LiftUpEffect)

    def test_center_of_mass_uses_repeat_n_times(self, wasp_state):
        """Test that center_of_mass uses MayRepeatNTimesStep with max_repeats=2."""
        effect = CardEffectRegistry.get("center_of_mass")
        wasp = wasp_state.get_hero("wasp")
        card = make_center_of_mass_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 4 steps: Select Unit, Select Hex, Place, MayRepeatNTimesStep
        assert len(steps) == 4
        assert steps[3].__class__.__name__ == "MayRepeatNTimesStep"

        repeat_step = steps[3]
        assert repeat_step.max_repeats == 2, "Should allow 2 repeats"
        assert repeat_step.repeats_done == 0, "Should start with 0 repeats done"

    def test_center_of_mass_structure(self, wasp_state):
        """Test that center_of_mass has correct step structure."""
        effect = CardEffectRegistry.get("center_of_mass")
        wasp = wasp_state.get_hero("wasp")
        card = make_center_of_mass_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Verify step types
        assert steps[0].__class__.__name__ == "SelectStep"  # Select Unit
        assert steps[1].__class__.__name__ == "SelectStep"  # Select Hex
        assert steps[2].__class__.__name__ == "PlaceUnitStep"  # Place
        assert steps[3].__class__.__name__ == "MayRepeatNTimesStep"  # Repeat

        # Verify repeat template only contains orbit steps (2 steps)
        repeat_step = steps[3]
        template = repeat_step.steps_template
        assert len(template) == 2
        assert template[0].__class__.__name__ == "SelectStep"
        assert template[1].__class__.__name__ == "PlaceUnitStep"

    def test_center_of_mass_uses_card_radius(self, wasp_state):
        """Test that center_of_mass uses the card's radius value (3)."""
        effect = CardEffectRegistry.get("center_of_mass")
        wasp = wasp_state.get_hero("wasp")
        card = make_center_of_mass_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Check unit select filter uses radius 3
        unit_select = steps[0]
        range_filter = next(
            (f for f in unit_select.filters if f.__class__.__name__ == "RangeFilter"),
            None,
        )
        assert range_filter is not None
        assert range_filter.max_range == 3, "Should use card's radius_value (3)"

    def test_center_of_mass_orbit_filters(self, wasp_state):
        """Test that orbit destination has correct filters."""
        effect = CardEffectRegistry.get("center_of_mass")
        wasp = wasp_state.get_hero("wasp")
        card = make_center_of_mass_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        hex_select = steps[1]

        # Verify AdjacencyToContextFilter
        assert any(
            f.__class__.__name__ == "AdjacencyToContextFilter"
            and f.target_key == "lift_target"
            for f in hex_select.filters
        )

        # Verify PreserveDistanceFilter
        assert any(
            f.__class__.__name__ == "PreserveDistanceFilter"
            and f.target_key == "lift_target"
            for f in hex_select.filters
        )

        # Verify OccupiedFilter (must be empty)
        assert any(
            f.__class__.__name__ == "ObstacleFilter" and f.is_obstacle is False
            for f in hex_select.filters
        )


# =============================================================================
# Kinetic Repulse Tests
# =============================================================================


def make_kinetic_repulse_card():
    """Create a Kinetic Repulse card (Tier II Blue Skill)."""
    return Card(
        id="kinetic_repulse",
        name="Kinetic Repulse",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 3},
        effect_id="kinetic_repulse",
        effect_text="Push up to 2 enemy units adjacent to you 3 spaces; if a pushed hero is stopped by an obstacle, that hero discards a card, if able.",
    )


class TestKineticRepulseEffect:
    """Tests for the Kinetic Repulse effect."""

    def test_kinetic_repulse_effect_registered(self):
        """Test that kinetic_repulse effect is properly registered."""
        effect = CardEffectRegistry.get("kinetic_repulse")
        assert effect is not None

    def test_kinetic_repulse_structure(self, wasp_state):
        """Test that kinetic_repulse returns correct step structure."""
        effect = CardEffectRegistry.get("kinetic_repulse")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_repulse_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 2 top-level steps: MultiSelectStep + ForEachStep
        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "MultiSelectStep"
        assert steps[1].__class__.__name__ == "ForEachStep"

    def test_kinetic_repulse_multi_select_config(self, wasp_state):
        """Test that MultiSelectStep is configured for up to 2 adjacent enemies."""
        effect = CardEffectRegistry.get("kinetic_repulse")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_repulse_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        multi_select = steps[0]

        # Up to 2 selections, optional
        assert multi_select.max_selections == 2
        assert multi_select.min_selections == 0
        assert multi_select.is_mandatory is False
        assert multi_select.output_key == "push_targets"

        # Check filters: Range 1 (adjacent) + Enemy
        has_range = any(
            f.__class__.__name__ == "RangeFilter" and f.max_range == 1
            for f in multi_select.filters
        )
        has_enemy = any(
            f.__class__.__name__ == "TeamFilter" and f.relation == "ENEMY"
            for f in multi_select.filters
        )
        assert has_range, "Must filter to adjacent units (range 1)"
        assert has_enemy, "Must filter to enemy units"

    def test_kinetic_repulse_foreach_template(self, wasp_state):
        """Test that ForEachStep template contains push and collision logic."""
        effect = CardEffectRegistry.get("kinetic_repulse")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_repulse_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        foreach_step = steps[1]

        assert foreach_step.list_key == "push_targets"
        assert foreach_step.item_key == "current_push_target"

        template = foreach_step.steps_template
        assert len(template) == 4

        # Step 1: PushUnitStep
        push_step = template[0]
        assert push_step.__class__.__name__ == "PushUnitStep"
        assert push_step.target_key == "current_push_target"
        assert push_step.distance == 3
        assert push_step.collision_output_key == "push_collision"

        # Step 2: CheckUnitTypeStep
        check_step = template[1]
        assert check_step.__class__.__name__ == "CheckUnitTypeStep"
        assert check_step.unit_key == "current_push_target"
        assert check_step.expected_type == "HERO"

        # Step 3: CombineBooleanContextStep
        combine_step = template[2]
        assert combine_step.__class__.__name__ == "CombineBooleanContextStep"
        assert combine_step.key_a == "push_collision"
        assert combine_step.key_b == "is_hero"
        assert combine_step.operation == "AND"

        # Step 4: ForceDiscardStep
        discard_step = template[3]
        assert discard_step.__class__.__name__ == "ForceDiscardStep"
        assert discard_step.victim_key == "current_push_target"
        assert discard_step.active_if_key == "should_discard"


# =============================================================================
# Kinetic Blast Tests
# =============================================================================


def make_kinetic_blast_card():
    """Create a Kinetic Blast card (Tier III Blue Skill)."""
    return Card(
        id="kinetic_blast",
        name="Kinetic Blast",
        tier=CardTier.III,
        color=CardColor.BLUE,
        initiative=11,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
        effect_id="kinetic_blast",
        effect_text="Push up to 2 enemy units adjacent to you 3 or 4 spaces; if a pushed hero is stopped by an obstacle, that hero discards a card, if able.",
    )


class TestKineticBlastEffect:
    """Tests for the Kinetic Blast effect."""

    def test_kinetic_blast_effect_registered(self):
        """Test that kinetic_blast effect is properly registered."""
        effect = CardEffectRegistry.get("kinetic_blast")
        assert effect is not None

    def test_kinetic_blast_structure(self, wasp_state):
        """Test that kinetic_blast returns correct step structure."""
        effect = CardEffectRegistry.get("kinetic_blast")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_blast_card()

        steps = effect.get_steps(wasp_state, wasp, card)

        # Should have 3 top-level steps: SelectStep (distance) + MultiSelectStep + ForEachStep
        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "MultiSelectStep"
        assert steps[2].__class__.__name__ == "ForEachStep"

    def test_kinetic_blast_distance_selection(self, wasp_state):
        """Test that first step selects push distance (3 or 4)."""
        effect = CardEffectRegistry.get("kinetic_blast")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_blast_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        distance_step = steps[0]

        # Should be a NUMBER selection with options 3 and 4
        from goa2.domain.models import TargetType

        assert distance_step.target_type == TargetType.NUMBER
        assert distance_step.output_key == "push_distance"
        assert distance_step.number_options == [3, 4]
        assert distance_step.is_mandatory is True

    def test_kinetic_blast_uses_distance_from_context(self, wasp_state):
        """Test that PushUnitStep reads distance from context."""
        effect = CardEffectRegistry.get("kinetic_blast")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_blast_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        foreach_step = steps[2]
        push_step = foreach_step.steps_template[0]

        # Should use distance_key instead of fixed distance
        assert push_step.distance_key == "push_distance"

    def test_kinetic_blast_same_collision_logic_as_repulse(self, wasp_state):
        """Test that Kinetic Blast has same collision/discard logic as Kinetic Repulse."""
        effect = CardEffectRegistry.get("kinetic_blast")
        wasp = wasp_state.get_hero("wasp")
        card = make_kinetic_blast_card()

        steps = effect.get_steps(wasp_state, wasp, card)
        foreach_step = steps[2]
        template = foreach_step.steps_template

        # Should have same 4-step template as Repulse
        assert len(template) == 4
        assert template[0].__class__.__name__ == "PushUnitStep"
        assert template[1].__class__.__name__ == "CheckUnitTypeStep"
        assert template[2].__class__.__name__ == "CombineBooleanContextStep"
        assert template[3].__class__.__name__ == "ForceDiscardStep"
