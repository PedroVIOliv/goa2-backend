"""Tests for Final Embrace (Xargatha Tier III Green) — DELAYED_TRIGGER finishing steps."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
)
from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.engine.steps import (
    AdvanceTurnStep,
    CreateEffectStep,
    DefeatUnitStep,
    EndPhaseStep,
    MinionBattleStep,
    SelectStep,
    SetActorStep,
)
from goa2.engine.filters import MinionTypesFilter, RangeFilter, TeamFilter
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.domain.models.enums import StepType, TargetType

# Ensure step_types patching is applied (imports trigger it)
import goa2.engine.step_types  # noqa: F401


@pytest.fixture
def embrace_state():
    """
    State with:
    - Xargatha (hero_xargatha, RED) at (0,0,0)
    - Enemy melee minion (melee_1, BLUE) at (1,0,-1) — adjacent
    - Enemy ranged minion (ranged_1, BLUE) at (0,1,-1) — adjacent
    - Enemy heavy minion (heavy_1, BLUE) at (-1,1,0) — adjacent
    - Friendly melee minion (ally_melee, RED) at (0,-1,1) — adjacent
    - Active zone with all hexes
    """
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
        Hex(q=0, r=-1, s=1),
        Hex(q=-1, r=0, s=1),
        Hex(q=1, r=-1, s=0),
    }
    board = Board()
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="hero_xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1)
    melee = Minion(id="melee_1", name="Melee", type=MinionType.MELEE, team=TeamColor.BLUE)
    ranged = Minion(id="ranged_1", name="Ranged", type=MinionType.RANGED, team=TeamColor.BLUE)
    heavy = Minion(id="heavy_1", name="Heavy", type=MinionType.HEAVY, team=TeamColor.BLUE)
    ally_melee = Minion(id="ally_melee", name="AllyMelee", type=MinionType.MELEE, team=TeamColor.RED)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[ally_melee]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[melee, ranged, heavy]),
        },
    )
    state.place_entity("hero_xargatha", Hex(q=0, r=0, s=0))
    state.place_entity("melee_1", Hex(q=1, r=0, s=-1))
    state.place_entity("ranged_1", Hex(q=0, r=1, s=-1))
    state.place_entity("heavy_1", Hex(q=-1, r=1, s=0))
    state.place_entity("ally_melee", Hex(q=0, r=-1, s=1))
    state.active_zone_id = "z1"

    return state


def _add_delayed_trigger(state, source_id="hero_xargatha"):
    """Add a DELAYED_TRIGGER effect with Final Embrace finishing steps."""
    finishing_steps = [
        SelectStep(
            target_type=TargetType.UNIT,
            filters=[
                TeamFilter(relation="ENEMY"),
                MinionTypesFilter(minion_types=[MinionType.MELEE, MinionType.RANGED]),
                RangeFilter(max_range=1),
            ],
            output_key="final_embrace_victim",
            is_mandatory=False,
            prompt="Select enemy melee or ranged minion to defeat (Final Embrace)",
        ),
        DefeatUnitStep(
            victim_key="final_embrace_victim",
            active_if_key="final_embrace_victim",
        ),
    ]
    effect = ActiveEffect(
        id="eff_final_embrace",
        source_id=source_id,
        effect_type=EffectType.DELAYED_TRIGGER,
        scope=EffectScope(shape=Shape.POINT),
        duration=DurationType.THIS_ROUND,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
        finishing_steps=finishing_steps,
    )
    state.active_effects.append(effect)


class TestFinishingStepsOnEndPhase:
    """Test that EndPhaseStep collects and executes finishing steps."""

    def test_defeat_adjacent_enemy_melee(self, embrace_state):
        """End of round with adjacent enemy melee → minion defeated."""
        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        # EndPhaseStep should inject SetActorStep + SelectStep
        req = process_resolution_stack(embrace_state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        assert "melee_1" in req["valid_options"]
        assert "ranged_1" in req["valid_options"]

        # Select melee minion
        embrace_state.execution_stack[-1].pending_input = {"selection": "melee_1"}
        process_resolution_stack(embrace_state)

        # Melee minion should be defeated (removed from locations)
        assert "melee_1" not in embrace_state.entity_locations

    def test_defeat_adjacent_enemy_ranged(self, embrace_state):
        """End of round with adjacent enemy ranged → minion defeated."""
        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        req = process_resolution_stack(embrace_state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"

        # Select ranged minion
        embrace_state.execution_stack[-1].pending_input = {"selection": "ranged_1"}
        process_resolution_stack(embrace_state)

        assert "ranged_1" not in embrace_state.entity_locations

    def test_heavy_minion_not_selectable(self, embrace_state):
        """Adjacent enemy heavy minion should NOT appear in valid options."""
        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        req = process_resolution_stack(embrace_state)
        assert req is not None
        assert "heavy_1" not in req["valid_options"]

    def test_friendly_minion_not_selectable(self, embrace_state):
        """Adjacent friendly minion should NOT appear in valid options."""
        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        req = process_resolution_stack(embrace_state)
        assert req is not None
        assert "ally_melee" not in req["valid_options"]

    def test_no_valid_targets_skips(self, embrace_state):
        """No adjacent enemy melee/ranged → effect silently skips."""
        # Remove melee and ranged minions
        embrace_state.remove_entity("melee_1")
        embrace_state.remove_entity("ranged_1")

        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        # Should complete without asking for input
        req = process_resolution_stack(embrace_state)
        assert req is None

    def test_set_actor_step_sets_correct_actor(self, embrace_state):
        """SetActorStep should set current_actor_id to the effect's source_id."""
        _add_delayed_trigger(embrace_state)
        embrace_state.current_actor_id = None  # Clear to verify it gets set

        push_steps(embrace_state, [EndPhaseStep()])
        req = process_resolution_stack(embrace_state)

        # If we got a SELECT_UNIT request, actor must have been set correctly
        # (TeamFilter and RangeFilter depend on current_actor_id)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        assert embrace_state.current_actor_id == "hero_xargatha"

    def test_effect_expired_after_end_phase(self, embrace_state):
        """The DELAYED_TRIGGER effect should be removed after EndPhaseStep."""
        _add_delayed_trigger(embrace_state)
        push_steps(embrace_state, [EndPhaseStep()])

        # Skip selection (no mandatory)
        req = process_resolution_stack(embrace_state)
        if req is not None:
            embrace_state.execution_stack[-1].pending_input = {"selection": "melee_1"}
            process_resolution_stack(embrace_state)

        # Effect should be gone
        assert len([
            e for e in embrace_state.active_effects
            if e.effect_type == EffectType.DELAYED_TRIGGER
        ]) == 0

    def test_no_finishing_steps_normal_end_phase(self, embrace_state):
        """EndPhaseStep without any DELAYED_TRIGGER effects works normally."""
        push_steps(embrace_state, [EndPhaseStep()])

        # Should complete without any SELECT_UNIT prompts
        # (minion battle may ask for removal, but not SELECT_UNIT for embrace)
        req = process_resolution_stack(embrace_state)
        # No delayed trigger, so first request (if any) is from minion battle
        if req is not None:
            assert req["type"] != "SELECT_UNIT" or "final_embrace" not in str(req)


