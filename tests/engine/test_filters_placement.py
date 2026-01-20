import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Hero,
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.domain.models.enums import DisplacementType
from goa2.domain.hex import Hex
from goa2.engine.filters import CanBePlacedByActorFilter


@pytest.fixture
def state_with_heroes():
    """State with heroes on both teams and cards."""
    # Create cards for heroes
    red_card = Card(
        id="red_card_1",
        name="Red Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e1",
        effect_text="Attack",
    )
    blue_card = Card(
        id="blue_card_1",
        name="Blue Shield",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=3,
        primary_action=ActionType.DEFENSE,
        primary_action_value=2,
        effect_id="e2",
        effect_text="Defend",
    )

    red_hero = Hero(id="red_hero", name="Red Hero", team=TeamColor.RED, deck=[red_card])
    red_hero.hand.append(red_card)

    blue_hero = Hero(
        id="blue_hero", name="Blue Hero", team=TeamColor.BLUE, deck=[blue_card]
    )
    blue_hero.hand.append(blue_card)

    # Create board with tiles
    board = Board()
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            if abs(s) <= 3:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[red_hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[blue_hero], minions=[]),
        },
        turn=1,
        round=1,
    )

    # Place heroes on board
    state.place_entity("red_hero", Hex(q=0, r=0, s=0))
    state.place_entity("blue_hero", Hex(q=2, r=-1, s=-1))

    return state


@pytest.fixture
def empty_state():
    """Basic state with empty teams."""
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )


class TestCanBePlacedByActorFilter:
    def test_can_be_placed_filter_allows_when_no_effect(self, state_with_heroes):
        state = state_with_heroes

        # Setup: Red hero actor, Blue hero target
        state.current_actor_id = "red_hero"
        target_id = "blue_hero"

        # Filter under test
        filter_cond = CanBePlacedByActorFilter()

        # Should allow placement when no effects exist
        assert filter_cond.apply(target_id, state, {}) is True

    def test_can_be_placed_filter_blocks_when_effect_active(self, state_with_heroes):
        state = state_with_heroes

        # Setup: Red hero actor, Blue hero target
        # Blue hero is at (2, -1, -1)
        # Red hero is at (0, 0, 0) (within radius 3)
        state.current_actor_id = "red_hero"

        # Create Magnetic Dagger effect (Placement Prevention in Radius 3)
        # Source is blue_hero, affects ENEMY_HEROES (Red Hero)
        effect = ActiveEffect(
            id="eff_mag_dagger",
            source_id="blue_hero",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=3,
                origin_id="blue_hero",
                affects=AffectsFilter.ENEMY_HEROES,
            ),
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1,
            displacement_blocks=[DisplacementType.PLACE],
            blocks_enemy_actors=True,
        )
        state.add_effect(effect)

        filter_cond = CanBePlacedByActorFilter()

        # Should return False (Blocked) because Red is affected by the prevention effect
        # and the action is performed by Red (an enemy of the source Blue)
        assert filter_cond.apply("red_hero", state, {}) is False

    def test_can_be_placed_filter_ignores_non_unit_candidates(self, empty_state):
        filter_cond = CanBePlacedByActorFilter()
        # Should return False for Hex candidates (this filter is for Unit selection)
        assert filter_cond.apply(Hex(q=0, r=0, s=0), empty_state, {}) is False
