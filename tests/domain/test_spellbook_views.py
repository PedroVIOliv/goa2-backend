from __future__ import annotations

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board
from goa2.domain.models import CardState, Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.views import build_view


def _state() -> tuple[GameState, Hero, Hero]:
    gydion = HeroRegistry.get("Gydion")
    assert gydion is not None
    gydion.initialize_state()
    gydion.team = TeamColor.RED
    opponent = Hero(
        id="hero_opponent",
        name="Opponent",
        team=TeamColor.BLUE,
        deck=[],
    )
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[gydion], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[opponent], minions=[]),
        },
    )
    for spell in gydion.spells:
        spell.state = CardState.SPELLBOOK
        spell.is_facedown = True
    magic_missile = next(spell for spell in gydion.spells if spell.id == "magic_missile")
    magic_missile.state = CardState.OUTSIDE_SPELLBOOK
    magic_missile.is_facedown = False
    return state, gydion, opponent


def _hero(view: dict, hero_id: str) -> dict:
    return next(
        hero for team in view["teams"].values() for hero in team["heroes"] if hero["id"] == hero_id
    )


def test_spellbook_is_full_for_owner_and_reveal_all_but_count_only_public() -> None:
    state, gydion, opponent = _state()

    owner = _hero(build_view(state, for_hero_id=gydion.id), gydion.id)
    enemy = _hero(build_view(state, for_hero_id=opponent.id), gydion.id)
    spectator = _hero(build_view(state), gydion.id)
    reveal_all = _hero(build_view(state, reveal_all=True), gydion.id)

    assert {spell["id"] for spell in owner["spellbook"]} == {spell.id for spell in gydion.spellbook}
    assert {spell["spell_rank"] for spell in owner["spellbook"]} == {
        spell.spell_rank for spell in gydion.spellbook
    }
    assert enemy["spellbook"] == {"count": len(gydion.spellbook)}
    assert spectator["spellbook"] == {"count": len(gydion.spellbook)}
    assert {spell["id"] for spell in reveal_all["spellbook"]} == {
        spell.id for spell in gydion.spellbook
    }


def test_cast_spells_are_faceup_public_and_hidden_spell_ids_do_not_leak() -> None:
    state, gydion, opponent = _state()

    views = [
        build_view(state, for_hero_id=gydion.id),
        build_view(state, for_hero_id=opponent.id),
        build_view(state),
    ]

    for view in views:
        hero = _hero(view, gydion.id)
        assert [spell["id"] for spell in hero["cast_spells"]] == ["magic_missile"]
        assert hero["cast_spells"][0]["is_facedown"] is False
        assert hero["cast_spells"][0]["spell_rank"] == 0

    public_gydion = _hero(views[-1], gydion.id)
    assert all(spell.id not in str(public_gydion["spellbook"]) for spell in gydion.spellbook)


def test_heroes_without_spells_expose_null_spellbook_and_empty_cast_spells() -> None:
    state, _, opponent = _state()

    hero = _hero(build_view(state, for_hero_id=opponent.id), opponent.id)

    assert hero["spellbook"] is None
    assert hero["cast_spells"] == []


def test_spellbook_zones_and_visibility_survive_game_state_json_round_trip() -> None:
    state, gydion, opponent = _state()

    restored = GameState.model_validate_json(state.model_dump_json())
    restored_owner = _hero(build_view(restored, for_hero_id=gydion.id), gydion.id)
    restored_public = _hero(build_view(restored, for_hero_id=opponent.id), gydion.id)

    assert {spell["id"] for spell in restored_owner["spellbook"]} == {
        spell.id for spell in gydion.spellbook
    }
    assert restored_public["spellbook"] == {"count": len(gydion.spellbook)}
    assert [spell["id"] for spell in restored_public["cast_spells"]] == ["magic_missile"]
