"""SwapResolvedCardsStep (NebKher P7 — Diabolical Laughter bullet 3).

"Swap two resolved cards of an enemy hero in radius, without canceling
active effects." — swaps the two cards' positions in the played slots;
active effects bound to either card keep running (unlike SwapCardStep,
which expires them); previous-turn-slot lookups see the new order.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import SwapResolvedCardsStep


def _card(card_id: str, state: CardState = CardState.RESOLVED) -> Card:
    card = Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=5,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id="",
        effect_text="",
    )
    card.state = state
    card.is_facedown = False
    return card


def _state() -> GameState:
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(4)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    actor = Hero(id="hero_actor", name="Actor", team=TeamColor.RED, deck=[], level=1)
    victim = Hero(id="hero_victim", name="Victim", team=TeamColor.BLUE, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[actor], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[victim], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_actor", Hex(q=0, r=0, s=0))
    state.place_entity("hero_victim", Hex(q=2, r=0, s=-2))
    state.current_actor_id = "hero_actor"
    return state


def _run_swap(state: GameState, card_a: str, card_b: str) -> None:
    state.execution_context["swap_victim"] = "hero_victim"
    state.execution_context["swap_card_a"] = card_a
    state.execution_context["swap_card_b"] = card_b
    push_steps(
        state,
        [
            SwapResolvedCardsStep(
                hero_key="swap_victim",
                card_a_key="swap_card_a",
                card_b_key="swap_card_b",
            )
        ],
    )
    process_stack(state)


def test_swap_reorders_played_slots_and_keeps_states() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.played_cards = [_card("card_t1"), _card("card_t2")]
    victim.resolved_turn_count = 2

    _run_swap(state, "card_t1", "card_t2")

    assert [c.id for c in victim.played_cards] == ["card_t2", "card_t1"]
    assert all(c.state == CardState.RESOLVED for c in victim.played_cards)


def test_swap_does_not_cancel_active_effects() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.played_cards = [_card("card_t1"), _card("card_t2")]
    victim.resolved_turn_count = 2
    state.active_effects.append(
        ActiveEffect(
            id="fx_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            source_id="hero_victim",
            source_card_id="card_t1",
            scope=EffectScope(shape=Shape.POINT, origin_id="hero_victim"),
            duration=DurationType.THIS_ROUND,
            is_active=True,
            created_at_turn=state.turn,
            created_at_round=state.round,
        )
    )

    _run_swap(state, "card_t1", "card_t2")

    assert any(e.source_card_id == "card_t1" and e.is_active for e in state.active_effects)


def test_swap_changes_previous_turn_slot_lookup() -> None:
    """Prev-slot references (Mind Grip / Cutter ult) must see the new order."""
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.played_cards = [_card("card_t1"), _card("card_t2")]
    victim.resolved_turn_count = 2

    _run_swap(state, "card_t1", "card_t2")

    prev_slot = victim.played_cards[victim.resolved_turn_count - 1]
    assert prev_slot is not None and prev_slot.id == "card_t1"


def test_swap_noops_when_a_card_is_not_resolved() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.played_cards = [_card("card_t1"), _card("card_t2", state=CardState.UNRESOLVED)]
    victim.resolved_turn_count = 1

    _run_swap(state, "card_t1", "card_t2")

    assert [c.id for c in victim.played_cards] == ["card_t1", "card_t2"]


def test_swap_noops_when_card_missing() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.played_cards = [_card("card_t1")]
    victim.resolved_turn_count = 1

    _run_swap(state, "card_t1", "card_nonexistent")

    assert [c.id for c in victim.played_cards] == ["card_t1"]
