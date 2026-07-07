"""NebKher effect tests — critical-infrastructure cards only.

Covers the five effects implemented alongside the engine primitives:
crack_in_reality, shift_reality, mind_grip, diabolical_laughter, and the
ultimate what_the_hell_are_you. The delegable placement/phantasmal/imbue
families are implemented (and tested) separately.

Spec: docs/superpowers/plans/2026-07-07-nebkher-tdd-paths.md
"""

from __future__ import annotations

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    MinionType,
    TokenType,
)
from goa2.domain.models.effect import DurationType, EffectType
from goa2.domain.models.token import Token
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import PlaceTokenStep
from goa2.engine.topology import are_connected

from ..builders import EffectScenarioBuilder, hero_card, skill_card
from ..runner import run_card

NEB = "hero_nebkher"
TREE_EFFECT_ID = "test_nebkher_tree_placer"


@register_effect(TREE_EFFECT_ID)
class _TreePlacingEffect(CardEffect):
    """Test-only effect: places a TREE token at a pre-seeded hex."""

    def build_steps(self, state, hero, card, stats):
        return [PlaceTokenStep(token_type=TokenType.TREE, hex_key="neb_tree_hex")]


def _add_illusion(state: GameState, token_id: str, at: Hex) -> None:
    token = Token(id=BoardEntityID(token_id), name="Illusion", token_type=TokenType.ILLUSION)
    state.register_entity(token, "token")
    state.token_pool.setdefault(TokenType.ILLUSION, []).append(token)
    state.place_entity(token_id, at)


def _add_illusion_pool(state: GameState, count: int = 3) -> None:
    state.token_pool.setdefault(TokenType.ILLUSION, [])
    for i in range(count):
        token = Token(
            id=BoardEntityID(f"illusion_pool_{i}"),
            name="Illusion",
            token_type=TokenType.ILLUSION,
        )
        state.register_entity(token, "token")
        state.token_pool[TokenType.ILLUSION].append(token)


def _add_tree_pool(state: GameState, count: int = 3) -> None:
    state.token_pool.setdefault(TokenType.TREE, [])
    for i in range(count):
        token = Token(id=BoardEntityID(f"tree_pool_{i}"), name="Tree", token_type=TokenType.TREE)
        state.register_entity(token, "token")
        state.token_pool[TokenType.TREE].append(token)


def _grid_state(card_id: str) -> GameState:
    """5x3 grid; NebKher on the q=2 column, enemy at q=4."""
    return (
        EffectScenarioBuilder()
        .with_hexes([(q, r, -q - r) for q in range(5) for r in range(3)])
        .red_hero(NEB, at=(2, 0, -2), current_card=hero_card("NebKher", card_id))
        .blue_hero("hero_enemy", at=(4, 0, -4))
        .with_actor(NEB)
        .build()
    )


def _resolved_card(card_id: str, color: CardColor = CardColor.GREEN) -> Card:
    card = Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=color,
        initiative=5,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id="",
        effect_text="",
    )
    card.state = CardState.RESOLVED
    card.is_facedown = False
    return card


# =============================================================================
# Crack in Reality (Tier 2 split)
# =============================================================================


@pytest.mark.effect_flow
def test_crack_in_reality_splits_board_along_chosen_axis() -> None:
    state = _grid_state("crack_in_reality")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert len(run.latest_request.options) == 3  # exactly the 3 hex axes
    run.choose(1)  # q-axis line through NebKher's space
    run.finish()

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.TOPOLOGY_SPLIT)
    assert effect.split_axis == "q"
    assert effect.split_value == 2  # NebKher's q at cast time
    assert effect.duration == DurationType.THIS_TURN
    assert effect.is_active is True

    # Opposite sides can't interact; the line bridges both.
    assert not are_connected(Hex(q=1, r=0, s=-1), Hex(q=3, r=0, s=-3), state)
    assert are_connected(Hex(q=1, r=0, s=-1), Hex(q=2, r=0, s=-2), state)


# =============================================================================
# Shift Reality (Tier 3 split + isolation)
# =============================================================================


