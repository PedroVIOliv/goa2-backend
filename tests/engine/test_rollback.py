"""Tests for Action Resolution Rollback & Confirmation."""

import pytest

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.input import InputResponse
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Team,
    TeamColor,
)
from goa2.domain.models.enums import StepType, TargetType
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.filters import TeamFilter
from goa2.engine.handler import (
    process_stack,
    push_steps,
)
from goa2.engine.phases import start_resolution_phase
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.steps import (
    AskConfirmationStep,
    ConfirmResolutionStep,
    FinalizeHeroTurnStep,
    SelectStep,
)


def _make_card(card_id, initiative, action=ActionType.SKILL):
    return Card(
        id=card_id,
        name=f"Card {card_id}",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=initiative,
        primary_action=action,
        primary_action_value=None,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )


def _filler_cards():
    return [
        Card(
            id=f"filler_{i}",
            name=f"Filler {i}",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="e",
            effect_text="t",
        )
        for i in range(3)
    ]


def _make_state():
    """Two-hero state: hero_a (RED, init 20), hero_b (BLUE, init 10)."""
    hero_a = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.RED, deck=[], hand=_filler_cards())
    hero_b = Hero(id=HeroID("hero_b"), name="B", team=TeamColor.BLUE, deck=[], hand=_filler_cards())
    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_b], minions=[]),
        },
    )
    state.place_entity("hero_a", Hex(q=0, r=0, s=0))
    state.place_entity("hero_b", Hex(q=2, r=0, s=-2))
    return state


def _setup_resolution(state):
    """Set up cards and start resolution phase."""
    state.get_hero("hero_a").current_turn_card = _make_card("card_a", 20)
    state.get_hero("hero_b").current_turn_card = _make_card("card_b", 10)
    state.unresolved_hero_ids = ["hero_a", "hero_b"]
    start_resolution_phase(state)


# ---- ConfirmResolutionStep basic behavior ----


