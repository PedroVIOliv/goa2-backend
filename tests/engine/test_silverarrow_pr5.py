"""Silverarrow integration tests.

These tests cover card behavior through the real engine steps rather than only
checking the card effect's step shape.
"""

import pytest

import goa2.data.heroes.silverarrow  # noqa: F401 - registers hero
import goa2.scripts.silverarrow_effects  # noqa: F401 - registers effects
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters import MovementPathFilter
from goa2.engine.steps import MoveSequenceStep, MoveUnitStep, SelectStep


def _card_by_id(card_id: str):
    hero = HeroRegistry.get("Silverarrow")
    card = next((c for c in hero.deck if c.id == card_id), None)
    assert card is not None, f"Silverarrow has no card {card_id}"
    return card


@pytest.fixture
def trailblazer_state():
    board = Board()
    hexes = set()
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            if abs(s) <= 3:
                hexes.add(Hex(q=q, r=r, s=s))
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()
    board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    silver = HeroRegistry.get("Silverarrow")
    silver.team = TeamColor.RED
    silver.hand = []

    ally = Hero(id="ally_hero", name="Ally", team=TeamColor.RED, deck=[])
    enemy = Hero(id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[])

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[silver, ally], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_silverarrow", Hex(q=0, r=1, s=-1))
    state.place_entity("ally_hero", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_hero", Hex(q=0, r=-1, s=1))
    return state


def _activate_trailblazer(state: GameState):
    effect = CardEffectRegistry.get("trailblazer")
    hero = state.get_hero("hero_silverarrow")
    card = _card_by_id("trailblazer")
    create = effect.get_steps(state, hero, card)[1]
    state.current_actor_id = "hero_silverarrow"
    create.resolve(
        state,
        {
            "current_card_id": "trailblazer",
            "current_action_type": card.primary_action,
        },
    )
    state.active_effects[-1].is_active = True


def _expand_move(state: GameState, unit_id: str):
    state.current_actor_id = unit_id
    result = MoveSequenceStep(unit_id=unit_id, range_val=2).resolve(state, {})
    assert len(result.new_steps) == 2
    select, move = result.new_steps
    assert isinstance(select, SelectStep)
    assert isinstance(move, MoveUnitStep)
    movement_filters = [
        f for f in select.filters if isinstance(f, MovementPathFilter)
    ]
    assert len(movement_filters) == 1
    return movement_filters[0], move


def test_trailblazer_lets_friendly_hero_move_through_obstacle(trailblazer_state):
    _activate_trailblazer(trailblazer_state)
    destination = Hex(q=2, r=0, s=-2)

    path_filter, move = _expand_move(trailblazer_state, "ally_hero")

    assert path_filter.pass_through_obstacles is True
    assert path_filter.apply(destination, trailblazer_state, {}) is True

    move.resolve(trailblazer_state, {"target_hex": destination})
    assert trailblazer_state.entity_locations[BoardEntityID("ally_hero")] == destination


def test_trailblazer_does_not_help_enemy_movement(trailblazer_state):
    _activate_trailblazer(trailblazer_state)
    trailblazer_state.move_unit("ally_hero", Hex(q=-1, r=0, s=1))
    trailblazer_state.move_unit("enemy_hero", Hex(q=0, r=0, s=0))
    destination = Hex(q=2, r=0, s=-2)

    path_filter, move = _expand_move(trailblazer_state, "enemy_hero")

    assert path_filter.pass_through_obstacles is False
    assert path_filter.apply(destination, trailblazer_state, {}) is False

    move.resolve(trailblazer_state, {"target_hex": destination})
    assert trailblazer_state.entity_locations[BoardEntityID("enemy_hero")] == Hex(
        q=0, r=0, s=0
    )
