"""Min mine ownership and immunity-source contracts."""

from __future__ import annotations

import pytest

import goa2.scripts.min_effects  # noqa: F401
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]


def _add_mine_pool(state, token_type: TokenType, count: int) -> None:
    state.token_pool[token_type] = []
    for index in range(count):
        token = Token(
            id=f"{token_type.value}_{index}",
            name="Mine",
            token_type=token_type,
        )
        state.register_entity(token)
        state.token_pool[token_type].append(token)


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "blast_count", "dud_count"),
    [
        ("trip_mine", 1, 1),
        ("cluster_mine", 1, 2),
        ("minefield", 2, 1),
    ],
)
def test_mine_cards_record_min_as_owner(card_id: str, blast_count: int, dud_count: int) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_min", at=(0, 0, 0), current_card=hero_card("Min", card_id))
        .with_actor("hero_min")
        .build()
    )
    _add_mine_pool(state, TokenType.MINE_BLAST, blast_count)
    _add_mine_pool(state, TokenType.MINE_DUD, dud_count)
    destinations = [
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
    ]

    run = run_card(state, "hero_min")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    for destination in destinations[: blast_count + dud_count]:
        run.expect_input(InputRequestType.SELECT_HEX).choose(destination)
    run.finish()

    placed = [
        token
        for token_type in (TokenType.MINE_BLAST, TokenType.MINE_DUD)
        for token in state.token_pool[token_type]
        if state.get_position(str(token.id)) is not None
    ]
    assert len(placed) == blast_count + dud_count
    assert all(str(token.owner_id) == "hero_min" for token in placed)