class TestConfirmResolutionStep:
    def test_prompts_confirm_rollback(self):
        """Confirm step shows CONFIRM/ROLLBACK options when rollback is available."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {})
        assert result.requires_input
        req = result.input_request
        assert req.player_id == "hero_a"
        option_ids = [o.id for o in req.options]
        assert "CONFIRM" in option_ids
        assert "ROLLBACK" in option_ids

    def test_auto_skips_when_rollback_frozen(self):
        """Confirm step auto-confirms when rollback is frozen."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {"rollback_frozen": True})
        assert result.is_finished
        assert not result.requires_input

    def test_confirm_input_finishes(self):
        """Submitting CONFIRM finishes the step."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        step.pending_input = {"selection": "CONFIRM"}
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {})
        assert result.is_finished


# ---- Rollback disabled tracking ----


class TestRollbackSegmentBoundary:
    def test_other_player_input_clears_snapshot_but_does_not_freeze(self):
        """When a step prompts a non-actor player, the actor's rollback snapshot is cleared (segment boundary)."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        session = GameSession(state)

        # Push two steps: own step first (to create snapshot) then foreign step
        own_step = AskConfirmationStep(player_id="hero_a", prompt="Continue?")
        foreign_step = AskConfirmationStep(player_id="hero_b", prompt="Block?")
        push_steps(state, [own_step, foreign_step])

        # First own step prompt
        res1 = session.advance()
        assert res1.input_request.player_id == "hero_a"
        assert session._rollback_snapshot is not None
        assert res1.input_request.can_rollback is True

        # Answer YES to proceed to foreign step
        res2 = session.advance(InputResponse(selection="YES"))
        assert res2.input_request.player_id == "hero_b"
        # Snapshot cleared because of foreign input
        assert session._rollback_snapshot is None
        assert res2.input_request.can_rollback is False
        # But rollback is NOT frozen
        assert state.execution_context.get("rollback_frozen") is not True

    def test_same_player_input_does_not_clear_snapshot(self):
        """When a step prompts the current actor, the rollback snapshot is retained."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        session = GameSession(state)

        own_step1 = AskConfirmationStep(player_id="hero_a", prompt="Continue 1?")
        own_step2 = AskConfirmationStep(player_id="hero_a", prompt="Continue 2?")
        push_steps(state, [own_step1, own_step2])

        res1 = session.advance()
        assert res1.input_request.player_id == "hero_a"
        assert session._rollback_snapshot is not None
        assert res1.input_request.can_rollback is True

        res2 = session.advance(InputResponse(selection="YES"))
        assert res2.input_request.player_id == "hero_a"
        assert session._rollback_snapshot is not None
        assert res2.input_request.can_rollback is True


# ---- GameSession rollback ----


class TestSessionRollback:
    def test_rollback_raises_when_no_snapshot(self):
        """rollback() raises ValueError when there's no snapshot."""
        state = _make_state()
        session = GameSession(state)
        with pytest.raises(ValueError, match="No rollback snapshot"):
            session.rollback()

    def test_basic_rollback_flow(self):
        """Start resolution -> choose action -> rollback -> back to action choice."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Process stack to get first action choice
        result = session.advance()
        assert result.result_type == SessionResultType.INPUT_NEEDED
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_a"
        assert result.input_request.can_rollback is True
        # Snapshot should be taken
        assert session._rollback_snapshot is not None

        # Choose HOLD
        result2 = session.advance(InputResponse(selection="HOLD"))
        # Should be at ConfirmResolutionStep
        assert result2.result_type == SessionResultType.INPUT_NEEDED
        assert result2.input_request.can_rollback is True

        # Rollback
        result3 = session.rollback()
        assert result3.result_type == SessionResultType.INPUT_NEEDED
        assert result3.input_request is not None
        # Back to action choice
        assert result3.input_request.player_id == "hero_a"
        assert result3.input_request.can_rollback is True

    def test_multiple_rollbacks(self):
        """Rollback, choose differently, rollback again."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Get first action choice
        result = session.advance()
        assert result.input_request.player_id == "hero_a"

        # Choose HOLD
        session.advance(InputResponse(selection="HOLD"))

        # Rollback
        r = session.rollback()
        assert r.input_request.player_id == "hero_a"

        # Choose HOLD again
        session.advance(InputResponse(selection="HOLD"))

        # Rollback again
        r2 = session.rollback()
        assert r2.input_request.player_id == "hero_a"

    def test_snapshot_cleared_after_turn(self):
        """After confirm -> finalize, snapshot is cleared."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # hero_a's action choice
        session.advance()
        assert session._rollback_snapshot is not None

        # Choose HOLD
        session.advance(InputResponse(selection="HOLD"))

        # Confirm
        result = session.advance(InputResponse(selection="CONFIRM"))

        # Now hero_b acts, hero_a's snapshot should be cleared and new one for hero_b
        if result.input_request and result.input_request.player_id == "hero_b":
            # Snapshot is now for hero_b
            assert session._rollback_snapshot is not None

    def test_can_rollback_false_for_other_players(self):
        """Input requests targeting non-actor players don't have can_rollback."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        session = GameSession(state)
        session._rollback_snapshot = state.model_dump(mode="json")

        # Push a step that targets hero_b
        step = AskConfirmationStep(player_id="hero_b", prompt="Block?")
        push_steps(state, [step])
        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_b"
        assert result.input_request.can_rollback is False

    def test_rollback_frozen_does_not_create_stale_snapshot(self):
        """Frozen rollback prompts must not become rollback targets later."""
        state = _make_state()
        state.current_actor_id = "hero_b"
        state.execution_context["rollback_frozen"] = True
        session = GameSession(state)

        # Simulates prompting hero_b
        push_steps(state, [AskConfirmationStep(player_id="hero_b", prompt="Action prompt?")])
        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_b"
        assert result.input_request.can_rollback is False
        assert session._rollback_snapshot is None
        assert session._rollback_actor_id is None

        # Later hero_b becomes the actor with rollback unfrozen.
        state.execution_context.clear()
        push_steps(state, [AskConfirmationStep(player_id="hero_b", prompt="Hero B turn")])
        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_b"
        assert result.input_request.can_rollback is True

        rollback = session.rollback()
        assert rollback.input_request is not None
        assert rollback.input_request.prompt == "Hero B turn"


# ---- Abort then rollback ----


class TestAbortThenRollback:
    def test_abort_clears_to_confirm_step(self):
        """Mandatory step failure aborts to ConfirmResolutionStep, not FinalizeHeroTurnStep."""
        state = _make_state()
        state.current_actor_id = "hero_a"

        # Use a mandatory select with filters that find no valid targets
        # TeamFilter(relation="ENEMY") requires enemies in range, but with
        # RangeFilter we can ensure none are found
        mandatory_select = SelectStep(
            target_type=TargetType.UNIT,
            prompt="Pick enemy",
            is_mandatory=True,
            filters=[
                TeamFilter(relation="ENEMY"),
                # hero_b is at distance 2 but range 0 means nothing in range
                {"type": "range_filter", "max_range": 0},
            ],
        )
        push_steps(
            state,
            [
                mandatory_select,
                ConfirmResolutionStep(hero_id="hero_a"),
                FinalizeHeroTurnStep(hero_id="hero_a"),
            ],
        )

        # Process: mandatory select fails (no valid targets), aborts to ConfirmResolutionStep
        stack_result = process_stack(state)

        # Should land on ConfirmResolutionStep
        assert stack_result.input_request is not None
        assert len(state.execution_stack) >= 1
        # The top of stack should be ConfirmResolutionStep
        top_step = state.execution_stack[-1]
        assert isinstance(top_step, ConfirmResolutionStep)