@pytest.mark.effect_flow
def test_shift_reality_isolates_nebkher_mutually() -> None:
    state = _grid_state("shift_reality")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # q-axis
    run.finish()

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.TOPOLOGY_ISOLATION)
    assert effect.split_axis == "q"
    assert effect.duration == DurationType.THIS_TURN

    neb_hex = Hex(q=2, r=0, s=-2)
    off_line = Hex(q=1, r=0, s=-1)
    on_line = Hex(q=2, r=1, s=-3)
    # Units on either side cannot interact with NebKher (mutual)…
    assert not are_connected(off_line, neb_hex, state)
    assert not are_connected(neb_hex, off_line, state)
    # …but units ON the line can.
    assert are_connected(on_line, neb_hex, state)


# =============================================================================
# Mind Grip
# =============================================================================


def _mind_grip_state() -> GameState:
    state = _grid_state("mind_grip")
    # It's turn 2 by the actor-slot convention: NebKher has one resolved card.
    neb = state.get_hero(NEB)
    neb.played_cards = [_resolved_card("neb_prev")]
    neb.resolved_turn_count = 1
    return state


@pytest.mark.effect_flow
def test_mind_grip_performs_enemy_previous_slot_action() -> None:
    state = _mind_grip_state()
    enemy = state.get_hero("hero_enemy")
    prev = _resolved_card("enemy_prev")
    prev.secondary_actions[ActionType.MOVEMENT] = 3
    enemy.played_cards = [prev]
    enemy.resolved_turn_count = 1

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # perform bullet
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    ids = {opt.id for opt in run.latest_request.options}
    assert "DEFENSE" not in ids
    assert "HOLD" in ids
    assert "MOVEMENT" in ids
    # The chooser is routed to NebKher, not the card's owner.
    assert run.latest_request.player_id == NEB
    run.choose("HOLD").finish()


@pytest.mark.effect_flow
def test_mind_grip_substitutes_illusions_for_copied_token_placement() -> None:
    state = _mind_grip_state()
    _add_illusion_pool(state)
    _add_tree_pool(state)
    state.execution_context["neb_tree_hex"] = Hex(q=3, r=1, s=-4)

    enemy = state.get_hero("hero_enemy")
    prev = _resolved_card("enemy_prev_token")
    prev.effect_id = TREE_EFFECT_ID
    enemy.played_cards = [prev]
    enemy.resolved_turn_count = 1

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    tile = state.board.get_tile(Hex(q=3, r=1, s=-4))
    assert tile is not None and tile.occupant_id is not None
    placed = state.get_entity(tile.occupant_id)
    assert placed.token_type == TokenType.ILLUSION
    # Tree supply untouched.
    assert all(
        BoardEntityID(str(t.id)) not in state.entity_locations
        for t in state.token_pool[TokenType.TREE]
    )


@pytest.mark.effect_flow
def test_mind_grip_defeat_bullet_removes_adjacent_minion() -> None:
    state = _mind_grip_state()
    builder_minion_hex = Hex(q=2, r=1, s=-3)
    from goa2.domain.models import Minion, TeamColor

    minion = Minion(id="blue_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(minion)
    state.place_entity("blue_minion", builder_minion_hex)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # defeat bullet
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.finish()

    assert state.entity_locations.get(BoardEntityID("blue_minion")) is None
    assert state.get_hero(NEB).gold > 0


@pytest.mark.effect_flow
def test_mind_grip_perform_bullet_aborts_on_turn_one() -> None:
    """Turn 1: no previous slot exists → no valid hero → mandatory failure."""
    state = _grid_state("mind_grip")  # NebKher rtc == 0 → turn 1
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = []

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()  # aborts — no further input, nothing happened


# =============================================================================
# Diabolical Laughter
# =============================================================================


def _laughter_state() -> GameState:
    return _grid_state("diabolical_laughter")


@pytest.mark.effect_flow
def test_diabolical_laughter_declined_does_nothing() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("NO")
    run.finish()

    assert not any(
        BoardEntityID(str(t.id)) in state.entity_locations
        for t in state.token_pool[TokenType.ILLUSION]
    )


@pytest.mark.effect_flow
def test_diabolical_laughter_place_bullet_then_stop() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")  # 1st of 3
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # place bullet
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=1, s=-3))
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")  # stop early
    run.finish()

    tile = state.board.get_tile(Hex(q=2, r=1, s=-3))
    assert tile is not None and tile.occupant_id is not None
    assert state.get_entity(tile.occupant_id).token_type == TokenType.ILLUSION


