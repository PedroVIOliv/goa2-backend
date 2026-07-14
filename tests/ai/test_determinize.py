"""Tests for ISMCTS determinization."""

from __future__ import annotations

import random

from automata.determinize import determinize
from automata.effects import register_all_effects
from automata.harness import DEFAULT_MAP
from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.phases import commit_card
from goa2.engine.setup import GameSetup


def _fresh() -> GameState:
    register_all_effects()
    return GameSetup.create_game(
        DEFAULT_MAP, ["Wasp", "Xargatha"], ["Arien", "Brogan"], game_type="QUICK", seed=1
    )


def test_determinize_resamples_enemy_commit_and_leaves_original() -> None:
    state = _fresh()
    assert state.phase == GamePhase.PLANNING
    blue_hero = state.teams[TeamColor.BLUE].heroes[0]
    hand_ids = {c.id for c in blue_hero.hand}
    committed = blue_hero.hand[0]
    commit_card(state, HeroID(blue_hero.id), committed)
    assert state.pending_inputs[HeroID(blue_hero.id)].id == committed.id

    # Perspective RED must not see BLUE's real commit; determinize resamples it.
    clone = determinize(state, TeamColor.RED, random.Random(0))
    clone_commit = clone.pending_inputs[HeroID(blue_hero.id)]
    assert clone_commit is not None
    assert clone_commit.id in hand_ids  # a legal card from that hero's hand

    # Original is untouched.
    assert state.pending_inputs[HeroID(blue_hero.id)].id == committed.id


def test_determinize_keeps_own_team_commit() -> None:
    state = _fresh()
    red_hero = state.teams[TeamColor.RED].heroes[0]
    committed = red_hero.hand[0]
    commit_card(state, HeroID(red_hero.id), committed)

    clone = determinize(state, TeamColor.RED, random.Random(0))
    # Our own commit is preserved (we control it / know it).
    assert clone.pending_inputs[HeroID(red_hero.id)].id == committed.id


def test_determinize_is_deterministic_given_rng() -> None:
    def run() -> str | None:
        state = _fresh()
        bh = state.teams[TeamColor.BLUE].heroes[0]
        commit_card(state, HeroID(bh.id), bh.hand[0])
        clone = determinize(state, TeamColor.RED, random.Random(42))
        c = clone.pending_inputs[HeroID(bh.id)]
        return c.id if c else None

    assert run() == run()


def test_determinize_outside_planning_is_plain_clone() -> None:
    state = _fresh()
    state.phase = GamePhase.RESOLUTION
    clone = determinize(state, TeamColor.RED, random.Random(0))
    assert clone is not state
    assert clone.phase == GamePhase.RESOLUTION
