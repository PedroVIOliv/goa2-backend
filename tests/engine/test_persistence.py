"""Tests for Phase 6: State Persistence — serialization round-trips."""

import os
import tempfile

import pytest

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, GamePhase
from goa2.domain.models.enums import TargetType
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState
from goa2.engine.filters import (
    RangeFilter,
    TeamFilter,
)
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.persistence import save_game, load_game, load_all_games, delete_game_save
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.engine.steps import (
    SelectStep,
    MoveUnitStep,
    LogMessageStep,
    ForEachStep,
    MayRepeatNTimesStep,
)

MAP_PATH = "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def save_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def full_state():
    """A fully initialized game state via GameSetup."""
    return GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


def test_round_trip_fresh_game(full_state, save_dir):
    """Save and load a fresh game — all fields should match."""
    path = save_game(
        game_id="test123",
        state=full_state,
        player_tokens={"tok_a": "hero_arien", "tok_b": "hero_wasp"},
        spectator_token="spec_tok",
        hero_to_token={"hero_arien": "tok_a", "hero_wasp": "tok_b"},
        created_at=1000.0,
        save_dir=save_dir,
    )

    assert path.exists()
    data = load_game(str(path))

    assert data["game_id"] == "test123"
    assert data["player_tokens"] == {"tok_a": "hero_arien", "tok_b": "hero_wasp"}
    assert data["spectator_token"] == "spec_tok"
    assert data["hero_to_token"] == {"hero_arien": "tok_a", "hero_wasp": "tok_b"}
    assert data["created_at"] == 1000.0

    restored_state = data["session"].state
    assert restored_state.phase == full_state.phase
    assert restored_state.round == full_state.round
    assert len(restored_state.teams) == len(full_state.teams)


def test_round_trip_preserves_entity_locations(full_state, save_dir):
    """Entity locations survive round-trip."""
    original_locs = dict(full_state.entity_locations)
    assert len(original_locs) > 0  # Game has placed entities

    save_game(
        game_id="locs",
        state=full_state,
        player_tokens={},
        spectator_token="s",
        hero_to_token={},
        created_at=0,
        save_dir=save_dir,
    )
    data = load_game(os.path.join(save_dir, "locs.json"))
    restored = data["session"].state

    assert len(restored.entity_locations) == len(original_locs)
    for eid, hex_val in original_locs.items():
        assert str(eid) in [str(k) for k in restored.entity_locations.keys()]


# ---------------------------------------------------------------------------
# Steps on stack
# ---------------------------------------------------------------------------


def test_round_trip_with_steps_on_stack():
    """Steps on the execution stack survive round-trip with correct types."""
    board = Board()
    hero = Hero(id="hero_a", name="HeroA", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_a",
    )
    h = Hex(q=0, r=0, s=0)
    board.tiles[h] = board.get_tile(h)
    state.place_entity("hero_a", h)

    push_steps(state, [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Pick target",
            filters=[RangeFilter(max_range=2), TeamFilter(relation="ENEMY")],
        ),
        MoveUnitStep(unit_id="hero_a"),
        LogMessageStep(message="done"),
    ])

    # Round-trip via model serialization (no process_stack)
    data = state.model_dump(mode="json")
    restored = GameState.model_validate(data)

    assert len(restored.execution_stack) == 3
    assert type(restored.execution_stack[0]).__name__ == "LogMessageStep"
    assert type(restored.execution_stack[1]).__name__ == "MoveUnitStep"

    select = restored.execution_stack[2]
    assert type(select).__name__ == "SelectStep"
    assert len(select.filters) == 2
    assert type(select.filters[0]).__name__ == "RangeFilter"
    assert type(select.filters[1]).__name__ == "TeamFilter"


# ---------------------------------------------------------------------------
# Nested step templates
# ---------------------------------------------------------------------------