class TestExpireEffectsReturnsFinishing:
    """Test that expire_effects returns finishing steps correctly."""

    def test_returns_finishing_steps(self, embrace_state):
        """expire_effects should return finishing steps from expired effects."""
        from goa2.engine.effect_manager import EffectManager

        _add_delayed_trigger(embrace_state)
        finishing = EffectManager.expire_effects(embrace_state, DurationType.THIS_ROUND)

        assert len(finishing) == 1
        source_id, steps = finishing[0]
        assert source_id == "hero_xargatha"
        assert len(steps) == 2
        assert isinstance(steps[0], SelectStep)
        assert isinstance(steps[1], DefeatUnitStep)

    def test_no_finishing_steps_returns_empty(self, embrace_state):
        """Effects without finishing_steps should not appear in results."""
        from goa2.engine.effect_manager import EffectManager

        # Add a normal effect (no finishing steps)
        effect = ActiveEffect(
            id="eff_normal",
            source_id="hero_xargatha",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.POINT),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
        )
        embrace_state.active_effects.append(effect)

        finishing = EffectManager.expire_effects(embrace_state, DurationType.THIS_ROUND)
        assert len(finishing) == 0


class TestCreateEffectStepWithFinishingSteps:
    """Test CreateEffectStep passes finishing_steps through."""

    def test_create_effect_with_finishing_steps(self, embrace_state):
        """CreateEffectStep should create an effect with finishing_steps attached."""
        embrace_state.current_actor_id = "hero_xargatha"

        step = CreateEffectStep(
            effect_type=EffectType.DELAYED_TRIGGER,
            duration=DurationType.THIS_ROUND,
            scope=EffectScope(shape=Shape.POINT),
            is_active=True,
            use_context_card=False,
            finishing_steps=[
                SelectStep(
                    target_type=TargetType.UNIT,
                    filters=[TeamFilter(relation="ENEMY")],
                    output_key="test_victim",
                    is_mandatory=False,
                    prompt="Test select",
                ),
            ],
        )
        push_steps(embrace_state, [step])
        process_resolution_stack(embrace_state)

        assert len(embrace_state.active_effects) == 1
        effect = embrace_state.active_effects[0]
        assert effect.effect_type == EffectType.DELAYED_TRIGGER
        assert len(effect.finishing_steps) == 1
        assert isinstance(effect.finishing_steps[0], SelectStep)


