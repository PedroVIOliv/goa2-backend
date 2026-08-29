"""Tests for Effect Creation Steps (Phase 4)."""

import pytest

from goa2.domain.board import Board
from goa2.domain.events import GameEventType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import (
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.steps import CreateEffectStep, ResolveCardTextStep


@pytest.fixture
def game_state():
    """Basic game state."""
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        turn=1,
        round=1,
    )
    # Add a hero acting as current actor
    hero = Hero(id="hero_1", name="Hero 1", team=TeamColor.RED, deck=[])
    state.teams[TeamColor.RED].heroes.append(hero)
    state.current_actor_id = "hero_1"
    return state


def test_create_effect_step_basic(game_state):
    """Test CreateEffectStep creates a spatial effect in state."""
    step = CreateEffectStep(
        effect_type=EffectType.MOVEMENT_ZONE,
        scope=EffectScope(shape=Shape.RADIUS, range=2),
        duration=DurationType.THIS_TURN,
        max_value=1,
    )

    context = {"current_card_id": "card_2"}

    result = step.resolve(game_state, context)

    assert result.is_finished is True
    assert len(game_state.active_effects) == 1

    effect = game_state.active_effects[0]
    assert effect.effect_type == EffectType.MOVEMENT_ZONE
    assert effect.scope.shape == Shape.RADIUS
    assert effect.max_value == 1
    assert effect.source_id == "hero_1"
    assert effect.source_card_id == "card_2"


def test_create_effect_step_prefers_its_bound_card_over_the_context(game_state):
    """Defense text resolves inside the attacker's action context.

    The defense card's steps are bound at build time by
    engine.effects.bind_effect_cards, so the attacker's card named by
    current_card_id must never win.
    """
    step = CreateEffectStep(
        effect_type=EffectType.ATTACK_IMMUNITY,
        scope=EffectScope(shape=Shape.POINT, origin_id="hero_1"),
        duration=DurationType.THIS_ROUND,
        is_active=True,
        source_card_id="defense_card",
    )
    context = {
        "current_action_type": ActionType.DEFENSE,
        "current_card_id": "incoming_attack",
    }

    step.resolve(game_state, context)

    assert game_state.active_effects[0].source_card_id == "defense_card"


def test_reperforming_an_active_effect_emits_no_created_event(game_state):
    step = CreateEffectStep(
        effect_type=EffectType.MOVEMENT_ZONE,
        scope=EffectScope(shape=Shape.RADIUS, range=2, origin_id="hero_1"),
        duration=DurationType.THIS_TURN,
        source_card_id="card_1",
        is_active=True,
    )

    first = step.resolve(game_state, {})
    game_state.current_actor_id = "hero_2"
    second = step.model_copy(
        update={"scope": EffectScope(shape=Shape.RADIUS, range=2, origin_id="hero_2")}
    ).resolve(game_state, {})

    assert len(game_state.active_effects) == 1
    assert [event.event_type for event in first.events] == [GameEventType.EFFECT_CREATED]
    assert second.events == []


def test_resolve_card_sets_current_card_id(game_state):
    """ResolveCardTextStep should set current_card_id in context."""
    # Setup hero with a card in current_turn_card
    hero = game_state.get_hero("hero_1")
    card = Card(
        id="card_abc",
        name="Test Card",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        effect_id="test_effect",
        effect_text="test",
    )
    hero.current_turn_card = card

    step = ResolveCardTextStep(card_id=card.id, hero_id="hero_1")

    context = {}
    step.resolve(game_state, context)

    assert context.get("current_card_id") == "card_abc"
