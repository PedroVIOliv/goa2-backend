"""ResolveCardStep fires the AFTER_RESOLVE_CARD passive trigger (Wuk's March)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.steps import ResolveCardStep
from goa2.engine.steps.effects import CheckPassiveAbilitiesStep


def _move_card() -> Card:
    return Card(
        id="basic_move",
        name="Basic Move",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=1,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _state() -> GameState:
    board = Board()
    board.zones = {"z": Zone(id="z", hexes={Hex(q=q, r=0, s=-q) for q in range(5)})}
    board.populate_tiles_from_zones()
    card = _move_card()
    hero = Hero(id=HeroID("hero_x"), name="X", team=TeamColor.RED, deck=[], level=1)
    hero.current_turn_card = card
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_x",
    )
    state.place_entity("hero_x", Hex(q=0, r=0, s=0))
    return state


def test_resolve_card_schedules_after_resolve_card_check() -> None:
    state = _state()
    step = ResolveCardStep(hero_id="hero_x")
    step.pending_input = {"selection": "MOVEMENT"}
    steps = step.resolve(state, {}).new_steps

    triggers = [s.trigger for s in steps if isinstance(s, CheckPassiveAbilitiesStep)]
    assert "after_resolve_card" in triggers
    # It must come last, after the action's own AFTER_* checks.
    after_resolve_idx = next(
        i
        for i, s in enumerate(steps)
        if isinstance(s, CheckPassiveAbilitiesStep) and s.trigger == "after_resolve_card"
    )
    assert after_resolve_idx == len(steps) - 1