# ---- can_rollback flag in full flow ----


class TestCanRollbackFlag:
    def test_can_rollback_on_action_choice(self):
        """can_rollback is True on the initial action choice for the current actor."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.can_rollback is True

    def test_can_rollback_on_confirm_step(self):
        """can_rollback is True on the confirm step."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Action choice
        session.advance()
        # Choose HOLD
        result = session.advance(InputResponse(selection="HOLD"))
        # Confirm step
        assert result.input_request is not None
        assert result.input_request.can_rollback is True


# ---- Per-actor rollback isolation ----


class TestRollbackPerActorIsolation:
    def test_rollback_does_not_restore_previous_actors_snapshot(self):
        """Rollback for player B should restore to B's turn start, not A's."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # hero_a's action choice (highest initiative goes first)
        r1 = session.advance()
        assert r1.input_request.player_id == "hero_a"
        assert r1.input_request.can_rollback is True
        snapshot_a = session._rollback_snapshot

        # hero_a chooses HOLD
        session.advance(InputResponse(selection="HOLD"))

        # hero_a confirms
        r_confirm = session.advance(InputResponse(selection="CONFIRM"))

        # Now it's hero_b's turn
        assert r_confirm.input_request is not None
        assert r_confirm.input_request.player_id == "hero_b"
        assert r_confirm.input_request.can_rollback is True

        # Snapshot should have been replaced for hero_b
        assert session._rollback_actor_id == "hero_b"
        snapshot_b = session._rollback_snapshot
        assert snapshot_b is not snapshot_a

        # hero_b chooses HOLD
        session.advance(InputResponse(selection="HOLD"))

        # hero_b rolls back
        r_rollback = session.rollback()
        assert r_rollback.input_request is not None
        assert r_rollback.input_request.player_id == "hero_b"

        # The restored state should have hero_b as current actor, not hero_a
        assert session.state.current_actor_id == "hero_b"


# ---- Rollback during Hanu's ultimate action control ----


def _control_state():
    """blue_enemy is the actor resolving card_e, controlled by hero_hanu.

    Mirrors Hanu's ultimate: a CONTROL_NEXT_ACTION effect reroutes the
    controlled hero's inputs to Hanu, who confirms or rolls back the action.
    """
    from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
    from goa2.engine.effect_manager import EffectManager

    hero_hanu = Hero(
        id=HeroID("hero_hanu"), name="Hanu", team=TeamColor.RED, deck=[], hand=_filler_cards()
    )
    blue_enemy = Hero(
        id=HeroID("blue_enemy"), name="E", team=TeamColor.BLUE, deck=[], hand=_filler_cards()
    )
    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_hanu], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[blue_enemy], minions=[]),
        },
    )
    state.place_entity("hero_hanu", Hex(q=0, r=0, s=0))
    state.place_entity("blue_enemy", Hex(q=2, r=0, s=-2))

    blue_enemy.current_turn_card = _make_card("card_e", 10)
    state.unresolved_hero_ids = ["blue_enemy"]
    start_resolution_phase(state)

    EffectManager.create_effect(
        state=state,
        source_id="hero_hanu",
        effect_type=EffectType.CONTROL_NEXT_ACTION,
        scope=EffectScope(shape=Shape.POINT, origin_id="blue_enemy"),
        duration=DurationType.THIS_ROUND,
        is_active=True,
        controlled_card_id="card_e",
    )
    return state


class TestRollbackDuringControl:
    def test_controller_gets_rollback_snapshot_and_flag(self):
        """During control, the remapped controller (Hanu) can roll back the
        controlled action even though the actor is the controlled hero."""
        state = _control_state()
        session = GameSession(state)

        result = session.advance()
        assert result.result_type == SessionResultType.INPUT_NEEDED
        assert result.input_request is not None
        # Input is remapped to the controller.
        assert result.input_request.player_id == "hero_hanu"
        assert result.input_request.context.get("controlled_hero_id") == "blue_enemy"
        # The controlled action must be rollback-able by the controller.
        assert result.input_request.can_rollback is True
        assert session._rollback_snapshot is not None

    def test_controller_can_actually_rollback(self):
        """rollback() restores the controlled action's start state."""
        state = _control_state()
        session = GameSession(state)

        session.advance()
        # Controller chooses HOLD for the controlled hero.
        result2 = session.advance(InputResponse(selection="HOLD"))
        assert result2.input_request is not None
        assert result2.input_request.can_rollback is True

        result3 = session.rollback()
        assert result3.result_type == SessionResultType.INPUT_NEEDED
        assert result3.input_request is not None
        assert result3.input_request.player_id == "hero_hanu"
        assert result3.input_request.can_rollback is True


