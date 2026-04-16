"""Unit tests for PR1 engine prereqs for Silverarrow.

Covers:
- CountMatchFilter accepting a unit-ID candidate (Family 1 isolated snipe).
- ComputeDistanceStep (unit <-> recorded hex / other unit).
- RangeFilter.max_range_key reading upper bound from context.
- MOVEMENT_AURA_ZONE aura pass-through-obstacles detection in MoveSequenceStep.
- PassiveTrigger.BEFORE_ACTION enum value + CheckPassiveAbilitiesStep match.
"""

import goa2.engine.step_types  # noqa: F401
import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.engine.filters import (
    CountMatchFilter,
    RangeFilter,
    TeamFilter,
)
from goa2.engine.steps import (
    ComputeDistanceStep,
    RecordHexStep,
    MoveSequenceStep,
)
from goa2.domain.models.enums import PassiveTrigger


@pytest.fixture
def basic_state():
    board = Board()
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            if -3 <= s <= 3:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)

    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    h3 = Hero(id="h3", name="H3", team=TeamColor.BLUE, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2, h3], minions=[m1]),
        },
        entity_locations={},
        current_actor_id="h1",
    )
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("h2", Hex(q=3, r=0, s=-3))  # isolated (far from others)
    state.place_entity("h3", Hex(q=-2, r=0, s=2))  # has m1 adjacent
    state.place_entity("m1", Hex(q=-3, r=0, s=3))  # adjacent to h3
    return state


class TestCountMatchFilterUnitCandidate:
    def test_isolated_hero_passes_max_count_zero(self, basic_state):
        """h2 is far from everyone — 0 units at distance 1."""
        f = CountMatchFilter(
            sub_filters=[
                RangeFilter(
                    min_range=1,
                    max_range=1,
                    origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                ),
            ],
            max_count=0,
            min_count=0,
        )
        assert f.apply("h2", basic_state, {}) is True

    def test_non_isolated_hero_fails_max_count_zero(self, basic_state):
        """h3 is adjacent to m1 — 1 unit at distance 1, so max_count=0 fails."""
        f = CountMatchFilter(
            sub_filters=[
                RangeFilter(
                    min_range=1,
                    max_range=1,
                    origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                ),
            ],
            max_count=0,
            min_count=0,
        )
        assert f.apply("h3", basic_state, {}) is False

    def test_unknown_unit_id_fails(self, basic_state):
        f = CountMatchFilter(
            sub_filters=[],
            max_count=0,
            min_count=0,
        )
        assert f.apply("does_not_exist", basic_state, {}) is False

    def test_hex_candidate_still_works(self, basic_state):
        """Existing Misa swoop_in hex-candidate path still works."""
        f = CountMatchFilter(
            sub_filters=[
                RangeFilter(
                    min_range=1,
                    max_range=1,
                    origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                ),
            ],
            max_count=None,
            min_count=0,
        )
        # Hex(0,0,0) has h1 on it — 0 units at distance 1 from it (itself excluded)
        assert f.apply(Hex(q=0, r=0, s=0), basic_state, {}) is True


class TestComputeDistanceStep:
    def test_distance_unit_to_recorded_hex(self, basic_state):
        ctx = {}
        # Record h1's starting hex
        RecordHexStep(unit_id="h1", output_key="start_hex").resolve(basic_state, ctx)
        # Move h1 to (2,0,-2)
        basic_state.place_entity("h1", Hex(q=2, r=0, s=-2))
        ComputeDistanceStep(
            unit_id="h1", hex_key="start_hex", output_key="moved"
        ).resolve(basic_state, ctx)
        assert ctx["moved"] == 2

    def test_distance_unit_to_unit(self, basic_state):
        ctx = {}
        ComputeDistanceStep(unit_id="h1", other_unit_id="h2", output_key="d").resolve(
            basic_state, ctx
        )
        assert ctx["d"] == 3

    def test_missing_unit_stores_zero(self, basic_state):
        ctx = {}
        ComputeDistanceStep(unit_id="nope", hex_key="missing", output_key="d").resolve(
            basic_state, ctx
        )
        assert ctx["d"] == 0


class TestRangeFilterMaxRangeKey:
    def test_max_range_read_from_context(self, basic_state):
        # Without context key, static max_range = 1 fails for h2 (distance 3)
        f = RangeFilter(max_range=1, max_range_key="drag_moved")
        # Set context to 5 — should now pass
        assert f.apply("h2", basic_state, {"drag_moved": 5}) is True
        # Without context key set, falls back to static 1
        assert f.apply("h2", basic_state, {}) is False


class TestMovementAuraZoneDetection:
    def test_move_sequence_picks_up_zone_aura(self, basic_state):
        """MoveSequenceStep should enable pass_through when a MOVEMENT_AURA_ZONE
        effect covers the actor and grants pass-through-obstacles."""
        # Create aura centered on h1 (self), radius 3, affects friendly heroes
        effect = ActiveEffect(
            id="ev1",
            source_id="h1",
            effect_type=EffectType.MOVEMENT_AURA_ZONE,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=3,
                origin_id="h1",
                affects=AffectsFilter.SELF_AND_FRIENDLY_HEROES,
            ),
            duration=DurationType.THIS_ROUND,
            created_at_turn=basic_state.turn,
            created_at_round=basic_state.round,
            is_active=True,
            grants_pass_through_obstacles=True,
        )
        basic_state.active_effects.append(effect)

        step = MoveSequenceStep(unit_id="h1", range_val=3)
        result = step.resolve(basic_state, {})
        # Look for MoveUnitStep in new_steps and verify pass_through is set
        from goa2.engine.steps import MoveUnitStep

        move_steps = [
            s for s in (result.new_steps or []) if isinstance(s, MoveUnitStep)
        ]
        assert move_steps, "Expected a MoveUnitStep in expansion"
        assert move_steps[0].pass_through_obstacles is True

    def test_move_sequence_without_aura_does_not_pass_through(self, basic_state):
        step = MoveSequenceStep(unit_id="h1", range_val=3)
        result = step.resolve(basic_state, {})
        from goa2.engine.steps import MoveUnitStep

        move_steps = [
            s for s in (result.new_steps or []) if isinstance(s, MoveUnitStep)
        ]
        assert move_steps
        assert move_steps[0].pass_through_obstacles is False


class TestBeforeActionTrigger:
    def test_enum_value_exists(self):
        assert PassiveTrigger.BEFORE_ACTION.value == "before_action"

    def test_distinct_from_other_triggers(self):
        assert PassiveTrigger.BEFORE_ACTION != PassiveTrigger.BEFORE_ATTACK
        assert PassiveTrigger.BEFORE_ACTION != PassiveTrigger.BEFORE_MOVEMENT
        assert PassiveTrigger.BEFORE_ACTION != PassiveTrigger.BEFORE_SKILL

    def test_fires_in_defense_path(self, basic_state):
        from goa2.engine.steps import (
            AttackSequenceStep,
            CheckPassiveAbilitiesStep,
        )

        atk = AttackSequenceStep(damage=3, range_val=3, is_ranged=True)
        result = atk.resolve(basic_state, {"attack_is_ranged": True})
        assert result.new_steps
        before_action_steps = [
            s
            for s in result.new_steps
            if isinstance(s, CheckPassiveAbilitiesStep)
            and s.trigger == PassiveTrigger.BEFORE_ACTION.value
        ]
        assert len(before_action_steps) == 1, (
            "Expected exactly one CheckPassiveAbilitiesStep(BEFORE_ACTION) "
            "in AttackSequenceStep expansion (defense path)"
        )
