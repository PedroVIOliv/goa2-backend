"""
TopologyService: Dynamic board connectivity aware of reality splits.

This service wraps all distance/connectivity queries to respect active
TopologyConstraint effects (Nebkher's Crack in Reality, etc.).

The core idea is that Nebkher's "Crack in Reality" splits the board into
disconnected regions. Units on opposite sides of the split cannot interact
"as if the other side did not exist."

Regions:
- NEGATIVE: Hexes where axis coordinate < split_value
- ZERO: Hexes where axis coordinate == split_value (the "bridge")
- POSITIVE: Hexes where axis coordinate > split_value

Tier 2 (TOPOLOGY_SPLIT): NEGATIVE <-> POSITIVE blocked, ZERO bridges both
Tier 3 (TOPOLOGY_ISOLATION): Same as Tier 2 + isolated_hex only reachable from ZERO

Usage:
    from goa2.engine.topology import get_topology_service

    topo = get_topology_service()
    if topo.distance(origin, target, state) <= range:
        # Target is in range (and connected)

    # Or use the module-level convenience functions:
    from goa2.engine.topology import topology_distance, are_connected

    if topology_distance(origin, target, state) <= range:
        ...
"""

from __future__ import annotations
import math
from typing import List, Optional, TYPE_CHECKING, Union