# ---- Snapshot board exclusion & persistence ----


def _loc(state, entity_id):
    """Look up an entity's hex regardless of key type coercion."""
    for k, v in state.entity_locations.items():
        if str(k) == entity_id:
            return v
    return None


class TestRollbackSnapshotBoardExclusion:
    def test_snapshot_excludes_board(self):
        """The rollback snapshot omits the static board to stay small."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        result = session.advance()
        assert result.input_request.can_rollback is True
        assert session._rollback_snapshot is not None
        assert "board" not in session._rollback_snapshot

    def test_rollback_restores_positions_without_snapshotting_board(self):
        """Rolling back restores unit positions even though the board is excluded."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        session.advance()  # snapshot taken at turn start; hero_a at (0,0,0)

        # Move hero_a after the snapshot
        session.state.place_entity("hero_a", Hex(q=1, r=-1, s=0))
        assert _loc(session.state, "hero_a") == Hex(q=1, r=-1, s=0)

        session.rollback()
        assert _loc(session.state, "hero_a") == Hex(q=0, r=0, s=0)


class TestRollbackSnapshotPersistence:
    def test_snapshot_and_can_rollback_survive_save_load(self, tmp_path):
        """A mid-action rollback snapshot survives a save/reload cycle."""
        from goa2.engine.persistence import load_game, save_game

        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        result = session.advance()  # action choice; snapshot taken
        assert result.input_request.can_rollback is True
        assert session._rollback_snapshot is not None

        path = save_game(
            game_id="g1",
            state=session.state,
            player_tokens={},
            spectator_token="s",
            hero_to_token={},
            created_at=0.0,
            save_dir=str(tmp_path),
            rollback_snapshot=session._rollback_snapshot,
            rollback_actor_id=session._rollback_actor_id,
        )

        data = load_game(str(path))
        restored = data["session"]

        # Snapshot and actor survived
        assert restored._rollback_snapshot is not None
        assert restored._rollback_actor_id == "hero_a"

        # The re-derived last_result re-offers rollback to the actor
        assert data["last_result"] is not None
        assert data["last_result"].input_request.can_rollback is True

        # Rollback actually works after reload
        rb = restored.rollback()
        assert rb.input_request is not None
        assert rb.input_request.player_id == "hero_a"


# ---- StepType registration ----


class TestStepTypeRegistration:
    def test_confirm_resolution_step_type(self):
        """ConfirmResolutionStep has the correct StepType."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        assert step.type == StepType.CONFIRM_RESOLUTION

    def test_serialization_roundtrip(self):
        """ConfirmResolutionStep can be serialized and deserialized."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        data = step.model_dump(mode="json")
        assert data["type"] == "confirm_resolution"
        assert data["hero_id"] == "hero_a"

        restored = ConfirmResolutionStep.model_validate(data)
        assert restored.hero_id == "hero_a"
        assert restored.type == StepType.CONFIRM_RESOLUTION


# ---- Scenario C and Mine Blast checks ----