class TestMinionBattleAfterFinishingSteps:
    """Test that minion battle uses post-finishing-step counts."""

    def test_finishing_step_defeat_affects_battle_count(self, embrace_state):
        """
        RED=5, BLUE=6 minions → finishing step defeats 1 BLUE →
        RED=5, BLUE=5 → tied → no removals.
        Without lazy MinionBattleStep, battle would see 5 vs 6 and remove 1 RED.
        """
        zone = embrace_state.board.zones["z1"]
        # Add extra hexes for more minions
        extra_hexes = [
            Hex(q=2, r=-1, s=-1), Hex(q=2, r=0, s=-2),
            Hex(q=-1, r=2, s=-1), Hex(q=0, r=2, s=-2),
            Hex(q=-2, r=1, s=1), Hex(q=-2, r=2, s=0),
            Hex(q=1, r=1, s=-2), Hex(q=-1, r=-1, s=2),
        ]
        for h in extra_hexes:
            zone.hexes.add(h)
        embrace_state.board.populate_tiles_from_zones()

        # Clear existing entities except xargatha
        for eid in list(embrace_state.entity_locations.keys()):
            if eid != "hero_xargatha":
                embrace_state.remove_entity(eid)

        # Place RED minions (5 total)
        red_team = embrace_state.teams[TeamColor.RED]
        red_team.minions = []
        red_hexes = [
            Hex(q=0, r=-1, s=1), Hex(q=1, r=-1, s=0),
            Hex(q=2, r=-1, s=-1), Hex(q=2, r=0, s=-2),
            Hex(q=-1, r=-1, s=2),
        ]
        for i, h in enumerate(red_hexes):
            m = Minion(id=f"red_m_{i}", name=f"RedM{i}", type=MinionType.MELEE, team=TeamColor.RED)
            red_team.minions.append(m)
            embrace_state.place_entity(m.id, h)

        # Place BLUE minions (6 total)
        blue_team = embrace_state.teams[TeamColor.BLUE]
        blue_team.minions = []
        blue_hexes = [
            Hex(q=1, r=0, s=-1), Hex(q=0, r=1, s=-1),
            Hex(q=-1, r=1, s=0), Hex(q=-1, r=2, s=-1),
            Hex(q=0, r=2, s=-2), Hex(q=1, r=1, s=-2),
        ]
        for i, h in enumerate(blue_hexes):
            mt = MinionType.MELEE if i > 0 else MinionType.RANGED
            m = Minion(id=f"blue_m_{i}", name=f"BlueM{i}", type=mt, team=TeamColor.BLUE)
            blue_team.minions.append(m)
            embrace_state.place_entity(m.id, h)

        # Add delayed trigger that defeats blue_m_0 (ranged, adjacent to xargatha)
        finishing_steps = [
            SelectStep(
                target_type=TargetType.UNIT,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    MinionTypesFilter(minion_types=[MinionType.MELEE, MinionType.RANGED]),
                    RangeFilter(max_range=1),
                ],
                output_key="final_embrace_victim",
                is_mandatory=False,
                prompt="Select enemy minion to defeat (Final Embrace)",
            ),
            DefeatUnitStep(
                victim_key="final_embrace_victim",
                active_if_key="final_embrace_victim",
            ),
        ]
        effect = ActiveEffect(
            id="eff_final_embrace",
            source_id="hero_xargatha",
            effect_type=EffectType.DELAYED_TRIGGER,
            scope=EffectScope(shape=Shape.POINT),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
            finishing_steps=finishing_steps,
        )
        embrace_state.active_effects.append(effect)

        # Run EndPhaseStep
        push_steps(embrace_state, [EndPhaseStep()])
        req = process_resolution_stack(embrace_state)

        # Should get SELECT_UNIT for finishing step
        assert req is not None
        assert req["type"] == "SELECT_UNIT"

        # Select blue_m_0 (ranged minion adjacent to xargatha)
        embrace_state.execution_stack[-1].pending_input = {"selection": "blue_m_0"}
        req = process_resolution_stack(embrace_state)

        # blue_m_0 should be defeated
        assert "blue_m_0" not in embrace_state.entity_locations

        # Now battle: RED=5, BLUE=5 → tied → no removals needed
        # So no further input should be required (req is None)
        assert req is None

    def test_minion_battle_step_standalone(self, embrace_state):
        """MinionBattleStep computes counts at resolve time."""
        # RED has 1 (ally_melee), BLUE has 3 (melee_1, ranged_1, heavy_1)
        push_steps(embrace_state, [MinionBattleStep()])
        req = process_resolution_stack(embrace_state)

        # BLUE has more, so RED loses 2 minions.
        # RED only has 1 minion → auto-remove (no choice needed)
        assert req is None
        assert "ally_melee" not in embrace_state.entity_locations