def test_round_trip_foreach_step():
    """ForEachStep with steps_template round-trips via model serialization."""
    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )

    foreach = ForEachStep(
        list_key="targets",
        item_key="current",
        steps_template=[
            MoveUnitStep(unit_id="hero_a"),
            LogMessageStep(message="moved"),
        ],
    )
    state.execution_stack.append(foreach)

    data = state.model_dump(mode="json")
    restored = GameState.model_validate(data)

    step = restored.execution_stack[0]
    assert type(step).__name__ == "ForEachStep"
    assert len(step.steps_template) == 2
    assert type(step.steps_template[0]).__name__ == "MoveUnitStep"
    assert type(step.steps_template[1]).__name__ == "LogMessageStep"


def test_round_trip_may_repeat_step():
    """MayRepeatNTimesStep with nested steps_template round-trips."""
    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )

    repeat = MayRepeatNTimesStep(
        max_repeats=3,
        prompt="Again?",
        steps_template=[LogMessageStep(message="repeated")],
    )
    state.execution_stack.append(repeat)

    data = state.model_dump(mode="json")
    restored = GameState.model_validate(data)

    step = restored.execution_stack[0]
    assert type(step).__name__ == "MayRepeatNTimesStep"
    assert step.max_repeats == 3
    assert len(step.steps_template) == 1


# ---------------------------------------------------------------------------
# All step types serialize
# ---------------------------------------------------------------------------


def test_every_step_type_has_unique_discriminator():
    """Every concrete step class has a unique StepType (no GENERIC collisions)."""
    import goa2.engine.steps as steps_mod
    import inspect

    seen = {}
    for name, cls in inspect.getmembers(steps_mod, inspect.isclass):
        if not issubclass(cls, steps_mod.GameStep) or cls is steps_mod.GameStep:
            continue
        # MayRepeatOnceStep shares with MayRepeatNTimesStep intentionally
        if name == "MayRepeatOnceStep":
            continue
        step_type = cls.model_fields["type"].default
        if step_type in seen:
            pytest.fail(
                f"{name} and {seen[step_type]} share StepType {step_type}"
            )
        seen[step_type] = name


# ---------------------------------------------------------------------------
# Filter union
# ---------------------------------------------------------------------------


def test_all_filter_types_round_trip(save_dir):
    """Each filter subclass serializes and deserializes correctly."""
    from goa2.engine import filters as f_mod
    import inspect

    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )

    # Collect all concrete filter subclasses
    filter_classes = []
    for name, cls in inspect.getmembers(f_mod, inspect.isclass):
        if issubclass(cls, f_mod.FilterCondition) and cls is not f_mod.FilterCondition:
            filter_classes.append(cls)

    assert len(filter_classes) >= 19  # Sanity check

    # Try to instantiate each with minimal args and put in a SelectStep
    for fc in filter_classes:
        fields = fc.model_fields
        kwargs = {}
        for fname, finfo in fields.items():
            if fname == "type":
                continue
            if finfo.is_required():
                # Provide minimal values
                ann = finfo.annotation
                if ann == str or ann == "str":
                    kwargs[fname] = "test"
                elif ann == int or ann == "int":
                    kwargs[fname] = 1
                elif str(ann).startswith("typing.List") or str(ann) == "list":
                    kwargs[fname] = []

        try:
            instance = fc(**kwargs)
        except Exception:
            continue  # Some may need complex args; that's OK

        step = SelectStep(
            target_type=TargetType.UNIT,
            prompt="test",
            filters=[instance],
        )
        state.execution_stack = [step]

        data = state.model_dump(mode="json")
        restored = GameState.model_validate(data)
        restored_filter = restored.execution_stack[0].filters[0]
        assert type(restored_filter).__name__ == type(instance).__name__, (
            f"Filter {type(instance).__name__} did not round-trip correctly"
        )


# ---------------------------------------------------------------------------
# Re-derivation of last_result
# ---------------------------------------------------------------------------


