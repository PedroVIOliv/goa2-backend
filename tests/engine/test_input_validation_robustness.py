"""Steps must never crash (or place at an unvalidated hex) on bogus client input.

The handler pops a step before calling ``resolve()``. If ``resolve()`` raises
on an invalid selection, the popped step is lost and the game state is left
corrupt. These steps must instead re-request input, and must only accept a
destination the player was actually offered.
"""

from __future__ import annotations

from goa2.domain.hex import Hex
from goa2.domain.input import InputResponse
from goa2.domain.models import (
    ActionType,
    CardColor,
    SpawnPoint,
    SpawnType,
    TeamColor,
)
from goa2.domain.models.card import Card
from goa2.domain.models.enums import CardTier
from goa2.engine.handler import process_stack, submit_input
from goa2.engine.steps.combat import RespawnHeroStep
from goa2.engine.steps.reactions import ReactionWindowStep
from goa2.engine.steps.utility import LogMessageStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _defense_card() -> Card:
    return Card(
        id="def1",
        name="Shield",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=3,
        primary_action=ActionType.DEFENSE,
        primary_action_value=3,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def test_reaction_window_invalid_card_rerequests():
    """A bogus defense-card id must re-open the reaction window, not crash.

    Reachable in every attack: the defender's SELECT_CARD_OR_PASS prompt.
    Previously ``ReactionWindowStep`` raised ValueError on an unknown id, and
    the already-popped step vanished from the stack.
    """
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_att", at=(0, 0, 0))
        .blue_hero("hero_def", at=(1, 1, -2))
        .with_actor("hero_att")
        .build()
    )
    state.get_hero("hero_def").hand.append(_defense_card())
    state.execution_context["target_id"] = "hero_def"
    state.execution_context["attack_damage"] = 5
    state.execution_stack = [
        LogMessageStep(message="SENTINEL"),
        ReactionWindowStep(target_player_key="target_id"),
    ]

    result = process_stack(state)
    assert result.input_request is not None

    submit_input(
        state,
        InputResponse(request_id=result.input_request.id, selection="totally_bogus_card"),
    )
    result = process_stack(state)

    # Re-requests the same reaction window instead of crashing.
    assert result.input_request is not None
    assert any(type(s).__name__ == "ReactionWindowStep" for s in state.execution_stack)
    assert "defense_value" not in state.execution_context


def test_reaction_window_valid_card_still_resolves():
    """The valid path is unchanged: a real defense card is accepted."""
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_att", at=(0, 0, 0))
        .blue_hero("hero_def", at=(1, 1, -2))
        .with_actor("hero_att")
        .build()
    )
    state.get_hero("hero_def").hand.append(_defense_card())
    state.execution_context["target_id"] = "hero_def"
    state.execution_context["attack_damage"] = 5
    state.execution_stack = [ReactionWindowStep(target_player_key="target_id")]

    result = process_stack(state)
    assert result.input_request is not None
    submit_input(state, InputResponse(request_id=result.input_request.id, selection="def1"))
    process_stack(state)

    assert state.execution_context["defense_card_id"] == "def1"
    assert state.execution_context["defense_value"] == 3


def _respawn_state() -> tuple:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_a", at=(0, 0, 0))
        .with_actor("hero_a")
        .build()
    )
    spawn = Hex(q=5, r=0, s=-5)
    state.board.spawn_points.append(
        SpawnPoint(location=spawn, team=TeamColor.RED, type=SpawnType.HERO)
    )
    state.remove_unit("hero_a")
    return state, spawn


def test_respawn_hero_rejects_hex_not_offered():
    """A defeated hero may only respawn on an offered spawn hex.

    Previously ``RespawnHeroStep`` placed the hero at the raw client-submitted
    hex without checking it against the offered spawn hexes, letting a player
    respawn anywhere empty on the board.
    """
    state, spawn = _respawn_state()
    state.execution_stack = [RespawnHeroStep(hero_id="hero_a")]

    result = process_stack(state)
    assert result.input_request is not None
    submit_input(state, InputResponse(request_id=result.input_request.id, selection="RESPAWN"))
    result = process_stack(state)
    assert result.input_request is not None

    # Submit an arbitrary empty hex that is NOT the offered spawn point.
    arbitrary = next(
        h for h, tile in state.board.tiles.items() if not tile.is_occupied and h != spawn
    )
    submit_input(
        state,
        InputResponse(
            request_id=result.input_request.id,
            selection={"q": arbitrary.q, "r": arbitrary.r, "s": arbitrary.s},
        ),
    )
    process_stack(state)

    # The hero must NOT have been placed on the arbitrary hex.
    assert state.entity_locations.get("hero_a") != arbitrary


def test_respawn_hero_accepts_offered_hex():
    """The valid path is unchanged: an offered spawn hex is accepted."""
    state, spawn = _respawn_state()
    state.execution_stack = [RespawnHeroStep(hero_id="hero_a")]

    result = process_stack(state)
    assert result.input_request is not None
    submit_input(state, InputResponse(request_id=result.input_request.id, selection="RESPAWN"))
    result = process_stack(state)
    assert result.input_request is not None
    submit_input(
        state,
        InputResponse(
            request_id=result.input_request.id,
            selection={"q": spawn.q, "r": spawn.r, "s": spawn.s},
        ),
    )
    process_stack(state)

    assert state.entity_locations.get("hero_a") == spawn