class TestFinishingStepsSerialization:
    """Test that finishing_steps round-trip through JSON serialization."""

    def test_active_effect_with_finishing_steps_round_trip(self):
        """ActiveEffect with finishing_steps should serialize and deserialize."""
        effect = ActiveEffect(
            id="eff_test",
            source_id="hero_xargatha",
            effect_type=EffectType.DELAYED_TRIGGER,
            scope=EffectScope(shape=Shape.POINT),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
            finishing_steps=[
                SelectStep(
                    target_type=TargetType.UNIT,
                    filters=[TeamFilter(relation="ENEMY")],
                    output_key="test_victim",
                    is_mandatory=False,
                    prompt="Test select",
                ),
                DefeatUnitStep(victim_key="test_victim"),
            ],
        )

        # Serialize
        data = effect.model_dump()

        # Deserialize
        restored = ActiveEffect.model_validate(data)

        assert restored.effect_type == EffectType.DELAYED_TRIGGER
        assert len(restored.finishing_steps) == 2
        assert restored.finishing_steps[0].type == StepType.SELECT
        assert restored.finishing_steps[1].type == StepType.DEFEAT_UNIT

    def test_create_effect_step_with_finishing_steps_round_trip(self):
        """CreateEffectStep with finishing_steps should serialize and deserialize."""
        step = CreateEffectStep(
            effect_type=EffectType.DELAYED_TRIGGER,
            duration=DurationType.THIS_ROUND,
            scope=EffectScope(shape=Shape.POINT),
            is_active=True,
            use_context_card=False,
            finishing_steps=[
                SelectStep(
                    target_type=TargetType.UNIT,
                    filters=[TeamFilter(relation="ENEMY")],
                    output_key="test_victim",
                    is_mandatory=False,
                    prompt="Test select",
                ),
                DefeatUnitStep(victim_key="test_victim"),
            ],
        )
        data = step.model_dump()
        restored = CreateEffectStep.model_validate(data)

        assert len(restored.finishing_steps) == 2
        assert restored.finishing_steps[0].type == StepType.SELECT
        assert restored.finishing_steps[1].type == StepType.DEFEAT_UNIT