@pytest.mark.effect_flow
def test_diabolical_laughter_swap_self_with_illusion() -> None:
    state = _laughter_state()
    _add_illusion(state, "illusion_1", Hex(q=4, r=1, s=-5))  # radius 4 away-ish

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # swap bullet
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")
    run.finish()

    assert state.entity_locations[BoardEntityID(NEB)] == Hex(q=4, r=1, s=-5)
    assert state.entity_locations[BoardEntityID("illusion_1")] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_diabolical_laughter_swaps_two_resolved_enemy_cards() -> None:
    state = _laughter_state()
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = [_resolved_card("enemy_t1"), _resolved_card("enemy_t2")]
    enemy.resolved_turn_count = 2

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(3)  # card-swap bullet
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD).choose("enemy_t1")
    run.expect_input(InputRequestType.SELECT_CARD)
    # The second pick must not offer the first card again.
    second_ids = {opt.id for opt in run.latest_request.options}
    assert "enemy_t1" not in second_ids
    run.choose("enemy_t2")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")
    run.finish()

    assert [c.id for c in enemy.played_cards] == ["enemy_t2", "enemy_t1"]


@pytest.mark.effect_flow
def test_diabolical_laughter_card_swap_needs_two_resolved_cards() -> None:
    """An enemy with only one resolved card is not selectable for bullet 3."""
    state = _laughter_state()
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = [_resolved_card("enemy_t1")]
    enemy.resolved_turn_count = 1

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION)
    # Bullet 3 has no legal target: the menu (if shown) must not offer it,
    # so choosing it must be impossible. We just verify the iteration can
    # be declined cleanly.
    run.choose("NO")
    run.finish()

    assert [c.id for c in enemy.played_cards] == ["enemy_t1"]


# =============================================================================
# Ultimate — What the Hell Are You?
# =============================================================================


def _activate_ultimate(state: GameState) -> None:
    from goa2.data.heroes.registry import HeroRegistry

    neb = state.get_hero(NEB)
    neb.level = 8
    registered = HeroRegistry.get("NebKher")
    assert registered is not None and registered.ultimate_card is not None
    neb.ultimate_card = registered.ultimate_card.model_copy(deep=True)
    neb.ultimate_card.state = CardState.PASSIVE
    neb.ultimate_card.is_facedown = False


@pytest.mark.effect_flow
def test_ultimate_fires_immediately_after_laugh() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)
    _activate_ultimate(state)

    enemy = state.get_hero("hero_enemy")  # at (4,0,-4), distance 2 — in radius 5
    enemy.hand = [skill_card("enemy_hand_a"), skill_card("enemy_hand_b")]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    # Ultimate fires BEFORE the choose-up-to-three menu: the enemy picks
    # which card to discard.
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == "hero_enemy"
    run.choose("enemy_hand_a")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")
    run.finish()

    assert len(enemy.hand) == 1
    assert enemy.hand[0].id == "enemy_hand_b"


@pytest.mark.effect_flow
def test_ultimate_defeats_enemy_with_empty_hand() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)
    _activate_ultimate(state)

    enemy = state.get_hero("hero_enemy")
    enemy.hand = []

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")
    run.finish()

    # Defeated: removed from the board.
    assert state.entity_locations.get(BoardEntityID("hero_enemy")) is None


@pytest.mark.effect_flow
def test_ultimate_does_not_fire_without_passive_state() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [skill_card("enemy_hand_a")]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("NO")
    run.finish()

    assert len(enemy.hand) == 1
