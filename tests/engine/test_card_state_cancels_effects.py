"""A card changing state (discarded, swapped, retrieved) cancels its active
effect, per the Changing Card State rules. Cancellation is a *premature* end,
so finishing_steps do not run (see expire_by_card)."""

from goa2.domain.board import Board
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import CardContainerType
from goa2.domain.state import GameState
from goa2.engine.steps.cards import DiscardCardStep, RetrieveCardStep, SwapCardStep


def _card(card_id: str, state: CardState = CardState.RESOLVED) -> Card:
    c = Card(
        id=card_id,
        name=card_id,
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )
    c.state = state
    return c


def _active_effect(card_id: str) -> ActiveEffect:
    return ActiveEffect(
        id=f"eff_{card_id}",
        source_id="hero_1",
        source_card_id=card_id,
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_ROUND,
        is_active=True,
        created_at_turn=1,
        created_at_round=1,
    )


def _state_with_hero(hero: Hero) -> GameState:
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        turn=1,
        round=1,
    )
    state.current_actor_id = "hero_1"
    return state


def _effect_ids(state: GameState) -> set[str]:
    return {e.id for e in state.active_effects}


def test_discarding_played_card_cancels_its_active_effect():
    card = _card("card_a")
    hero = Hero(id="hero_1", name="H", team=TeamColor.RED, deck=[], played_cards=[card])
    state = _state_with_hero(hero)
    state.active_effects.append(_active_effect("card_a"))

    DiscardCardStep(card_id="card_a", hero_id="hero_1", source=CardContainerType.PLAYED).resolve(
        state, {}
    )

    assert "eff_card_a" not in _effect_ids(state)


def test_swapping_card_cancels_active_effect():
    active_card = _card("card_a")
    bench_card = _card("card_b", state=CardState.DISCARD)
    hero = Hero(
        id="hero_1",
        name="H",
        team=TeamColor.RED,
        deck=[],
        discard_pile=[bench_card],
    )
    hero.current_turn_card = active_card
    state = _state_with_hero(hero)
    state.active_effects.append(_active_effect("card_a"))

    SwapCardStep(target_card_id="card_b").resolve(state, {})

    assert "eff_card_a" not in _effect_ids(state)


def test_retrieving_played_card_cancels_active_effect():
    card = _card("card_a")
    hero = Hero(id="hero_1", name="H", team=TeamColor.RED, deck=[], played_cards=[card])
    state = _state_with_hero(hero)
    state.active_effects.append(_active_effect("card_a"))

    RetrieveCardStep(card_key="rc").resolve(state, {"rc": "card_a"})

    assert "eff_card_a" not in _effect_ids(state)
