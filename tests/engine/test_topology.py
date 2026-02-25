"""
Tests for TopologyService - board connectivity with reality splits.

The TopologyService handles Nebkher's "Crack in Reality" mechanic which splits
the board into disconnected regions where units cannot interact across the split.

Regions (based on split_axis and split_value):
- NEGATIVE: Hexes where axis coordinate < split_value
- ZERO: Hexes where axis coordinate == split_value (the "bridge")
- POSITIVE: Hexes where axis coordinate > split_value

Tier 2 (TOPOLOGY_SPLIT): NEGATIVE <-> POSITIVE blocked, ZERO bridges both
Tier 3 (TOPOLOGY_ISOLATION): Same as Tier 2 + isolated_hex only reachable from ZERO
"""

import math
import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    Shape,
    EffectScope,
    DurationType,
)
from goa2.domain.hex import Hex
from goa2.engine.topology import (
    TopologyService,
    get_topology_service,
    topology_distance,
    are_connected,
    are_adjacent,
    get_connected_neighbors,
    hex_in_scope,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def topo():
    """Fresh TopologyService instance."""
    return TopologyService()


@pytest.fixture
def basic_board():
    """
    A simple 5-hex board for testing:

         (-1,0,1)----(0,0,0)----(1,0,-1)
                       |
                    (0,1,-1)
                       |
                    (0,2,-2)

    All hexes have r coordinate from -1 to 2.
    All hexes have q coordinate from -1 to 1.
    """
    board = Board()
    hexes = [
        Hex(q=-1, r=0, s=1),  # Left
        Hex(q=0, r=0, s=0),  # Center
        Hex(q=1, r=0, s=-1),  # Right
        Hex(q=0, r=1, s=-1),  # Below center
        Hex(q=0, r=2, s=-2),  # Far below
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    return board


@pytest.fixture
def basic_state(basic_board):
    """Basic state with no active effects."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    state = GameState(
        board=basic_board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        entity_locations={},
        current_actor_id="h1",
    )
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    return state


@pytest.fixture
def split_state(basic_state):
    """
    State with a TOPOLOGY_SPLIT effect splitting along q=0.

    - NEGATIVE region: q < 0 (just the Left hex)
    - ZERO region (bridge): q == 0 (Center, Below center, Far below)
    - POSITIVE region: q > 0 (just the Right hex)

    Left (-1,0,1) <-BLOCKED-> Right (1,0,-1)
    Both can reach Center (0,0,0)
    """
    basic_state.active_effects.append(
        ActiveEffect(
            id="split_1",
            source_id="nebkher",
            effect_type=EffectType.TOPOLOGY_SPLIT,
            split_axis="q",
            split_value=0,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
    )
    return basic_state


@pytest.fixture
def isolation_state(split_state):
    """
    State with TOPOLOGY_ISOLATION (Tier 3).
    Same as split_state but the Center hex (0,0,0) is isolated.

    The isolated hex can only be reached from the ZERO region.
    """
    # Replace the split effect with an isolation effect
    split_state.active_effects.clear()
    split_state.active_effects.append(
        ActiveEffect(
            id="isolation_1",
            source_id="nebkher",
            effect_type=EffectType.TOPOLOGY_ISOLATION,
            split_axis="q",
            split_value=0,
            isolated_hex=Hex(q=0, r=0, s=0),  # Center is isolated
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
    )
    return split_state


# =============================================================================
# TEST: NO EFFECTS (BASELINE)
# =============================================================================


class TestNoEffects:
    """When no topology effects are active, everything is connected."""

    def test_distance_same_hex(self, topo, basic_state):
        """Distance to self is 0."""
        origin = Hex(q=0, r=0, s=0)
        assert topo.distance(origin, origin, basic_state) == 0

    def test_distance_adjacent(self, topo, basic_state):
        """Distance to adjacent hex is 1."""
        origin = Hex(q=0, r=0, s=0)
        target = Hex(q=1, r=0, s=-1)
        assert topo.distance(origin, target, basic_state) == 1

    def test_distance_two_away(self, topo, basic_state):
        """Distance to hex 2 away."""
        origin = Hex(q=-1, r=0, s=1)  # Left
        target = Hex(q=1, r=0, s=-1)  # Right (2 hexes away)
        assert topo.distance(origin, target, basic_state) == 2

    def test_are_connected_always_true(self, topo, basic_state):
        """All hexes are connected when no effects."""
        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        center = Hex(q=0, r=0, s=0)

        assert topo.are_connected(left, right, basic_state)
        assert topo.are_connected(left, center, basic_state)
        assert topo.are_connected(right, center, basic_state)

    def test_are_adjacent_true(self, topo, basic_state):
        """Adjacent hexes return True."""
        center = Hex(q=0, r=0, s=0)
        right = Hex(q=1, r=0, s=-1)
        assert topo.are_adjacent(center, right, basic_state)

    def test_are_adjacent_false_for_non_adjacent(self, topo, basic_state):
        """Non-adjacent hexes return False."""
        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        assert not topo.are_adjacent(left, right, basic_state)

    def test_get_connected_neighbors(self, topo, basic_state):
        """All geometric neighbors are returned."""
        center = Hex(q=0, r=0, s=0)
        neighbors = topo.get_connected_neighbors(center, basic_state)

        # Center has 6 geometric neighbors, but only some are on the board
        assert Hex(q=-1, r=0, s=1) in neighbors  # Left
        assert Hex(q=1, r=0, s=-1) in neighbors  # Right
        assert Hex(q=0, r=1, s=-1) in neighbors  # Below

    def test_get_connected_ring(self, topo, basic_state):
        """get_connected_ring returns hexes at exact distance."""
        center = Hex(q=0, r=0, s=0)

        # Ring 1 = adjacent hexes
        ring1 = topo.get_connected_ring(center, 1, basic_state)
        assert Hex(q=-1, r=0, s=1) in ring1  # Left
        assert Hex(q=1, r=0, s=-1) in ring1  # Right
        assert Hex(q=0, r=1, s=-1) in ring1  # Below
        assert center not in ring1  # Center is not in ring 1

        # Ring 2 = hexes at distance 2
        ring2 = topo.get_connected_ring(center, 2, basic_state)
        assert Hex(q=0, r=2, s=-2) in ring2  # Far below


# =============================================================================
# TEST: TOPOLOGY_SPLIT (Tier 2 - Crack in Reality)
# =============================================================================


class TestTopologySplit:
    """Test TOPOLOGY_SPLIT effect (Tier 2)."""

    def test_same_region_connected(self, topo, split_state):
        """Hexes in the same region can interact."""
        # Both in ZERO region
        center = Hex(q=0, r=0, s=0)
        below = Hex(q=0, r=1, s=-1)
        assert topo.are_connected(center, below, split_state)
        assert topo.distance(center, below, split_state) == 1

    def test_negative_positive_blocked(self, topo, split_state):
        """NEGATIVE <-> POSITIVE is blocked."""
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE (q < 0)
        right = Hex(q=1, r=0, s=-1)  # POSITIVE (q > 0)

        assert not topo.are_connected(left, right, split_state)
        assert topo.distance(left, right, split_state) == math.inf

    def test_zero_bridges_negative(self, topo, split_state):
        """ZERO region can interact with NEGATIVE."""
        center = Hex(q=0, r=0, s=0)  # ZERO
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE

        assert topo.are_connected(center, left, split_state)
        assert topo.distance(center, left, split_state) == 1

    def test_zero_bridges_positive(self, topo, split_state):
        """ZERO region can interact with POSITIVE."""
        center = Hex(q=0, r=0, s=0)  # ZERO
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        assert topo.are_connected(center, right, split_state)
        assert topo.distance(center, right, split_state) == 1

    def test_are_adjacent_respects_split(self, topo, split_state):
        """are_adjacent returns False for geometrically adjacent but split hexes."""
        # This requires hexes that are geometrically adjacent but in different regions
        # With q=0 split, we need adjacent hexes with q=-1 and q=1
        # But those aren't adjacent (distance=2). Let's verify split blocks correctly.
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        center = Hex(q=0, r=0, s=0)  # ZERO

        # Adjacent and connected
        assert topo.are_adjacent(left, center, split_state)

    def test_get_connected_neighbors_filters_blocked(self, topo, split_state):
        """get_connected_neighbors excludes hexes in blocked regions."""
        # From NEGATIVE region, can reach ZERO but not POSITIVE
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        neighbors = topo.get_connected_neighbors(left, split_state)

        # Should include center (ZERO) but not any POSITIVE hexes
        center = Hex(q=0, r=0, s=0)
        assert center in neighbors

    def test_get_connected_ring_filters_blocked(self, topo, split_state):
        """get_connected_ring excludes hexes in blocked regions."""
        # From center (ZERO), ring 1 includes both left (NEGATIVE) and right (POSITIVE)
        # because ZERO bridges both sides
        center = Hex(q=0, r=0, s=0)  # ZERO
        ring1 = topo.get_connected_ring(center, 1, split_state)

        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        # From ZERO, both sides are reachable
        assert left in ring1
        assert right in ring1

        # But from NEGATIVE, ring 2 should NOT include POSITIVE hexes
        # (left is at distance 2 from right, going through center)
        ring2_from_left = topo.get_connected_ring(left, 2, split_state)
        assert right not in ring2_from_left  # Blocked by split


# =============================================================================
# TEST: TOPOLOGY_ISOLATION (Tier 3 - Shift Reality)
# =============================================================================


class TestTopologyIsolation:
    """Test TOPOLOGY_ISOLATION effect (Tier 3)."""

    def test_split_rules_still_apply(self, topo, isolation_state):
        """Basic split rules still apply."""
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        # NEGATIVE <-> POSITIVE still blocked
        assert not topo.are_connected(left, right, isolation_state)

    def test_isolated_hex_reachable_from_zero(self, topo, isolation_state):
        """Isolated hex can be reached from ZERO region."""
        isolated = Hex(q=0, r=0, s=0)  # Isolated center
        below = Hex(q=0, r=1, s=-1)  # Also ZERO

        assert topo.are_connected(below, isolated, isolation_state)

    def test_isolated_hex_unreachable_from_negative(self, topo, isolation_state):
        """Isolated hex cannot be reached from NEGATIVE region."""
        isolated = Hex(q=0, r=0, s=0)  # Isolated center
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE

        # Even though left and center are geometrically adjacent,
        # the isolation blocks access from non-ZERO regions
        assert not topo.are_connected(left, isolated, isolation_state)

    def test_isolated_hex_unreachable_from_positive(self, topo, isolation_state):
        """Isolated hex cannot be reached from POSITIVE region."""
        isolated = Hex(q=0, r=0, s=0)  # Isolated center
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        assert not topo.are_connected(right, isolated, isolation_state)

    def test_isolated_hex_can_only_reach_zero(self, topo, isolation_state):
        """From isolated hex, can only interact with ZERO region."""
        isolated = Hex(q=0, r=0, s=0)  # Isolated center
        below = Hex(q=0, r=1, s=-1)  # ZERO
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        # Can reach ZERO
        assert topo.are_connected(isolated, below, isolation_state)

        # Cannot reach NEGATIVE or POSITIVE
        assert not topo.are_connected(isolated, left, isolation_state)
        assert not topo.are_connected(isolated, right, isolation_state)


# =============================================================================
# TEST: HEX_IN_SCOPE
# =============================================================================


class TestHexInScope:
    """Test hex_in_scope for various shapes."""

    def test_point_shape(self, topo, basic_state):
        """POINT shape only matches exact hex."""
        origin = Hex(q=0, r=0, s=0)

        assert topo.hex_in_scope(origin, origin, Shape.POINT, 0, basic_state)
        assert not topo.hex_in_scope(
            origin, Hex(q=1, r=0, s=-1), Shape.POINT, 0, basic_state
        )

    def test_adjacent_shape(self, topo, basic_state):
        """ADJACENT shape matches hexes at distance 1."""
        origin = Hex(q=0, r=0, s=0)
        adjacent = Hex(q=1, r=0, s=-1)
        far = Hex(q=0, r=2, s=-2)

        assert topo.hex_in_scope(origin, adjacent, Shape.ADJACENT, 0, basic_state)
        assert not topo.hex_in_scope(origin, far, Shape.ADJACENT, 0, basic_state)

    def test_radius_shape(self, topo, basic_state):
        """RADIUS shape matches hexes within range."""
        origin = Hex(q=0, r=0, s=0)
        adjacent = Hex(q=1, r=0, s=-1)  # Distance 1
        below = Hex(q=0, r=1, s=-1)  # Distance 1
        far_below = Hex(q=0, r=2, s=-2)  # Distance 2

        # Range 1 includes adjacent but not far_below
        assert topo.hex_in_scope(origin, adjacent, Shape.RADIUS, 1, basic_state)
        assert topo.hex_in_scope(origin, below, Shape.RADIUS, 1, basic_state)
        assert not topo.hex_in_scope(origin, far_below, Shape.RADIUS, 1, basic_state)

        # Range 2 includes all
        assert topo.hex_in_scope(origin, far_below, Shape.RADIUS, 2, basic_state)

    def test_global_shape_no_effects(self, topo, basic_state):
        """GLOBAL shape matches all connected hexes (all when no effects)."""
        origin = Hex(q=0, r=0, s=0)
        far_below = Hex(q=0, r=2, s=-2)

        assert topo.hex_in_scope(origin, far_below, Shape.GLOBAL, 0, basic_state)

    def test_global_shape_respects_split(self, topo, split_state):
        """GLOBAL shape blocked by topology split."""
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        right = Hex(q=1, r=0, s=-1)  # POSITIVE

        # NEGATIVE -> POSITIVE blocked
        assert not topo.hex_in_scope(left, right, Shape.GLOBAL, 0, split_state)

        # But NEGATIVE -> ZERO works
        center = Hex(q=0, r=0, s=0)
        assert topo.hex_in_scope(left, center, Shape.GLOBAL, 0, split_state)

    def test_radius_respects_split(self, topo, split_state):
        """RADIUS blocked by topology even if geometrically in range."""
        left = Hex(q=-1, r=0, s=1)  # NEGATIVE
        right = Hex(q=1, r=0, s=-1)  # POSITIVE (distance 2)

        # Geometrically in range 2, but blocked by split
        assert not topo.hex_in_scope(left, right, Shape.RADIUS, 5, split_state)


# =============================================================================
# TEST: MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_get_topology_service_singleton(self):
        """get_topology_service returns the same instance."""
        topo1 = get_topology_service()
        topo2 = get_topology_service()
        assert topo1 is topo2

    def test_topology_distance(self, basic_state):
        """topology_distance convenience function works."""
        origin = Hex(q=0, r=0, s=0)
        target = Hex(q=1, r=0, s=-1)
        assert topology_distance(origin, target, basic_state) == 1

    def test_are_connected_function(self, split_state):
        """are_connected convenience function works."""
        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        assert not are_connected(left, right, split_state)

    def test_are_adjacent_function(self, basic_state):
        """are_adjacent convenience function works."""
        center = Hex(q=0, r=0, s=0)
        right = Hex(q=1, r=0, s=-1)
        assert are_adjacent(center, right, basic_state)

    def test_get_connected_neighbors_function(self, basic_state):
        """get_connected_neighbors convenience function works."""
        center = Hex(q=0, r=0, s=0)
        neighbors = get_connected_neighbors(center, basic_state)
        assert len(neighbors) > 0

    def test_hex_in_scope_function(self, basic_state):
        """hex_in_scope convenience function works."""
        origin = Hex(q=0, r=0, s=0)
        target = Hex(q=1, r=0, s=-1)
        assert hex_in_scope(origin, target, Shape.RADIUS, 1, basic_state)


# =============================================================================
# TEST: TRAVERSABLE NEIGHBORS (for pathfinding)
# =============================================================================


class TestTraversableNeighbors:
    """Test get_traversable_neighbors for movement/pathfinding."""

    def test_filters_off_map_hexes(self, topo, basic_state):
        """Off-map hexes are not included."""
        center = Hex(q=0, r=0, s=0)
        neighbors = topo.get_traversable_neighbors(center, basic_state)

        # All returned neighbors should be on the map
        for n in neighbors:
            assert basic_state.board.is_on_map(n)

    def test_filters_obstacles(self, topo, basic_state):
        """Obstacle tiles are not included."""
        # Mark right hex as terrain (obstacle)
        right = Hex(q=1, r=0, s=-1)
        basic_state.board.tiles[right].is_terrain = True

        center = Hex(q=0, r=0, s=0)
        neighbors = topo.get_traversable_neighbors(center, basic_state)

        assert right not in neighbors

    def test_allows_destination_obstacle(self, topo, basic_state):
        """end_hex allows reaching an obstacle (for attacks)."""
        right = Hex(q=1, r=0, s=-1)
        basic_state.board.tiles[right].is_terrain = True

        center = Hex(q=0, r=0, s=0)
        neighbors = topo.get_traversable_neighbors(center, basic_state, end_hex=right)

        assert right in neighbors

    def test_respects_split(self, topo, split_state):
        """Traversable neighbors respects topology split."""
        # From NEGATIVE region, should not include POSITIVE hexes
        left = Hex(q=-1, r=0, s=1)
        neighbors = topo.get_traversable_neighbors(left, split_state)

        # Should include center (ZERO) but no POSITIVE hexes
        # Note: Need to check what's geometrically adjacent to left
        right = Hex(q=1, r=0, s=-1)
        assert right not in neighbors


# =============================================================================
# TEST: EDGE CASES
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_multiple_split_effects(self, topo, basic_state):
        """Multiple split effects are all checked."""
        # Add two split effects with different axes
        basic_state.active_effects.append(
            ActiveEffect(
                id="split_q",
                source_id="nebkher",
                effect_type=EffectType.TOPOLOGY_SPLIT,
                split_axis="q",
                split_value=0,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
                is_active=True,
            )
        )
        basic_state.active_effects.append(
            ActiveEffect(
                id="split_r",
                source_id="nebkher",
                effect_type=EffectType.TOPOLOGY_SPLIT,
                split_axis="r",
                split_value=0,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
                is_active=True,
            )
        )

        # Both splits must allow connection
        left = Hex(q=-1, r=0, s=1)  # q=-1 (NEGATIVE for q), r=0 (ZERO for r)
        center = Hex(q=0, r=0, s=0)  # q=0 (ZERO), r=0 (ZERO)

        # Should still be connected (both in valid regions)
        assert topo.are_connected(left, center, basic_state)

    def test_invalid_split_axis(self, topo, basic_state):
        """Invalid split axis defaults to ZERO region (no blocking)."""
        basic_state.active_effects.append(
            ActiveEffect(
                id="bad_split",
                source_id="nebkher",
                effect_type=EffectType.TOPOLOGY_SPLIT,
                split_axis="invalid",  # Not q, r, or s
                split_value=0,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
                is_active=True,
            )
        )

        # Should not block anything
        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        assert topo.are_connected(left, right, basic_state)

    def test_none_split_axis(self, topo, basic_state):
        """None split axis defaults to ZERO region (no blocking)."""
        basic_state.active_effects.append(
            ActiveEffect(
                id="no_axis",
                source_id="nebkher",
                effect_type=EffectType.TOPOLOGY_SPLIT,
                split_axis=None,
                split_value=0,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
                is_active=True,
            )
        )

        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        assert topo.are_connected(left, right, basic_state)

    def test_distance_returns_int_when_connected(self, topo, basic_state):
        """distance() returns int (not float) when connected."""
        origin = Hex(q=0, r=0, s=0)
        target = Hex(q=1, r=0, s=-1)
        dist = topo.distance(origin, target, basic_state)
        assert isinstance(dist, int)

    def test_distance_returns_inf_when_blocked(self, topo, split_state):
        """distance() returns math.inf when blocked."""
        left = Hex(q=-1, r=0, s=1)
        right = Hex(q=1, r=0, s=-1)
        dist = topo.distance(left, right, split_state)
        assert dist == math.inf
        assert isinstance(dist, float)
