"""Takahide's spatial denial family (TDD §14-§15).

"Target a unit adjacent to you. After the attack: This turn: Empty spaces
adjacent to you (Blade Helix: in radius) count as obstacles for enemy units."

The EMPTY_HEX_OBSTACLE effect is consulted by is_obstacle_for_actor, so it bites
on enemy movement, pushes, placement and movement pathing alike, and it tracks
Takahide's CURRENT position (interp 12). Note the engine's range/radius checks
are cube distance via the topology service, so a denied ring lengthens enemy
PATHS, not their attack range.
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
    Minion,
    MinionType,
    StatType,
    TeamColor,
)
from goa2.domain.models.effect import DurationType, EffectType
from goa2.engine import rules
from goa2.engine.effect_manager import EffectManager

from ..builders import EffectScenarioBuilder, movement_card
from ..runner import EffectRun, run_card
from ..takahide_common import equip_takahide

TAKAHIDE = "hero_takahide"
ENEMY = "hero_enemy_1"
ALLY = "hero_ally_1"
ENEMY_MINION = "minion_e1"


def shield(card_id: str = "enemy_shield") -> Card:
    card = Card(
        id=card_id,
        name="Enemy Shield",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=2,
        primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 9},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )
    card.state = CardState.HAND
    return card


def board(radius: int = 4) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def denial_state(card_id: str, *, enemy_at=(1, 0, -1), enemy_move: int = 3):
    """Takahide with an adjacent enemy hero who acts next with a movement card.

    The enemy holds a big defense card, so the attack is blocked and everybody
    stays on the board (which also covers "the rider fires when defended").
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes(board())
        .red_hero(TAKAHIDE, at=(0, 0, 0))
        .red_hero(ALLY, at=(0, -2, 2))
        .blue_hero(ENEMY, at=enemy_at, current_card=movement_card(value=enemy_move))
        .blue_minion(ENEMY_MINION, at=(3, 0, -3))
        .with_actor(TAKAHIDE)
        .with_unresolved_heroes([ENEMY])
        .build()
    )
    equip_takahide(state, card_id)
    enemy = state.get_hero(ENEMY)
    assert enemy is not None
    card = shield()
    enemy.deck.append(card)
    enemy.hand.append(card)
    return state


def attack_and_defend(run: EffectRun) -> EffectRun:
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("enemy_shield")
    return run


def denial_effect(state):
    return next(
        (e for e in state.active_effects if e.effect_type == EffectType.EMPTY_HEX_OBSTACLE),
        None,
    )


def obstacle_for(state, coords, actor_id: str) -> bool:
    return state.validator.is_obstacle_for_actor(
        state, Hex(q=coords[0], r=coords[1], s=coords[2]), actor_id
    )


# ---------------------------------------------------------------------------
# §14 Spinning Blade (adjacent = radius 1)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_spinning_blade_h1_h7_denies_empty_hexes_around_takahide_after_the_turn():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)  # the enemy's turn begins

    effect = denial_effect(state)
    assert effect is not None  # H7: created even though the attack was defended
    assert effect.is_active and effect.duration == DurationType.THIS_TURN
    assert effect.scope.range == 1

    assert obstacle_for(state, (0, 1, -1), ENEMY)
    assert obstacle_for(state, (1, -1, 0), ENEMY)
    assert not obstacle_for(state, (2, 0, -2), ENEMY)  # distance 2: free


@pytest.mark.effect_flow
def test_spinning_blade_h1b_enemy_movement_cannot_enter_the_denied_ring():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX)

    offered = {Hex(**opt.metadata["hex"]) for opt in run.latest_request.options}
    assert Hex(q=0, r=1, s=-1) not in offered  # adjacent to Takahide, empty
    assert Hex(q=1, r=-1, s=0) not in offered
    assert Hex(q=2, r=0, s=-2) in offered  # outside the ring


@pytest.mark.effect_flow
def test_spinning_blade_h2_denied_ring_lengthens_enemy_paths():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    enemy_hex = state.get_position(ENEMY)
    reachable_enemy = rules.find_reachable_hexes(
        board=state.board, start=enemy_hex, max_steps=2, state=state, actor_id=ENEMY
    )
    reachable_ally = rules.find_reachable_hexes(
        board=state.board,
        start=enemy_hex,
        max_steps=2,
        state=state,
        actor_id=ALLY,  # a friendly unit ignores the denial
    )
    behind = Hex(q=-1, r=2, s=-1)  # only reachable by crossing the ring at (0,1,-1)
    assert behind not in reachable_enemy
    assert behind in reachable_ally


