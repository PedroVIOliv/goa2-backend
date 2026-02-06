"""
Tests for Wasp's Static Barrier effect.

Card Text: "This turn: While an enemy hero outside of radius is performing
an action, spaces in radius count as obstacles. While an enemy hero in radius
is performing an action, spaces outside of radius count as obstacles."

Key test scenarios:
1. Actor outside radius sees inside hexes as obstacles
2. Actor inside radius sees outside hexes as obstacles
3. Friendly units are unaffected
4. Minions are unaffected (only heroes)
5. Effect expires at turn end
6. Movement blocked by barrier
7. Push collision with barrier
8. Units can be trapped by barrier
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Minion,
    MinionType,
)
from goa2.domain.models.effect import (
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import CreateEffectStep, ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effect_manager import EffectManager
import goa2.scripts.wasp_effects  # noqa: F401 - Register wasp effects


@pytest.fixture
def static_barrier_state():
    """
    Board setup (line of hexes):
    - (0,0,0): Wasp (barrier origin, radius 2)
    - (1,0,-1): Distance 1 from Wasp (inside radius)
    - (2,0,-2): Distance 2 from Wasp (inside radius - boundary)
    - (3,0,-3): Distance 3 from Wasp (outside radius)
    - (4,0,-4): Distance 4 from Wasp (outside radius)
    - (5,0,-5): Distance 5 from Wasp (outside radius)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=4, r=0, s=-4),
        Hex(q=5, r=0, s=-5),
        # Add some neighbors for movement tests
        Hex(q=0, r=1, s=-1),
        Hex(q=1, r=1, s=-2),
        Hex(q=2, r=1, s=-3),
        Hex(q=3, r=1, s=-4),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    wasp = Hero(id="hero_wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="static_barrier",
        name="Static Barrier",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=13,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        radius_value=2,
        effect_id="static_barrier",
        effect_text="This turn: While an enemy hero outside of radius is performing an action, spaces in radius count as obstacles. While an enemy hero in radius is performing an action, spaces outside of radius count as obstacles.",
        is_facedown=False,
    )
    wasp.current_turn_card = card

    # Enemy heroes at various distances
    enemy_inside = Hero(
        id="enemy_inside", name="Enemy Inside", team=TeamColor.BLUE, deck=[], level=1
    )
    enemy_outside = Hero(
        id="enemy_outside", name="Enemy Outside", team=TeamColor.BLUE, deck=[], level=1
    )

    # Friendly hero for testing friendly unaffected
    friendly = Hero(
        id="friendly", name="Friendly", team=TeamColor.RED, deck=[], level=1
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[wasp, friendly], minions=[]
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy_inside, enemy_outside], minions=[]
            ),
        },
    )

    state.place_entity("hero_wasp", Hex(q=0, r=0, s=0))
    # enemy_inside at distance 1 (inside radius 2)
    state.place_entity("enemy_inside", Hex(q=1, r=0, s=-1))
    # enemy_outside at distance 4 (outside radius 2)
    state.place_entity("enemy_outside", Hex(q=4, r=0, s=-4))
    # friendly at distance 3 (should be unaffected)
    state.place_entity("friendly", Hex(q=3, r=0, s=-3))

    state.current_actor_id = "hero_wasp"
    return state