from goa2.domain.hex import Hex
from goa2.domain.models.effect import ActiveEffect, EffectType, Shape

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class TopologyService:
    """
    Topology-aware distance and connectivity service.

    This service is the authority on whether two hexes can "see" each other
    given active topology constraints (like Nebkher's reality splits).

    All game logic that needs to check distance, adjacency, or connectivity
    should use this service instead of raw Hex.distance() calls.
    """

    # -------------------------------------------------------------------------
    # Primary API - Use these methods in game logic
    # -------------------------------------------------------------------------

    def distance(
        self, origin: Hex, target: Hex, state: "GameState"
    ) -> Union[int, float]:
        """
        Returns topology-aware distance between two hexes.

        Returns:
            int: The geometric distance if hexes are connected
            math.inf: If hexes are in disconnected components (cannot interact)

        Example:
            dist = topo.distance(attacker_hex, target_hex, state)
            if dist <= attack_range:
                # Can attack
        """
        if not self.are_connected(origin, target, state):
            return math.inf
        return origin.distance(target)

    def are_connected(self, origin: Hex, target: Hex, state: "GameState") -> bool:
        """
        Check if two hexes can interact given active topology constraints.

        This is the core connectivity check. Two hexes are connected if:
        1. No topology constraints exist, OR
        2. They are in the same region, OR
        3. At least one is in the ZERO region (bridge)

        Returns:
            True if hexes can interact, False if blocked by topology
        """
        for effect in state.active_effects:
            if effect.effect_type == EffectType.TOPOLOGY_SPLIT:
                if not self._check_split(origin, target, effect):
                    return False
            elif effect.effect_type == EffectType.TOPOLOGY_ISOLATION:
                if not self._check_isolation(origin, target, effect):
                    return False
        return True

    def are_adjacent(self, a: Hex, b: Hex, state: "GameState") -> bool:
        """
        Game-aware adjacency check: geometric adjacency + connectivity.

        Two hexes are adjacent for game purposes only if:
        1. They are geometrically adjacent (distance == 1), AND
        2. They are connected (not split by topology)

        Returns:
            True if hexes are adjacent and connected
        """
        if a.distance(b) != 1:
            return False
        return self.are_connected(a, b, state)

    def get_connected_neighbors(self, hex: Hex, state: "GameState") -> List[Hex]:
        """
        Returns geometric neighbors that are connected (not split off).

        Use this when you need to find adjacent hexes that a unit could
        potentially interact with (for auras, adjacency checks, etc.)

        Note: Does NOT check for obstacles or map boundaries.
        Use get_traversable_neighbors() for movement.
        """
        return [n for n in hex.neighbors() if self.are_connected(hex, n, state)]

    def get_connected_ring(
        self, center: Hex, radius: int, state: "GameState"
    ) -> List[Hex]:
        """
        Returns hexes at exactly `radius` distance that are connected.

        This is the topology-aware version of Hex.ring(). Use this when
        checking for units at a specific range that must be able to interact
        with the center (e.g., minion defense modifiers).

        Args:
            center: The center hex
            radius: The ring radius (1 = adjacent, 2 = two away, etc.)
            state: Game state

        Returns:
            List of hexes at exactly `radius` distance that are connected
        """
        return [h for h in center.ring(radius) if self.are_connected(center, h, state)]

    def get_traversable_neighbors(
        self,
        hex: Hex,
        state: "GameState",
        end_hex: Optional[Hex] = None,
        actor_id: Optional[str] = None,
        pass_through_obstacles: bool = False,
    ) -> List[Hex]:
        """
        Returns neighbors that can be traversed during movement.

        Combines three checks:
        1. Topology: Must be connected (not split off)
        2. Map bounds: Must be on the game map
        3. Obstacles: Must not be blocked (unless it's the destination
           or pass_through_obstacles is True)
           - Includes STATIC_BARRIER effects if actor_id is provided

        Args:
            hex: The current position
            state: Game state
            end_hex: Optional destination (obstacles are allowed if it's the end)
            actor_id: Optional actor ID for context-aware obstacle checking
            pass_through_obstacles: If True, allow traversing through obstacles
                (but not landing on them — destination check is separate)

        Returns:
            List of hexes that can be moved to from the current position
        """
        result = []
        for n in hex.neighbors():
            # Must be connected (topology check)
            if not self.are_connected(hex, n, state):
                continue

            # Must be on the map
            if not state.board.is_on_map(n):
                continue

            # Skip obstacle check entirely if pass_through_obstacles is enabled
            if not pass_through_obstacles:
                # Check obstacles (unless it's the destination)
                # Use context-aware check if validator available
                is_obs = False
                if state.validator:
                    is_obs = state.validator.is_obstacle_for_actor(state, n, actor_id)
                else:
                    tile = state.board.get_tile(n)
                    is_obs = tile.is_obstacle if tile else True

                if is_obs:
                    # Allow if this is the destination (for attacks, etc.)
                    if end_hex is not None and n == end_hex:
                        pass  # Allow
                    else:
                        continue

            result.append(n)
        return result

    def hex_in_scope(
        self,
        origin: Hex,
        target: Hex,
        scope_shape: Shape,
        scope_range: int,
        state: "GameState",
        direction: Optional[int] = None,
    ) -> bool:
        """
        Consolidated scope check for effects/auras.

        This replaces the duplicate _hex_in_scope() implementations in
        validation.py, stats.py, and steps.py.

        Args:
            origin: The origin hex of the effect
            target: The hex being checked
            scope_shape: The shape of the effect (POINT, RADIUS, etc.)
            scope_range: The range of the effect
            state: Game state
            direction: Direction index for LINE shapes (0-5)

        Returns:
            True if target is within scope of origin, respecting topology
        """
        if scope_shape == Shape.GLOBAL:
            # "Global" means "everywhere connected to source"
            # This is the key change: Global no longer means entire map
            return self.are_connected(origin, target, state)

        if scope_shape == Shape.POINT:
            return origin == target

        if scope_shape == Shape.ADJACENT:
            return self.are_adjacent(origin, target, state)

        if scope_shape == Shape.RADIUS:
            dist = self.distance(origin, target, state)
            return dist <= scope_range

        if scope_shape == Shape.LINE:
            if not origin.is_straight_line(target):
                return False
            dist = self.distance(origin, target, state)
            return dist <= scope_range

        if scope_shape == Shape.ZONE:
            # Zone checks are unaffected by topology
            # If they're in the same zone, they're in the same zone
            origin_zone = state.board.get_zone_for_hex(origin)
            target_zone = state.board.get_zone_for_hex(target)
            return origin_zone == target_zone and origin_zone is not None

        return False

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _get_region(self, hex: Hex, effect: ActiveEffect) -> str:
        """
        Determines which region a hex belongs to based on the split axis.

        Returns:
            "NEGATIVE": axis coordinate < split_value
            "ZERO": axis coordinate == split_value (the bridge)
            "POSITIVE": axis coordinate > split_value
        """
        axis = effect.split_axis
        if not axis or axis not in ("q", "r", "s"):
            return "ZERO"

        value = getattr(hex, axis)
        split_value = effect.split_value

        if value < split_value:
            return "NEGATIVE"
        elif value > split_value:
            return "POSITIVE"
        else:
            return "ZERO"

    def _check_split(self, origin: Hex, target: Hex, effect: ActiveEffect) -> bool:
        """
        Tier 2 (Crack in Reality): NEGATIVE <-> POSITIVE blocked, ZERO is bridge.

        The split creates three regions:
        - NEGATIVE can interact with NEGATIVE and ZERO
        - POSITIVE can interact with POSITIVE and ZERO
        - ZERO can interact with everyone (it's the bridge)
        - NEGATIVE cannot interact with POSITIVE directly

        Returns:
            True if connected (can interact), False if blocked
        """
        origin_region = self._get_region(origin, effect)
        target_region = self._get_region(target, effect)

        # Block NEGATIVE <-> POSITIVE direct interaction
        if origin_region == "POSITIVE" and target_region == "NEGATIVE":
            return False
        if origin_region == "NEGATIVE" and target_region == "POSITIVE":
            return False

        return True

    def _check_isolation(self, origin: Hex, target: Hex, effect: ActiveEffect) -> bool:
        """
        Tier 3 (Shift Reality): Same as split + isolated_hex only reachable from ZERO.

        This adds an additional rule: the caster's hex (isolated_hex) can only
        be interacted with from the ZERO region. Units on either side cannot
        target or reach the caster directly.

        Returns:
            True if connected (can interact), False if blocked
        """
        # First apply base split rules
        if not self._check_split(origin, target, effect):
            return False

        # Then check isolation of the specific hex (typically Nebkher's position)
        if effect.isolated_hex:
            # If targeting the isolated hex, origin must be in ZERO region
            if target == effect.isolated_hex:
                origin_region = self._get_region(origin, effect)
                if origin_region != "ZERO":
                    return False

            # If originating from the isolated hex, target must be in ZERO region
            # (Nebkher can only interact with the bridge too)
            if origin == effect.isolated_hex:
                target_region = self._get_region(target, effect)
                if target_region != "ZERO":
                    return False

        return True