@pytest.mark.effect_flow
def test_spinning_blade_h3_h4_minions_are_blocked_and_friendlies_are_not():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    assert obstacle_for(state, (0, 1, -1), ENEMY_MINION)  # H3
    assert not obstacle_for(state, (0, 1, -1), ALLY)  # H4
    assert not obstacle_for(state, (0, 1, -1), TAKAHIDE)


@pytest.mark.effect_flow
def test_spinning_blade_h5_the_ring_follows_takahide():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    state.place_entity(TAKAHIDE, Hex(q=-2, r=0, s=2))

    assert not obstacle_for(state, (0, 1, -1), ENEMY)  # old ring released
    assert obstacle_for(state, (-1, 0, 1), ENEMY)  # new ring denied


@pytest.mark.effect_flow
def test_spinning_blade_h6_occupied_hexes_are_unaffected_until_vacated():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    enemy_hex = state.get_position(ENEMY)  # adjacent to Takahide, occupied
    assert obstacle_for(state, (enemy_hex.q, enemy_hex.r, enemy_hex.s), ALLY)  # occupancy

    state.place_entity(ENEMY, Hex(q=3, r=-1, s=-2))  # the hex is now empty
    assert not obstacle_for(state, (enemy_hex.q, enemy_hex.r, enemy_hex.s), ALLY)
    assert obstacle_for(state, (enemy_hex.q, enemy_hex.r, enemy_hex.s), ENEMY_MINION)


@pytest.mark.effect_flow
def test_spinning_blade_u1_effect_expires_at_end_of_turn():
    state = denial_state("spinning_blade")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    EffectManager.expire_effects(state, DurationType.THIS_TURN)

    assert denial_effect(state) is None
    assert not obstacle_for(state, (0, 1, -1), ENEMY)


@pytest.mark.effect_flow
def test_spinning_blade_u2_no_adjacent_target_creates_no_effect():
    state = denial_state("spinning_blade", enemy_at=(4, 0, -4))

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.CHOOSE_ACTION)  # aborted → next hero acts

    assert denial_effect(state) is None


# ---------------------------------------------------------------------------
# §15 Blade Helix (radius stat, item-boostable)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_blade_helix_h1_denies_radius_one_by_default():
    state = denial_state("blade_helix")

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    effect = denial_effect(state)
    assert effect is not None and effect.scope.range == 1
    assert obstacle_for(state, (0, 1, -1), ENEMY)
    assert not obstacle_for(state, (0, 2, -2), ENEMY)


@pytest.mark.effect_flow
def test_blade_helix_h2_radius_item_extends_the_denied_area():
    state = denial_state("blade_helix")
    taka = state.get_hero(TAKAHIDE)
    taka.items[StatType.RADIUS] = 1

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    attack_and_defend(run)
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    effect = denial_effect(state)
    assert effect is not None and effect.scope.range == 2
    assert obstacle_for(state, (0, 2, -2), ENEMY)  # distance 2 now denied
    assert not obstacle_for(state, (0, 3, -3), ENEMY)


@pytest.mark.effect_flow
def test_spinning_blade_u3_enemy_pushes_into_the_denied_ring_are_blocked():
    """Displacement counts: an enemy-driven push cannot deliver a unit into a
    denied hex, though a friendly-driven push into the same hex still lands."""
    from goa2.domain.state import GameState
    from goa2.engine.steps import PushUnitStep

    def push_victim_toward_takahide(actor_id: str) -> GameState:
        state = denial_state("spinning_blade")
        state.teams[TeamColor.RED].minions.append(
            Minion(id="minion_r1", name="minion_r1", team=TeamColor.RED, type=MinionType.MELEE)
        )
        state.place_entity("minion_r1", Hex(q=0, r=2, s=-2))

        run = run_card(state, TAKAHIDE, finalize_turn=True)
        attack_and_defend(run)
        run.expect_input(InputRequestType.CHOOSE_ACTION)

        state.current_actor_id = actor_id
        step = PushUnitStep(target_id="minion_r1", source_hex=Hex(q=0, r=3, s=-3), distance=1)
        step.resolve(state, state.execution_context)
        return state

    blocked = push_victim_toward_takahide(ENEMY)
    assert blocked.get_position("minion_r1") == Hex(q=0, r=2, s=-2)  # push stopped

    allowed = push_victim_toward_takahide(TAKAHIDE)
    assert allowed.get_position("minion_r1") == Hex(q=0, r=1, s=-1)  # friendly push lands