def create_static_barrier_effect(state: GameState, radius: int = 2) -> None:
    """Helper to create the Static Barrier effect."""
    EffectManager.create_effect(
        state=state,
        source_id="hero_wasp",
        effect_type=EffectType.STATIC_BARRIER,
        scope=EffectScope(
            shape=Shape.GLOBAL,
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        barrier_radius=radius,
        barrier_origin_id="hero_wasp",
        is_active=True,  # Activate immediately for tests
    )


class TestStaticBarrierBasics:
    """Basic Static Barrier effect tests."""

    def test_effect_created_with_correct_fields(self, static_barrier_state):
        """Verify effect is created with correct barrier fields."""
        state = static_barrier_state
        create_static_barrier_effect(state, radius=2)

        assert len(state.active_effects) == 1
        effect = state.active_effects[0]
        assert effect.effect_type == EffectType.STATIC_BARRIER
        assert effect.barrier_radius == 2
        assert effect.barrier_origin_id == "hero_wasp"
        assert effect.duration == DurationType.THIS_TURN

    def test_effect_expires_at_turn_end(self, static_barrier_state):
        """Verify effect is removed at end of turn."""
        state = static_barrier_state
        create_static_barrier_effect(state, radius=2)

        assert len(state.active_effects) == 1

        # Expire THIS_TURN effects
        EffectManager.expire_effects(state, DurationType.THIS_TURN)

        assert len(state.active_effects) == 0


class TestStaticBarrierObstacleChecks:
    """Test is_obstacle_for_actor logic."""

    def test_actor_outside_radius_sees_inside_as_obstacles(self, static_barrier_state):
        """Enemy hero OUTSIDE radius sees hexes INSIDE radius as obstacles."""
        state = static_barrier_state
        create_static_barrier_effect(state, radius=2)

        # enemy_outside is at distance 4 (OUTSIDE radius 2)
        # Hexes at distance 0-2 should be obstacles for this actor

        # Wasp's position (distance 0) - should be obstacle
        hex_at_wasp = Hex(q=0, r=0, s=0)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_at_wasp, "enemy_outside")
            is True
        )

        # Distance 1 - should be obstacle
        hex_dist_1 = Hex(q=1, r=0, s=-1)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_1, "enemy_outside")
            is True
        )

        # Distance 2 (boundary) - should be obstacle
        hex_dist_2 = Hex(q=2, r=0, s=-2)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_2, "enemy_outside")
            is True
        )

        # Distance 3 - should NOT be obstacle (outside radius)
        hex_dist_3 = Hex(q=3, r=0, s=-3)
        # Note: This hex is occupied by 'friendly' so base is_obstacle is True
        # But the barrier itself should not block it
        # We need an empty hex at distance 3
        hex_dist_3_empty = Hex(q=3, r=1, s=-4)
        result = state.validator.is_obstacle_for_actor(
            state, hex_dist_3_empty, "enemy_outside"
        )
        assert result is False

    def test_actor_inside_radius_sees_outside_as_obstacles(self, static_barrier_state):
        """Enemy hero INSIDE radius sees hexes OUTSIDE radius as obstacles."""
        state = static_barrier_state
        create_static_barrier_effect(state, radius=2)

        # enemy_inside is at distance 1 (INSIDE radius 2)
        # Hexes at distance 3+ should be obstacles for this actor

        # Distance 3 - should be obstacle
        hex_dist_3 = Hex(q=3, r=1, s=-4)  # Empty hex at distance 3
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_3, "enemy_inside")
            is True
        )

        # Distance 4 - should be obstacle
        # enemy_outside is there, but barrier should still apply
        hex_dist_4 = Hex(q=4, r=0, s=-4)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_4, "enemy_inside")
            is True
        )

        # Distance 5 - should be obstacle
        hex_dist_5 = Hex(q=5, r=0, s=-5)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_5, "enemy_inside")
            is True
        )

        # Distance 0-2 - should NOT be obstacle (inside radius)
        hex_dist_0 = Hex(q=0, r=1, s=-1)  # Empty hex adjacent to Wasp
        result = state.validator.is_obstacle_for_actor(
            state, hex_dist_0, "enemy_inside"
        )
        # Should only be obstacle if occupied - not from barrier
        assert result is False

    def test_friendly_actors_unaffected(self, static_barrier_state):
        """Friendly heroes should not see barrier obstacles."""
        state = static_barrier_state
        create_static_barrier_effect(state, radius=2)

        # friendly is at distance 3 (outside radius)
        # but should not be affected by the barrier

        # Check hexes inside radius - should not be obstacle for friendly
        hex_at_wasp = Hex(q=0, r=1, s=-1)  # Empty, distance 1
        result = state.validator.is_obstacle_for_actor(state, hex_at_wasp, "friendly")
        assert result is False

        # Check hexes outside radius - should not be obstacle for friendly
        hex_outside = Hex(q=5, r=0, s=-5)  # Empty, distance 5
        result = state.validator.is_obstacle_for_actor(state, hex_outside, "friendly")
        assert result is False


