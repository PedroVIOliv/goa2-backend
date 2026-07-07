"""LaughStep + AFTER_LAUGH passive trigger (NebKher P6).

Locked interpretation (2026-07-07): the laugh is a YES/NO confirm; declining
does nothing at all. The ultimate fires immediately after the laugh, before
any subsequent steps of the laughing card's effect.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import (
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.enums import ActionType, PassiveTrigger
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import CheckContextConditionStep, LaughStep, SetContextFlagStep

DUMMY_PASSIVE_ID = "test_after_laugh_passive"


@register_effect(DUMMY_PASSIVE_ID)
class _AfterLaughPassive(CardEffect):
    """Test-only ultimate passive that marks context when the laugh fires."""

    def get_passive_config(self):
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_LAUGH,
            uses_per_turn=0,
            is_optional=False,
        )

    def get_passive_steps(self, state, hero, card, trigger, context):
        return [SetContextFlagStep(key="after_laugh_fired", value=1)]


def _ultimate_card() -> Card:
    card = Card(
        id="test_laugh_ultimate",
        name="Test Laugh Ultimate",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id=DUMMY_PASSIVE_ID,
        effect_text="",
    )
    card.state = CardState.PASSIVE
    card.is_facedown = False
    return card


def _laugh_state(*, with_ultimate: bool) -> GameState:
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(6)}
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    laugher = Hero(id="hero_laugher", name="Laugher", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[laugher], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION
    state.place_entity("hero_laugher", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=3, r=0, s=-3))
    state.current_actor_id = "hero_laugher"

    if with_ultimate:
        laugher.level = 8
        laugher.ultimate_card = _ultimate_card()
    return state


def test_laugh_yes_sets_flag_and_emits_event() -> None:
    state = _laugh_state(with_ultimate=False)
    push_steps(state, [LaughStep(output_key="laughed")])

    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "CONFIRM_PASSIVE"

    state.execution_stack[-1].pending_input = {"selection": "YES"}
    result = process_stack(state)

    assert state.execution_context.get("laughed") is True
    assert any(e.event_type == GameEventType.HERO_LAUGHED for e in result.events)


def test_laugh_no_leaves_flag_unset_and_no_event() -> None:
    state = _laugh_state(with_ultimate=False)
    push_steps(state, [LaughStep(output_key="laughed")])

    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "NO"}
    result = process_stack(state)

    assert state.execution_context.get("laughed") is None
    assert not any(e.event_type == GameEventType.HERO_LAUGHED for e in result.events)


def test_laugh_yes_fires_after_laugh_passive_before_following_steps() -> None:
    """The AFTER_LAUGH passive resolves BEFORE steps queued after LaughStep."""
    state = _laugh_state(with_ultimate=True)

    # Probe queued after the laugh: it stores True only if the passive's
    # context flag is already present when it runs — a real ordering check.
    push_steps(
        state,
        [
            LaughStep(output_key="laughed"),
            CheckContextConditionStep(
                input_key="after_laugh_fired",
                operator=">=",
                threshold=1,
                output_key="passive_ran_before_probe",
            ),
        ],
    )

    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "YES"}
    process_stack(state)

    assert state.execution_context.get("after_laugh_fired") == 1
    assert state.execution_context.get("passive_ran_before_probe") is True


def test_laugh_no_does_not_fire_passive() -> None:
    state = _laugh_state(with_ultimate=True)
    push_steps(state, [LaughStep(output_key="laughed")])

    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "NO"}
    process_stack(state)

    assert state.execution_context.get("after_laugh_fired") is None
