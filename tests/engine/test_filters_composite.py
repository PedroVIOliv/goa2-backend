"""Tests for OrFilter, AndFilter composite filters."""

import goa2.engine.step_types  # noqa: F401 — triggers model patching for serialization tests
import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.models.token import Token
from goa2.domain.models.enums import TokenType
from goa2.domain.hex import Hex
from goa2.engine.filters import (
    OrFilter,
    AndFilter,
    TeamFilter,
    UnitTypeFilter,
    RangeFilter,
)


@pytest.fixture
def composite_state():
    board = Board()
    hexes = [
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=1, r=-1, s=0),
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)

    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.RED)
    token = Token(id="token_1", name="Obstacle Token", token_type=TokenType.SMOKE_BOMB)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[]),
        },
        entity_locations={},
        current_actor_id="h1",
    )
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("h2", Hex(q=1, r=0, s=-1))
    state.place_entity("m1", Hex(q=0, r=1, s=-1))
    state.register_entity(token)
    state.place_entity("token_1", Hex(q=1, r=-1, s=0))

    return state


class TestOrFilter:
    def test_passes_if_first_filter_passes(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        # h2 is enemy — passes via first filter
        assert f.apply("h2", composite_state, {}) is True

    def test_passes_if_second_filter_passes(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        # token_1 has no team, so TeamFilter fails, but UnitTypeFilter("TOKEN") passes
        assert f.apply("token_1", composite_state, {}) is True

    def test_fails_if_neither_passes(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        # m1 is friendly, not a token — both fail
        assert f.apply("m1", composite_state, {}) is False

    def test_empty_or_filter_fails(self, composite_state):
        f = OrFilter(filters=[])
        assert f.apply("h2", composite_state, {}) is False


class TestAndFilter:
    def test_passes_if_all_pass(self, composite_state):
        f = AndFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="HERO"),
        ])
        # h2 is enemy hero — both pass
        assert f.apply("h2", composite_state, {}) is True

    def test_fails_if_one_fails(self, composite_state):
        f = AndFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="MINION"),
        ])
        # h2 is enemy but not a minion
        assert f.apply("h2", composite_state, {}) is False

    def test_empty_and_filter_passes(self, composite_state):
        f = AndFilter(filters=[])
        assert f.apply("h2", composite_state, {}) is True


class TestOrFilterBroganPattern:
    """Tests the specific pattern used in Brogan's push effects."""

    def test_enemy_unit_passes(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        assert f.apply("h2", composite_state, {}) is True

    def test_token_passes(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        assert f.apply("token_1", composite_state, {}) is True

    def test_friendly_unit_rejected(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        assert f.apply("m1", composite_state, {}) is False

    def test_self_rejected(self, composite_state):
        f = OrFilter(filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="TOKEN"),
        ])
        assert f.apply("h1", composite_state, {}) is False


class TestCompositeFilterSerialization:
    """Tests that OrFilter/AndFilter round-trip through Pydantic serialization."""

    def test_or_filter_round_trip(self):
        from goa2.engine.steps import SelectStep
        from goa2.domain.models.enums import TargetType

        step = SelectStep(
            target_type=TargetType.UNIT,
            prompt="test",
            output_key="test_key",
            filters=[
                OrFilter(filters=[
                    TeamFilter(relation="ENEMY"),
                    UnitTypeFilter(unit_type="TOKEN"),
                ]),
                RangeFilter(max_range=1),
            ],
        )
        data = step.model_dump()
        restored = SelectStep.model_validate(data)
        assert len(restored.filters) == 2
        assert isinstance(restored.filters[0], OrFilter)
        assert len(restored.filters[0].filters) == 2
        assert isinstance(restored.filters[0].filters[0], TeamFilter)
        assert isinstance(restored.filters[0].filters[1], UnitTypeFilter)

    def test_and_filter_round_trip(self):
        from goa2.engine.steps import SelectStep
        from goa2.domain.models.enums import TargetType

        step = SelectStep(
            target_type=TargetType.UNIT,
            prompt="test",
            output_key="test_key",
            filters=[
                AndFilter(filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=2),
                ]),
            ],
        )
        data = step.model_dump()
        restored = SelectStep.model_validate(data)
        assert isinstance(restored.filters[0], AndFilter)
        assert len(restored.filters[0].filters) == 2

    def test_nested_composite_round_trip(self):
        from goa2.engine.steps import SelectStep
        from goa2.domain.models.enums import TargetType

        step = SelectStep(
            target_type=TargetType.UNIT,
            prompt="test",
            output_key="test_key",
            filters=[
                OrFilter(filters=[
                    AndFilter(filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="HERO"),
                    ]),
                    UnitTypeFilter(unit_type="TOKEN"),
                ]),
            ],
        )
        data = step.model_dump()
        restored = SelectStep.model_validate(data)
        or_f = restored.filters[0]
        assert isinstance(or_f, OrFilter)
        assert isinstance(or_f.filters[0], AndFilter)
        assert isinstance(or_f.filters[1], UnitTypeFilter)