class TestStaticBarrierWithMinions:
    """Test that minions are unaffected."""

    def test_minions_not_affected_by_barrier(self, static_barrier_state):
        """Minions should not see barrier obstacles."""
        state = static_barrier_state

        # Add an enemy minion
        minion = Minion(
            id="enemy_minion",
            name="Minion",
            team=TeamColor.BLUE,
            type=MinionType.MELEE,
        )
        state.teams[TeamColor.BLUE].minions.append(minion)
        state.place_entity("enemy_minion", Hex(q=5, r=0, s=-5))  # Distance 5

        create_static_barrier_effect(state, radius=2)

        # Minion should not be affected by barrier (only heroes are)
        hex_inside = Hex(q=0, r=1, s=-1)  # Empty, distance 1
        result = state.validator.is_obstacle_for_actor(
            state, hex_inside, "enemy_minion"
        )
        assert result is False


class TestStaticBarrierEffectCreation:
    """Test the StaticBarrierEffect card effect."""

    def test_effect_builds_correct_steps(self, static_barrier_state):
        """Verify the effect creates the correct CreateEffectStep."""
        from goa2.scripts.wasp_effects import StaticBarrierEffect
        from goa2.engine.stats import CardStats

        state = static_barrier_state
        wasp = state.get_hero("hero_wasp")
        card = wasp.current_turn_card

        effect = StaticBarrierEffect()
        stats = CardStats(
            primary_value=0,
            range=0,
            radius=2,
        )

        steps = effect.build_steps(state, wasp, card, stats)

        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, CreateEffectStep)
        assert step.effect_type == EffectType.STATIC_BARRIER
        assert step.barrier_radius == 2
        assert step.barrier_origin_id == "hero_wasp"
        assert step.duration == DurationType.THIS_TURN


class TestStaticBarrierOnBoundary:
    """Test edge cases at the radius boundary."""

    def test_actor_exactly_on_boundary(self, static_barrier_state):
        """Actor exactly at radius distance should be considered INSIDE."""
        state = static_barrier_state

        # Move enemy_inside to exactly distance 2 (on the boundary)
        state.move_unit("enemy_inside", Hex(q=2, r=0, s=-2))
        create_static_barrier_effect(state, radius=2)

        # Actor at distance 2 is INSIDE (distance <= radius)
        # So hexes OUTSIDE (distance > 2) should be obstacles

        # Distance 3 - should be obstacle
        hex_dist_3 = Hex(q=3, r=0, s=-3)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_dist_3, "enemy_inside")
            is True
        )

        # Distance 2 - should NOT be obstacle (same distance = inside)
        # Use (1, 1, -2) which is also at distance 2 from origin
        hex_dist_2_other = Hex(q=1, r=1, s=-2)
        result = state.validator.is_obstacle_for_actor(
            state, hex_dist_2_other, "enemy_inside"
        )
        assert result is False


class TestStaticBarrierNoEffectWithoutBarrier:
    """Test that without the effect, obstacles work normally."""

    def test_no_barrier_normal_obstacle_check(self, static_barrier_state):
        """Without barrier effect, obstacle check should be normal."""
        state = static_barrier_state
        # No barrier effect created

        # Empty hex should not be obstacle for any actor
        hex_empty = Hex(q=2, r=1, s=-3)
        assert (
            state.validator.is_obstacle_for_actor(state, hex_empty, "enemy_outside")
            is False
        )
        assert (
            state.validator.is_obstacle_for_actor(state, hex_empty, "enemy_inside")
            is False
        )

        # Occupied hex should be obstacle (base check)
        hex_occupied = Hex(q=0, r=0, s=0)  # Wasp's position
        assert (
            state.validator.is_obstacle_for_actor(state, hex_occupied, "enemy_outside")
            is True
        )
