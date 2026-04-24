"""Tests for Silverarrow PR4 card effects.

Covered:
- Family 8 SILVER Trailblazer: optional fast travel plus round-long friendly
  hero movement-action aura that ignores obstacles.
"""

import pytest

import goa2.scripts.silverarrow_effects  # noqa: F401 - registers effects
import goa2.data.heroes.silverarrow  # noqa: F401 - registers hero
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import DurationType, EffectType, Hero, Team, TeamColor
from goa2.domain.models.effect import AffectsFilter, Shape
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.steps import CreateEffectStep, FastTravelSequenceStep


def _card_by_id(card_id: str):
    hero = HeroRegistry.get("Silverarrow")
    card = next((c for c in hero.deck if c.id == card_id), None)
    assert card is not None, f"Silverarrow has no card {card_id}"
    return card


@pytest.fixture
def silver_state():
    board = Board()
    hexes = set()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

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
    state.place_entity("hero_silverarrow", Hex(q=0, r=0, s=0))
    state.place_entity("ally_hero", Hex(q=2, r=0, s=-2))
    state.place_entity("enemy_hero", Hex(q=1, r=-2, s=1))
    state.current_actor_id = "hero_silverarrow"
    return state


class TestTrailblazer:
    def test_registered(self):
        assert CardEffectRegistry.get("trailblazer") is not None

    def test_fast_travel_then_creates_movement_aura(self, silver_state):
        effect = CardEffectRegistry.get("trailblazer")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("trailblazer")

        steps = effect.get_steps(silver_state, hero, card)

        assert len(steps) == 2
        fast_travel, create = steps

        assert isinstance(fast_travel, FastTravelSequenceStep)
        assert fast_travel.unit_id == "hero_silverarrow"

        assert isinstance(create, CreateEffectStep)
        assert create.effect_type == EffectType.MOVEMENT_AURA_ZONE
        assert create.scope.shape == Shape.RADIUS
        assert create.scope.range == card.radius_value
        assert create.scope.origin_id == "hero_silverarrow"
        assert create.scope.affects == AffectsFilter.SELF_AND_FRIENDLY_HEROES
        assert create.duration == DurationType.THIS_ROUND
        assert create.grants_pass_through_obstacles is True

    def test_created_effect_preserves_pass_through_payload(self, silver_state):
        effect = CardEffectRegistry.get("trailblazer")
        hero = silver_state.get_hero("hero_silverarrow")
        card = _card_by_id("trailblazer")
        create = effect.get_steps(silver_state, hero, card)[1]

        create.resolve(
            silver_state,
            {
                "current_card_id": "trailblazer",
                "current_action_type": card.primary_action,
            },
        )

        created = silver_state.active_effects[-1]
        assert created.effect_type == EffectType.MOVEMENT_AURA_ZONE
        assert created.source_card_id == "trailblazer"
        assert created.grants_pass_through_obstacles is True