class TestScenarioCAndMineBlast:
    def test_scenario_c_foreign_decision_anchoring(self):
        """Actor picks own hex, then enemy is prompted, then actor picks another own hex.
        Assert that:
        1. Actor can roll back after the second own pick.
        2. Rollback undoes only the post-foreign own choices.
        3. The enemy's committed result (e.g. its placed unit/token) survives the rollback.
        """
        from goa2.engine.steps import PlaceUnitStep

        state = _make_state()
        session = GameSession(state)
        state.current_actor_id = "hero_a"

        choice1 = AskConfirmationStep(
            player_id="hero_a", prompt="Actor Choice 1", output_key="actor_choice_1"
        )
        enemy_choice = AskConfirmationStep(
            player_id="hero_b", prompt="Enemy Choice", output_key="enemy_decided"
        )
        place_unit = PlaceUnitStep(
            unit_id="hero_b", target_hex_arg=Hex(q=1, r=0, s=-1), active_if_key="enemy_decided"
        )
        choice2 = AskConfirmationStep(
            player_id="hero_a", prompt="Actor Choice 2", output_key="actor_choice_2"
        )
        confirm = ConfirmResolutionStep(hero_id="hero_a")

        push_steps(state, [choice1, enemy_choice, place_unit, choice2, confirm])

        # 1. Prompt actor for Choice 1
        res1 = session.advance()
        assert res1.input_request.player_id == "hero_a"
        assert res1.input_request.prompt == "Actor Choice 1"
        assert res1.input_request.can_rollback is True
        assert session._rollback_snapshot is not None

        # Actor submits YES
        res2 = session.advance(InputResponse(selection="YES"))

        # 2. Prompt enemy for Enemy Choice
        assert res2.input_request.player_id == "hero_b"
        assert res2.input_request.prompt == "Enemy Choice"
        # Since it's foreign, can_rollback should be False, and snapshot should be cleared.
        assert res2.input_request.can_rollback is False
        assert session._rollback_snapshot is None

        # Enemy submits YES
        res3 = session.advance(InputResponse(selection="YES"))

        # 3. PlaceUnitStep executes automatically (no input needed), then choice2 prompts hero_a
        assert res3.input_request.player_id == "hero_a"
        assert res3.input_request.prompt == "Actor Choice 2"
        # Since this is actor's next own input after a foreign segment boundary, a fresh snapshot is taken
        assert res3.input_request.can_rollback is True
        assert session._rollback_snapshot is not None

        # Verify that the enemy's placed unit exists at the target hex in current state
        assert state.entity_locations.get("hero_b") == Hex(q=1, r=0, s=-1)

        # Actor submits YES for Choice 2
        res4 = session.advance(InputResponse(selection="YES"))

        # Now we land on ConfirmResolutionStep (or we can rollback before or after)
        assert res4.input_request is not None
        assert res4.input_request.can_rollback is True

        # Actor rolls back!
        res_rollback = session.rollback()

        # Assert that we are back at "Actor Choice 2" prompt
        assert res_rollback.input_request.prompt == "Actor Choice 2"

        # Assert that the enemy's committed result SURVIVES the rollback!
        assert session.state.entity_locations.get("hero_b") == Hex(q=1, r=0, s=-1)

        # Assert that the post-foreign own choice was undone (actor_choice_2 is None/False)
        assert session.state.execution_context.get("actor_choice_2") is not True

        # Assert that pre-foreign own choice is still intact
        assert session.state.execution_context.get("actor_choice_1") is True

    def test_mine_blast_freezes_rollback(self):
        """Assert that rollback stays frozen after a mine blast (the permanent case)."""
        from goa2.domain.models import Token, TokenType
        from goa2.domain.types import BoardEntityID
        from goa2.engine.steps import TriggerMineStep

        state = _make_state()
        state.current_actor_id = "hero_a"
        session = GameSession(state)

        # Place a mine token in state
        mine = Token(
            id=BoardEntityID("mine_1"),
            name="Mine",
            token_type=TokenType.MINE_BLAST,
            owner_id="hero_b",
            is_passable=True,
            is_facedown=True,
        )
        state.token_pool[TokenType.MINE_BLAST] = [mine]
        state.misc_entities[BoardEntityID("mine_1")] = mine
        state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=0, s=-1))

        # 1. Prompt actor for Choice 1 to establish a snapshot
        choice1 = AskConfirmationStep(player_id="hero_a", prompt="Choice 1")
        push_steps(state, [choice1])
        res1 = session.advance()
        assert res1.input_request.can_rollback is True
        assert session._rollback_snapshot is not None

        # Trigger mine blast.
        # We push: [TriggerMineStep, AskConfirmationStep(Choice 2)]
        trigger = TriggerMineStep()
        choice2 = AskConfirmationStep(player_id="hero_a", prompt="Choice 2")

        # Set context variables needed by TriggerMineStep
        state.execution_context["triggered_mine_ids"] = ["mine_1"]
        state.execution_context["mine_victim_id"] = "hero_a"

        push_steps(state, [trigger, choice2])

        # Advance session to process the input, run the trigger step (which sets rollback_frozen),
        # and then prompt Choice 2 (in our LIFO execution flow, the force discard step runs first).
        res2 = session.advance(InputResponse(selection="YES"))

        # Assert we are prompted for discard (since a blast mine forces the victim to discard a card)
        assert "select a card to discard" in res2.input_request.prompt
        # Assert rollback is frozen and snapshot is cleared
        assert res2.input_request.can_rollback is False
        assert session._rollback_snapshot is None
        assert state.execution_context.get("rollback_frozen") is True

        # Confirm that calling rollback raises ValueError
        with pytest.raises(ValueError, match="No rollback snapshot"):
            session.rollback()
