"""Tests for Silverarrow PR4 card effects.

Covered:
- Family 8 SILVER Trailblazer: optional fast travel plus round-long friendly
  hero movement-action aura that ignores obstacles.
- Family 9 ULTIMATE Wild Hunt: before-action optional straight-line nudge.
"""

import pytest

import goa2.scripts.silverarrow_effects  # noqa: F401 - registers effects
import goa2.data.heroes.silverarrow  # noqa: F401 - registers hero
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import DurationType, EffectType, Hero, Team, TeamColor
from goa2.domain.models.enums import PassiveTrigger
from goa2.domain.models.effect import AffectsFilter, Shape
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters import (
    InStraightLineFilter,
    ObstacleFilter,
    RangeFilter,
    StraightLinePathFilter,
)
from goa2.engine.steps import (
    CheckPassiveAbilitiesStep,
    CreateEffectStep,
    FastTravelSequenceStep,
    MarkPassiveUsedStep,
    MoveUnitStep,
    OfferPassiveStep,
    SelectStep,
)


def _card_by_id(card_id: str):
    hero = HeroRegistry.get("Silverarrow")
    card = next((c for c in hero.deck if c.id == card_id), None)
    if card is None and hero.ultimate_card and hero.ultimate_card.id == card_id:
        card = hero.ultimate_card
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
    silver.level = 8

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


class TestWildHunt:
    def test_registered(self):
        assert CardEffectRegistry.get("wild_hunt") is not None

    def test_passive_config(self):
        effect = CardEffectRegistry.get("wild_hunt")
        config = effect.get_passive_config()

        assert config is not None
        assert config.trigger == PassiveTrigger.BEFORE_ACTION
        assert config.uses_per_turn == 0
        assert config.is_optional is True

    def test_before_action_offers_ultimate_at_level_8(self, silver_state):
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ACTION.value)

        result = step.resolve(silver_state, {})

        assert len(result.new_steps) == 1
        offer = result.new_steps[0]
        assert isinstance(offer, OfferPassiveStep)
        assert offer.card_id == "wild_hunt"
        assert offer.trigger == PassiveTrigger.BEFORE_ACTION.value

    def test_accepting_passive_spawns_straight_line_nudge(self, silver_state):
        step = OfferPassiveStep(
            card_id="wild_hunt",
            trigger=PassiveTrigger.BEFORE_ACTION.value,
            is_optional=True,
        )
        step.pending_input = {"selection": "YES"}

        result = step.resolve(silver_state, {})

        assert len(result.new_steps) == 3
        select, move, mark = result.new_steps

        assert isinstance(select, SelectStep)
        assert select.output_key == "wild_hunt_dest"
        assert select.is_mandatory is False
        assert any(
            isinstance(f, RangeFilter) and f.max_range == 2
            for f in select.filters
        )
        assert any(isinstance(f, InStraightLineFilter) for f in select.filters)
        assert any(isinstance(f, StraightLinePathFilter) for f in select.filters)
        assert any(isinstance(f, ObstacleFilter) for f in select.filters)

        assert isinstance(move, MoveUnitStep)
        assert move.unit_id == "hero_silverarrow"
        assert move.destination_key == "wild_hunt_dest"
        assert move.range_val == 2
        assert move.is_movement_action is False
        assert move.active_if_key == "wild_hunt_dest"

        assert isinstance(mark, MarkPassiveUsedStep)
        assert mark.card_id == "wild_hunt"
