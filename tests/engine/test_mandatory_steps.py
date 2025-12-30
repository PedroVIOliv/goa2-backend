import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    SelectStep, MoveUnitStep, LogMessageStep, FinalizeHeroTurnStep
)
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def basic_state():
    """Creates a basic state with one hero for testing."""
    h1 = Hero(id="hero_red", name="RedHero", team=TeamColor.RED, deck=[])
    
    start_hex = Hex(q=0, r=0, s=0)
    target_hex = Hex(q=1, r=0, s=-1)
    
    board = Board()
    board.tiles[start_hex] = Tile(hex=start_hex)
    board.tiles[target_hex] = Tile(hex=target_hex)
    board.tiles[start_hex].occupant_id = "hero_red"
    
    return GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        unit_locations={"hero_red": start_hex},
        current_actor_id="hero_red"
    )


class TestMandatoryStepAbort:
    """Tests for the mandatory step abort mechanism (GoA2 Rules)."""
    
    def test_mandatory_select_no_candidates_aborts(self, basic_state):
        """Mandatory SelectStep with no candidates should abort and clear stack."""
        # Setup: No units on board except hero_red (who is filtered out by ENEMY filter)
        from goa2.engine.filters import TeamFilter
        
        # Stack: SelectStep -> LogMessageStep -> FinalizeHeroTurnStep
        push_steps(basic_state, [
            FinalizeHeroTurnStep(hero_id="hero_red"),
            LogMessageStep(message="This should be skipped"),
            SelectStep(
                target_type="UNIT",
                prompt="Select enemy to attack",
                filters=[TeamFilter(relation="ENEMY")],
                is_mandatory=True  # Default, but explicit
            )
        ])
        
        # Stack before: [Finalize, Log, Select]
        # Select runs, finds no enemies, aborts
        # Log and all steps until Finalize are cleared
        # Finalize runs
        
        req = process_resolution_stack(basic_state)
        
        # Stack should be empty (Finalize executed and spawned FindNextActor which finished)
        # No input required since abort happened
        assert req is None or req.get("type") != "SELECT_UNIT"
    
    def test_optional_select_no_candidates_continues(self, basic_state):
        """Optional SelectStep with no candidates should skip but continue."""
        from goa2.engine.filters import TeamFilter
        
        # Track execution with a flag in context
        basic_state.execution_context["log_executed"] = False
        
        class TrackingLogStep(LogMessageStep):
            def resolve(self, state, context):
                context["log_executed"] = True
                return super().resolve(state, context)
        
        push_steps(basic_state, [
            TrackingLogStep(message="This should execute"),
            SelectStep(
                target_type="UNIT",
                prompt="Select enemy (optional)",
                filters=[TeamFilter(relation="ENEMY")],
                is_mandatory=False  # OPTIONAL
            )
        ])
        
        req = process_resolution_stack(basic_state)
        
        # Tracking log should have executed since select was optional
        assert basic_state.execution_context.get("log_executed") == True
    
    def test_movement_select_no_valid_destinations_aborts(self, basic_state):
        """When SelectStep for movement has no valid destinations, it should abort.
        
        This is the CORRECT abort trigger - player has no valid options to choose from.
        """
        from goa2.engine.filters import RangeFilter, OccupiedFilter
        
        # Setup: All hexes in range are occupied (no valid movement destinations)
        adjacent_hex = Hex(q=1, r=0, s=-1)
        basic_state.board.tiles[adjacent_hex].occupant_id = "obstacle"  # Block the only adjacent hex
        
        push_steps(basic_state, [
            FinalizeHeroTurnStep(hero_id="hero_red"),
            LogMessageStep(message="This should be skipped"),
            MoveUnitStep(unit_id="hero_red", range_val=1),  # Would execute after select
            SelectStep(
                target_type="HEX",
                prompt="Select movement destination",
                filters=[RangeFilter(max_range=1), OccupiedFilter(require_empty=True)],
                is_mandatory=True  # No valid hexes -> abort
            )
        ])
        
        req = process_resolution_stack(basic_state)
        
        # Should not prompt for HEX selection since there are no valid options
        assert req is None or req.get("type") != "SELECT_HEX"
        # Hero should NOT have moved
        assert basic_state.unit_locations["hero_red"] == Hex(q=0, r=0, s=0)
    
    def test_move_unit_with_wrong_destination_is_error_not_abort(self, basic_state):
        """MoveUnitStep with invalid path is an error, not an abort trigger.
        
        In proper gameplay, SelectStep filters ensure players only see valid options.
        This test verifies that if an invalid destination somehow reaches MoveUnitStep,
        it logs an error but does NOT abort the action chain.
        """
        basic_state.execution_context["target_hex"] = Hex(q=5, r=0, s=-5)  # Too far
        basic_state.execution_context["next_step_ran"] = False
        
        class TrackingLogStep(LogMessageStep):
            def resolve(self, state, context):
                context["next_step_ran"] = True
                return super().resolve(state, context)
        
        push_steps(basic_state, [
            TrackingLogStep(message="This should still execute"),
            MoveUnitStep(unit_id="hero_red", range_val=1)  # Invalid, but no abort
        ])
        
        start_loc = basic_state.unit_locations["hero_red"]
        req = process_resolution_stack(basic_state)
        
        # Hero did NOT move (path invalid)
        assert basic_state.unit_locations["hero_red"] == start_loc
        # But the next step DID execute (no abort occurred)
        assert basic_state.execution_context.get("next_step_ran") == True


class TestAbortClearsToFinalize:
    """Tests that abort correctly clears stack to FinalizeHeroTurnStep."""
    
    def test_abort_clears_intermediate_steps(self, basic_state):
        """Abort should skip all steps until FinalizeHeroTurnStep."""
        from goa2.engine.filters import TeamFilter
        
        # Track which steps executed
        executed = []
        
        class TrackingLog(LogMessageStep):
            msg_id: str = "default"
            def resolve(self, state, context):
                executed.append(self.msg_id)
                return super().resolve(state, context)
        
        # Stack order: list is [first_to_run, ..., last_to_run]
        # After push_steps (which reverses), first_to_run is at top of stack
        # So we want: SelectStep -> TrackingLog -> TrackingLog -> FinalizeHeroTurnStep
        push_steps(basic_state, [
            SelectStep(
                target_type="UNIT",
                prompt="Will fail",
                filters=[TeamFilter(relation="ENEMY")],
                is_mandatory=True
            ),
            TrackingLog(message="Step 2", msg_id="s2"),  # Should be skipped
            TrackingLog(message="Step 3", msg_id="s3"),  # Should be skipped
            FinalizeHeroTurnStep(hero_id="hero_red"),
        ])
        
        process_resolution_stack(basic_state)
        
        # None of the tracking logs should have executed
        assert "s2" not in executed
        assert "s3" not in executed