def test_last_result_re_derived_on_load(save_dir):
    """When loading a game waiting for input, last_result is re-derived."""
    board = Board()
    hero_a = Hero(id="hero_a", name="HeroA", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_a",
        phase=GamePhase.RESOLUTION,
    )

    h0 = Hex(q=0, r=0, s=0)
    board.tiles[h0] = board.get_tile(h0)
    state.place_entity("hero_a", h0)

    # Push a NUMBER SelectStep — always finds candidates (no board filtering)
    push_steps(state, [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Pick a number",
            output_key="chosen_number",
            number_options=[1, 2, 3],
        ),
    ])

    # Process stack — pauses at SelectStep waiting for input
    result = process_stack(state)
    assert result.input_request is not None

    # Save while waiting for input
    save_game(
        game_id="input_pending",
        state=state,
        player_tokens={"tok": "hero_a"},
        spectator_token="s",
        hero_to_token={"hero_a": "tok"},
        created_at=0,
        save_dir=save_dir,
    )

    data = load_game(os.path.join(save_dir, "input_pending.json"))
    assert data["last_result"] is not None
    assert data["last_result"].input_request is not None


# ---------------------------------------------------------------------------
# load_all_games / delete
# ---------------------------------------------------------------------------


def test_load_all_games(full_state, save_dir):
    """load_all_games loads all JSON files in directory."""
    for i in range(3):
        save_game(
            game_id=f"game_{i}",
            state=full_state,
            player_tokens={},
            spectator_token="s",
            hero_to_token={},
            created_at=float(i),
            save_dir=save_dir,
        )

    games = load_all_games(save_dir)
    assert len(games) == 3
    ids = {g["game_id"] for g in games}
    assert ids == {"game_0", "game_1", "game_2"}


def test_load_all_games_skips_corrupt(full_state, save_dir):
    """Corrupt files are skipped without crashing."""
    save_game(
        game_id="good",
        state=full_state,
        player_tokens={},
        spectator_token="s",
        hero_to_token={},
        created_at=0,
        save_dir=save_dir,
    )
    # Write a corrupt file
    with open(os.path.join(save_dir, "bad.json"), "w") as f:
        f.write("{corrupt")

    games = load_all_games(save_dir)
    assert len(games) == 1
    assert games[0]["game_id"] == "good"


def test_load_all_games_empty_dir(save_dir):
    """Empty directory returns empty list."""
    assert load_all_games(save_dir) == []


def test_load_all_games_missing_dir():
    """Non-existent directory returns empty list."""
    assert load_all_games("/nonexistent/path") == []


def test_delete_game_save(full_state, save_dir):
    """delete_game_save removes the file."""
    save_game(
        game_id="del_me",
        state=full_state,
        player_tokens={},
        spectator_token="s",
        hero_to_token={},
        created_at=0,
        save_dir=save_dir,
    )
    assert os.path.exists(os.path.join(save_dir, "del_me.json"))

    delete_game_save("del_me", save_dir)
    assert not os.path.exists(os.path.join(save_dir, "del_me.json"))


def test_delete_nonexistent_save(save_dir):
    """Deleting a nonexistent save doesn't raise."""
    delete_game_save("nope", save_dir)  # Should not raise


# ---------------------------------------------------------------------------
# Mid-resolution round-trip (full game state)
# ---------------------------------------------------------------------------


def test_mid_resolution_round_trip(save_dir):
    """A game mid-resolution (with steps, context, etc.) round-trips correctly."""
    state = GameSetup.create_game(MAP_PATH, ["Arien"], ["Wasp"])

    # Transition to resolution by committing cards for all heroes
    session = GameSession(state)
    for team in state.teams.values():
        for hero in team.heroes:
            if hero.hand:
                session.commit_card(hero.id, hero.hand[0])

    # Now in resolution — there should be steps on the stack
    save_game(
        game_id="midres",
        state=state,
        player_tokens={"t1": "hero_arien", "t2": "hero_wasp"},
        spectator_token="spec",
        hero_to_token={"hero_arien": "t1", "hero_wasp": "t2"},
        created_at=42.0,
        save_dir=save_dir,
    )

    data = load_game(os.path.join(save_dir, "midres.json"))
    restored = data["session"].state
    assert restored.phase == state.phase
    assert restored.round == state.round
    assert restored.turn == state.turn
