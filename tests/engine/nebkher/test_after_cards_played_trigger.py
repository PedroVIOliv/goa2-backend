"""AFTER_CARDS_PLAYED_TRIGGER firing point (NebKher P3 — Imbue Doubt family).

"Next turn, after playing cards:" — the payload fires after every player has
committed AND revealed cards on the following turn, before any card resolves.

Locked interpretations / spec decisions (2026-07-07):
- Fires at the revelation→resolution boundary, before the first actor.
- Payload runs with the effect's SOURCE as current actor (prompt routing,
  Team/Range filters relative to the scheduler).
- Round boundary → fizzles silently (NEXT_TURN never crosses rounds).
- The generic end-of-turn expiry must NEVER run this payload (it would
  otherwise double-fire or fire a round late).
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    GamePhase,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import TargetType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack
from goa2.engine.phases import commit_card, end_turn
from goa2.engine.steps import SelectStep, SetContextFlagStep


def _hand_card(card_id: str) -> Card:
    return Card(
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


def _state() -> GameState:
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(5)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    source = Hero(id="hero_source", name="Source", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    source.hand = [_hand_card("src_next")]
    enemy.hand = [_hand_card("enm_next")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[source], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_source", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=2, r=0, s=-2))
    state.turn = 1
    state.round = 1
    return state


def _schedule(state: GameState, finishing_steps: list) -> ActiveEffect:
    effect = ActiveEffect(
        id="fx_acp",
        effect_type=EffectType.AFTER_CARDS_PLAYED_TRIGGER,
        source_id="hero_source",
        source_card_id="card_imbue_doubt",
        scope=EffectScope(shape=Shape.GLOBAL, origin_id="hero_source"),
        duration=DurationType.NEXT_TURN,
        is_active=True,
        created_at_turn=state.turn,
        created_at_round=state.round,
        finishing_steps=finishing_steps,
    )
    state.active_effects.append(effect)
    return effect


def _advance_to_next_turn_reveal(state: GameState) -> None:
    """End the current turn, then commit both heroes' cards (which triggers
    revelation + resolution start)."""
    end_turn(state)
    assert state.phase == GamePhase.PLANNING
    source = state.get_hero("hero_source")
    enemy = state.get_hero("hero_enemy")
    commit_card(state, source.id, source.hand[0])
    commit_card(state, enemy.id, enemy.hand[0])


def test_payload_fires_after_reveal_before_any_resolution() -> None:
    state = _state()
    _schedule(state, [SetContextFlagStep(key="acp_fired", value=True)])

    _advance_to_next_turn_reveal(state)
    assert state.phase == GamePhase.RESOLUTION

    # Both revealed cards are still unresolved when the payload runs: the
    # flag-setting step sits on the stack before FindNextActor. Process just
    # the payload portion by stepping until the flag appears.
    process_stack(state)
    assert state.execution_context.get("acp_fired") is True

    # The trigger effect was consumed — it must not linger.
    assert not any(
        e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER for e in state.active_effects
    )


def test_payload_pauses_for_input_before_first_actor_with_source_as_actor() -> None:
    """An input-requiring payload pauses the stack before any hero acts,
    and the prompt is routed to the SOURCE hero."""
    state = _state()
    _schedule(
        state,
        [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="payload choice",
                output_key="acp_choice",
                number_options=[1, 2],
            )
        ],
    )

    _advance_to_next_turn_reveal(state)
    result = process_stack(state)

    assert result.input_request is not None
    assert result.input_request.prompt == "payload choice"
    assert result.input_request.player_id == "hero_source"
    # No hero has resolved yet — both cards still unresolved.
    assert set(state.unresolved_hero_ids) == {"hero_source", "hero_enemy"}


def test_cross_round_trigger_fizzles_silently() -> None:
    """An effect scheduled in a previous round never fires."""
    state = _state()
    effect = _schedule(state, [SetContextFlagStep(key="acp_fired", value=True)])
    effect.created_at_round = state.round - 1  # simulate: scheduled last round

    _advance_to_next_turn_reveal(state)
    process_stack(state)

    assert state.execution_context.get("acp_fired") is None
    assert not any(
        e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER for e in state.active_effects
    )


def test_generic_turn_expiry_never_runs_the_payload() -> None:
    """If the trigger somehow reaches the generic NEXT_TURN expiry (e.g. it
    was already due at the end of a turn), the payload must NOT fire there."""
    state = _state()
    effect = _schedule(state, [SetContextFlagStep(key="acp_fired", value=True)])
    # Make it look one turn old: generic expiry at end of THIS turn would
    # normally collect an active NEXT_TURN effect's finishing steps.
    effect.created_at_turn = state.turn - 1

    end_turn(state)
    process_stack(state)

    assert state.execution_context.get("acp_fired") is None
    assert not any(
        e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER for e in state.active_effects
    )
