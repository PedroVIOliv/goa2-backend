from __future__ import annotations

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import RemovePreparedSpellsStep


def _state() -> tuple[GameState, Hero]:
    gydion = HeroRegistry.get("Gydion")
    assert gydion is not None
    gydion.initialize_state()
    gydion.team = TeamColor.RED
    caster = Hero(id="hero_caster", name="Caster", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[gydion]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[caster]),
        },
        current_actor_id=caster.id,
    )
    return state, gydion


def _prepare(gydion: Hero, *spell_ids: str) -> None:
    for spell in gydion.spells:
        if spell.id in spell_ids:
            spell.state = CardState.SPELLBOOK
            spell.is_facedown = True


def test_remove_prepared_spells_can_remove_three_and_reveal_each() -> None:
    state, gydion = _state()
    prepared = ("shield", "suggestion", "burning_hands", "magic_missile")
    _prepare(gydion, *prepared)
    push_steps(state, [RemovePreparedSpellsStep(caster_id="hero_caster", max_removals=3)])

    seen_events = []
    for spell_id in prepared[:3]:
        request = process_stack(state)
        seen_events.extend(request.events)
        assert request.input_request is not None
        assert request.input_request.request_type == InputRequestType.SELECT_CARD
        assert request.input_request.player_id == "hero_caster"
        assert spell_id in {option.id for option in request.input_request.options}
        state.execution_stack[-1].pending_input = {"selection": spell_id}

    finished = process_stack(state)
    seen_events.extend(finished.events)
    assert finished.input_request is None
    assert {spell.id for spell in gydion.spellbook} == {"magic_missile"}
    for spell_id in prepared[:3]:
        spell = state.get_card_by_id(spell_id)
        assert spell is not None
        assert spell.state == CardState.OUTSIDE_SPELLBOOK
        assert spell.is_facedown is False
    removed_events = [
        event
        for event in seen_events
        if event.event_type == GameEventType.SPELL_REMOVED_FROM_SPELLBOOK
    ]
    assert [event.metadata["spell_id"] for event in removed_events] == list(prepared[:3])
    assert all(event.metadata["owner_id"] == gydion.id for event in removed_events)
    assert all(event.metadata["caster_id"] == "hero_caster" for event in removed_events)
    assert all(event.event_type != GameEventType.SPELL_CAST for event in seen_events)


def test_remove_prepared_spells_allows_zero_and_no_candidates_is_noop() -> None:
    state, gydion = _state()
    _prepare(gydion, "shield")
    push_steps(state, [RemovePreparedSpellsStep(caster_id="hero_caster")])
    request = process_stack(state)
    assert request.input_request is not None
    state.execution_stack[-1].pending_input = {"selection": "SKIP"}

    skipped = process_stack(state)
    assert skipped.input_request is None
    assert {spell.id for spell in gydion.spellbook} == {"shield"}
    assert skipped.events == []

    for spell in gydion.spells:
        spell.state = CardState.OUTSIDE_SPELLBOOK
        spell.is_facedown = False
    push_steps(state, [RemovePreparedSpellsStep(caster_id="hero_caster")])
    empty = process_stack(state)
    assert empty.input_request is None
    assert empty.events == []


def test_remove_prepared_spells_rejects_stale_input_without_mutation() -> None:
    state, gydion = _state()
    _prepare(gydion, "shield")
    push_steps(state, [RemovePreparedSpellsStep(caster_id="hero_caster")])
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "magic_missile"}

    stale = process_stack(state)

    assert stale.input_request is not None
    assert {option.id for option in stale.input_request.options} == {"shield"}
    assert {spell.id for spell in gydion.spellbook} == {"shield"}
    assert stale.events == []


def test_remove_prepared_spells_round_trips_while_waiting() -> None:
    state, gydion = _state()
    _prepare(gydion, "shield", "suggestion")
    push_steps(state, [RemovePreparedSpellsStep(caster_id="hero_caster")])
    first = process_stack(state)
    assert first.input_request is not None

    restored = GameState.model_validate_json(state.model_dump_json())
    resumed = process_stack(restored)

    assert resumed.input_request is not None
    assert resumed.input_request.player_id == "hero_caster"
    assert {option.id for option in resumed.input_request.options} == {"shield", "suggestion"}