# -----------------------------------------------------------------------------
# Singleton and Module-Level Convenience Functions
# -----------------------------------------------------------------------------

_topology_service: Optional[TopologyService] = None


def get_topology_service() -> TopologyService:
    """
    Get the global TopologyService instance.

    The service is stateless, so a singleton is fine.
    """
    global _topology_service
    if _topology_service is None:
        _topology_service = TopologyService()
    return _topology_service


# Convenience functions for common operations
# These allow `from goa2.engine.topology import topology_distance` usage


def topology_distance(
    origin: Hex, target: Hex, state: "GameState"
) -> Union[int, float]:
    """Module-level convenience for TopologyService.distance()."""
    return get_topology_service().distance(origin, target, state)


def are_connected(origin: Hex, target: Hex, state: "GameState") -> bool:
    """Module-level convenience for TopologyService.are_connected()."""
    return get_topology_service().are_connected(origin, target, state)


def are_adjacent(a: Hex, b: Hex, state: "GameState") -> bool:
    """Module-level convenience for TopologyService.are_adjacent()."""
    return get_topology_service().are_adjacent(a, b, state)


def get_connected_neighbors(hex: Hex, state: "GameState") -> List[Hex]:
    """Module-level convenience for TopologyService.get_connected_neighbors()."""
    return get_topology_service().get_connected_neighbors(hex, state)


def get_traversable_neighbors(
    hex: Hex, state: "GameState", end_hex: Optional[Hex] = None
) -> List[Hex]:
    """Module-level convenience for TopologyService.get_traversable_neighbors()."""
    return get_topology_service().get_traversable_neighbors(hex, state, end_hex)


def get_connected_ring(center: Hex, radius: int, state: "GameState") -> List[Hex]:
    """Module-level convenience for TopologyService.get_connected_ring()."""
    return get_topology_service().get_connected_ring(center, radius, state)


def hex_in_scope(
    origin: Hex,
    target: Hex,
    scope_shape: Shape,
    scope_range: int,
    state: "GameState",
    direction: Optional[int] = None,
) -> bool:
    """Module-level convenience for TopologyService.hex_in_scope()."""
    return get_topology_service().hex_in_scope(
        origin, target, scope_shape, scope_range, state, direction
    )
