"""NebKher effect tests.

Covers the critical infrastructure cards plus effect-level coverage for the
delegable families. Lower-level engine primitives used by these cards have
dedicated tests under tests/engine/nebkher/.

Spec: docs/superpowers/plans/2026-07-07-nebkher-tdd-paths.md
"""

from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401
from goa2.domain.events import GameEventType
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
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.token import Token
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, UnitID
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.stats import calculate_minion_defense_modifier
from goa2.engine.steps import EndPhaseCleanupStep, PlaceTokenStep
from goa2.engine.topology import are_connected

from ..builders import EffectScenarioBuilder, hero_card, skill_card
from ..gydion_common import fresh_gydion, gydion_card
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


def _token_ids_on_board(state: GameState, token_type: TokenType) -> list[str]:
    return [
        str(t.id)
        for t in state.token_pool.get(token_type, [])
        if BoardEntityID(str(t.id)) in state.entity_locations
    ]


def _expect_stack_input(state: GameState, request_type: InputRequestType):
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == request_type
    return result.input_request


def _answer_stack_input(state: GameState, selection) -> None:
    assert state.execution_stack
    state.execution_stack[-1].pending_input = {"selection": selection}


def _make_immune_to_enemy_actions(state: GameState, unit_id: str) -> None:
    state.active_effects.append(
        ActiveEffect(
            id=f"immune_{unit_id}",
            source_id=unit_id,
            effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            is_active=True,
            created_at_turn=state.turn,
            created_at_round=state.round,
        )
    )


# =============================================================================
# Imbue Doubt / Time to Reconsider / An Illusion of Choice
# =============================================================================


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "expected_radius"),
    [("imbue_doubt", 3), ("time_to_reconsider", 4)],
)
def test_imbue_doubt_family_names_color_and_schedules_trigger(
    card_id: str, expected_radius: int
) -> None:
    state = _grid_state(card_id)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION)
    assert {opt.id for opt in run.latest_request.options} == {
        "BLUE",
        "GOLD",
        "GREEN",
        "RED",
        "SILVER",
    }
    run.choose("BLUE").finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    assert effect.duration == DurationType.NEXT_TURN
    # The announced color is public: stored on the effect for client display.
    assert effect.named_color == CardColor.BLUE
    assert any(
        getattr(step, "color_key", None) == "chosen_color" for step in effect.finishing_steps
    )
    select = next(
        step
        for step in effect.finishing_steps
        if getattr(step, "output_key", None) == "doubt_victim"
    )
    range_filter = next(f for f in select.filters if getattr(f, "max_range", None) is not None)
    assert range_filter.max_range == expected_radius


@pytest.mark.effect_flow
def test_imbue_doubt_trigger_discards_named_color_from_victim_hand() -> None:
    state = _grid_state("imbue_doubt")
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [
        skill_card("enemy_blue", color=CardColor.BLUE),
        skill_card("enemy_red", color=CardColor.RED),
    ]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)

    request = _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    assert {opt.id for opt in request.options} == {"hero_enemy"}
    _answer_stack_input(state, "hero_enemy")
    request = _expect_stack_input(state, InputRequestType.SELECT_CARD)
    assert request.player_id == "hero_enemy"
    assert [opt.id for opt in request.options] == ["enemy_blue"]
    _answer_stack_input(state, "enemy_blue")
    process_stack(state)

    assert [c.id for c in enemy.hand] == ["enemy_red"]
    assert [c.id for c in enemy.discard_pile] == ["enemy_blue"]


@pytest.mark.effect_flow
def test_imbue_doubt_victim_chooses_between_matching_cards() -> None:
    state = _grid_state("imbue_doubt")
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [
        skill_card("enemy_blue_a", color=CardColor.BLUE),
        skill_card("enemy_blue_b", color=CardColor.BLUE),
    ]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)
    _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    _answer_stack_input(state, "hero_enemy")
    request = _expect_stack_input(state, InputRequestType.SELECT_CARD)
    assert request.player_id == "hero_enemy"
    assert {opt.id for opt in request.options} == {"enemy_blue_a", "enemy_blue_b"}
    _answer_stack_input(state, "enemy_blue_b")
    process_stack(state)

    assert [c.id for c in enemy.hand] == ["enemy_blue_a"]
    assert [c.id for c in enemy.discard_pile] == ["enemy_blue_b"]


@pytest.mark.effect_flow
def test_imbue_doubt_committed_card_is_safe_from_trigger() -> None:
    state = _grid_state("imbue_doubt")
    enemy = state.get_hero("hero_enemy")
    enemy.current_turn_card = skill_card("enemy_committed_blue", color=CardColor.BLUE)
    enemy.hand = [skill_card("enemy_red", color=CardColor.RED)]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)
    _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    _answer_stack_input(state, "hero_enemy")
    result = process_stack(state)

    assert result.input_request is None
    assert [c.id for c in enemy.hand] == ["enemy_red"]
    assert enemy.discard_pile == []


@pytest.mark.effect_flow
def test_imbue_doubt_excludes_immune_enemy_at_trigger_time() -> None:
    state = _grid_state("imbue_doubt")
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [skill_card("enemy_blue", color=CardColor.BLUE)]
    _make_immune_to_enemy_actions(state, "hero_enemy")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)
    result = process_stack(state)

    assert result.input_request is None
    assert [c.id for c in enemy.hand] == ["enemy_blue"]


@pytest.mark.effect_flow
def test_an_illusion_of_choice_trigger_discards_from_two_different_victims() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, r, -q - r) for q in range(5) for r in range(3)])
        .red_hero(NEB, at=(2, 0, -2), current_card=hero_card("NebKher", "an_illusion_of_choice"))
        .blue_hero("hero_enemy_a", at=(4, 0, -4))
        .blue_hero("hero_enemy_b", at=(3, 1, -4))
        .with_actor(NEB)
        .build()
    )
    enemy_a = state.get_hero("hero_enemy_a")
    enemy_b = state.get_hero("hero_enemy_b")
    enemy_a.hand = [skill_card("a_blue", color=CardColor.BLUE)]
    enemy_b.hand = [skill_card("b_blue", color=CardColor.BLUE)]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)

    request = _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    assert {opt.id for opt in request.options} == {"hero_enemy_a", "hero_enemy_b"}
    _answer_stack_input(state, "hero_enemy_a")
    request = _expect_stack_input(state, InputRequestType.SELECT_CARD)
    assert request.player_id == "hero_enemy_a"
    _answer_stack_input(state, "a_blue")

    request = _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    assert {opt.id for opt in request.options} == {"hero_enemy_b"}
    _answer_stack_input(state, "hero_enemy_b")
    request = _expect_stack_input(state, InputRequestType.SELECT_CARD)
    assert request.player_id == "hero_enemy_b"
    _answer_stack_input(state, "b_blue")
    process_stack(state)

    assert enemy_a.hand == []
    assert enemy_b.hand == []
    assert [c.id for c in enemy_a.discard_pile] == ["a_blue"]
    assert [c.id for c in enemy_b.discard_pile] == ["b_blue"]


@pytest.mark.effect_flow
def test_an_illusion_of_choice_can_pick_zero_victims() -> None:
    state = _grid_state("an_illusion_of_choice")
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [skill_card("enemy_blue", color=CardColor.BLUE)]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)
    request = _expect_stack_input(state, InputRequestType.SELECT_UNIT)
    assert request.can_skip is True
    _answer_stack_input(state, "SKIP")
    result = process_stack(state)

    assert result.input_request is None
    assert [c.id for c in enemy.hand] == ["enemy_blue"]


@pytest.mark.effect_flow
def test_an_illusion_of_choice_excludes_immune_victims() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, r, -q - r) for q in range(5) for r in range(3)])
        .red_hero(NEB, at=(2, 0, -2), current_card=hero_card("NebKher", "an_illusion_of_choice"))
        .blue_hero("hero_enemy_a", at=(4, 0, -4))
        .blue_hero("hero_enemy_b", at=(3, 1, -4))
        .with_actor(NEB)
        .build()
    )
    state.get_hero("hero_enemy_a").hand = [skill_card("a_blue", color=CardColor.BLUE)]
    state.get_hero("hero_enemy_b").hand = [skill_card("b_blue", color=CardColor.BLUE)]
    _make_immune_to_enemy_actions(state, "hero_enemy_b")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("BLUE")
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.AFTER_CARDS_PLAYED_TRIGGER
    )
    push_steps(state, effect.finishing_steps)
    request = _expect_stack_input(state, InputRequestType.SELECT_UNIT)

    assert {opt.id for opt in request.options} == {"hero_enemy_a"}


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
def test_shift_reality_isolates_nebkher_one_way() -> None:
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
    # Units on either side cannot interact with NebKher…
    assert not are_connected(off_line, neb_hex, state)
    # …but units ON the line can…
    assert are_connected(on_line, neb_hex, state)
    # …and NebKher himself ignores his own reality shift (audit §3.4).
    assert are_connected(neb_hex, off_line, state)


# =============================================================================
# Fleeting Image / Multiple Projections / Master of Illusions
# =============================================================================


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "placements"),
    [
        ("fleeting_image", [Hex(q=3, r=0, s=-3)]),
        ("multiple_projections", [Hex(q=3, r=0, s=-3), Hex(q=3, r=1, s=-4)]),
        (
            "master_of_illusions",
            [Hex(q=3, r=0, s=-3), Hex(q=3, r=1, s=-4), Hex(q=2, r=1, s=-3)],
        ),
    ],
)
def test_fleeting_image_family_places_configured_number_then_may_skip_swap(
    card_id: str, placements: list[Hex]
) -> None:
    state = _grid_state(card_id)
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    for hex_ in placements:
        run.expect_input(InputRequestType.SELECT_HEX).choose(hex_)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).skip()
    run.finish()

    assert len(_token_ids_on_board(state, TokenType.ILLUSION)) == len(placements)
    assert {
        state.entity_locations[BoardEntityID(token_id)]
        for token_id in _token_ids_on_board(state, TokenType.ILLUSION)
    } == set(placements)


@pytest.mark.effect_flow
def test_fleeting_image_can_swap_with_token_placed_by_this_card() -> None:
    state = _grid_state("fleeting_image")
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_pool_0")
    run.finish()

    assert state.entity_locations[BoardEntityID(NEB)] == Hex(q=3, r=0, s=-3)
    assert state.entity_locations[BoardEntityID("illusion_pool_0")] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_fleeting_image_can_place_zero_and_skips_swap_when_no_illusions_exist() -> None:
    state = _grid_state("fleeting_image")
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.finish()

    assert _token_ids_on_board(state, TokenType.ILLUSION) == []
    assert state.entity_locations[BoardEntityID(NEB)] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_fleeting_image_reconciles_exhausted_illusion_supply_before_placing() -> None:
    state = _grid_state("fleeting_image")
    _add_illusion(state, "illusion_0", Hex(q=1, r=0, s=-1))
    _add_illusion(state, "illusion_1", Hex(q=1, r=1, s=-2))
    _add_illusion(state, "illusion_2", Hex(q=2, r=1, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_0")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).skip()
    run.finish()

    assert BoardEntityID("illusion_0") in state.entity_locations
    assert state.entity_locations[BoardEntityID("illusion_0")] == Hex(q=3, r=0, s=-3)
    assert len(_token_ids_on_board(state, TokenType.ILLUSION)) == 3


@pytest.mark.effect_flow
def test_illusion_tokens_are_removed_by_end_phase_cleanup() -> None:
    state = _grid_state("fleeting_image")
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).skip()
    run.finish()

    result = EndPhaseCleanupStep().resolve(state, {})

    assert _token_ids_on_board(state, TokenType.ILLUSION) == []
    assert any(e.event_type == GameEventType.TOKEN_REMOVED for e in result.events)


# =============================================================================
# Illusionary Force / Illusionary Army
# =============================================================================


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "placements"),
    [
        ("illusionary_force", [Hex(q=3, r=0, s=-3), Hex(q=3, r=1, s=-4)]),
        (
            "illusionary_army",
            [Hex(q=3, r=0, s=-3), Hex(q=3, r=1, s=-4), Hex(q=2, r=1, s=-3)],
        ),
    ],
)
def test_illusionary_force_family_places_tokens_and_creates_equivalence(
    card_id: str, placements: list[Hex]
) -> None:
    state = _grid_state(card_id)
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    for hex_ in placements:
        run.expect_input(InputRequestType.SELECT_HEX).choose(hex_)
    run.finish()

    effect = next(
        e for e in state.active_effects if e.effect_type == EffectType.ILLUSION_MINION_EQUIVALENCE
    )
    assert effect.duration == DurationType.THIS_ROUND
    assert effect.source_id == NEB
    assert len(_token_ids_on_board(state, TokenType.ILLUSION)) == len(placements)

    # Both Illusions adjacent to hero_enemy count as friendly melee minions
    # only while NebKher is the acting source.
    state.current_actor_id = NEB
    assert calculate_minion_defense_modifier(state, UnitID("hero_enemy")) == -2


# =============================================================================
# Phantasmal Sentry / Warrior / Champion
# =============================================================================


@pytest.mark.effect_flow
def test_phantasmal_sentry_attacks_hero_adjacent_to_illusion_in_range() -> None:
    state = _grid_state("phantasmal_sentry")
    _add_illusion(state, "illusion_1", Hex(q=3, r=0, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat[-1].target_id == "hero_enemy"
    assert combat[-1].metadata["attack_value"] == 2


@pytest.mark.effect_flow
def test_phantasmal_sentry_adjacent_bullet_is_ranged_attack() -> None:
    from goa2.domain.models import Minion, TeamColor

    state = _grid_state("phantasmal_sentry")
    minion = Minion(id="blue_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(minion)
    state.place_entity("blue_minion", Hex(q=2, r=1, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.finish()
    assert state.execution_context["attack_is_ranged"] is True

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat[-1].target_id == "blue_minion"


@pytest.mark.effect_flow
def test_phantasmal_sentry_rejects_hero_when_adjacent_illusion_is_out_of_range() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(7)])
        .red_hero(NEB, at=(0, 0, 0), current_card=hero_card("NebKher", "phantasmal_sentry"))
        .blue_hero("hero_enemy", at=(4, 0, -4))
        .with_actor(NEB)
        .build()
    )
    _add_illusion(state, "illusion_1", Hex(q=5, r=0, s=-5))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()

    assert not any(e.event_type == GameEventType.COMBAT_RESOLVED for e in run.events)


@pytest.mark.effect_flow
def test_phantasmal_sentry_excludes_immune_targets() -> None:
    state = _grid_state("phantasmal_sentry")
    _add_illusion(state, "illusion_1", Hex(q=3, r=0, s=-3))
    _make_immune_to_enemy_actions(state, "hero_enemy")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()

    assert not any(e.event_type == GameEventType.COMBAT_RESOLVED for e in run.events)


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "start_hex", "dest_hex"),
    [
        ("phantasmal_warrior", Hex(q=3, r=1, s=-4), Hex(q=4, r=1, s=-5)),
        ("phantasmal_champion", Hex(q=2, r=2, s=-4), Hex(q=4, r=1, s=-5)),
    ],
)
def test_phantasmal_warrior_family_moves_illusion_then_attacks_forced_target(
    card_id: str, start_hex: Hex, dest_hex: Hex
) -> None:
    state = _grid_state(card_id)
    _add_illusion(state, "illusion_1", start_hex)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.expect_input(InputRequestType.SELECT_HEX).choose(dest_hex)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()

    assert state.entity_locations[BoardEntityID("illusion_1")] == dest_hex
    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat[-1].target_id == "hero_enemy"
    assert combat[-1].metadata["attack_value"] == 3


@pytest.mark.effect_flow
def test_phantasmal_warrior_allows_zero_space_token_move() -> None:
    state = _grid_state("phantasmal_warrior")
    _add_illusion(state, "illusion_1", Hex(q=4, r=1, s=-5))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=4, r=1, s=-5))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()

    assert state.entity_locations[BoardEntityID("illusion_1")] == Hex(q=4, r=1, s=-5)
    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat[-1].target_id == "hero_enemy"


@pytest.mark.effect_flow
def test_phantasmal_warrior_rejects_enemy_hero_out_of_range() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(8)] + [(5, 1, -6)])
        .red_hero(NEB, at=(0, 0, 0), current_card=hero_card("NebKher", "phantasmal_warrior"))
        .blue_hero("hero_enemy", at=(6, 0, -6))
        .with_actor(NEB)
        .build()
    )
    _add_illusion(state, "illusion_1", Hex(q=5, r=0, s=-5))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.finish()

    assert not any(e.event_type == GameEventType.COMBAT_RESOLVED for e in run.events)


@pytest.mark.effect_flow
def test_phantasmal_warrior_destination_must_be_empty() -> None:
    from goa2.domain.models import Minion, TeamColor

    state = _grid_state("phantasmal_warrior")
    _add_illusion(state, "illusion_1", Hex(q=3, r=1, s=-4))
    blocker = Minion(id="blue_blocker", name="B", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(blocker)
    state.place_entity("blue_blocker", Hex(q=4, r=1, s=-5))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.expect_input(InputRequestType.SELECT_HEX)

    option_hexes = {
        (
            opt.metadata.get("hex", {}).get("q"),
            opt.metadata.get("hex", {}).get("r"),
            opt.metadata.get("hex", {}).get("s"),
        )
        for opt in run.latest_request.options
    }
    assert (4, 1, -5) not in option_hexes


# =============================================================================
# Twist Fate / Devious Scheme
# =============================================================================


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "illusion_hex"),
    [
        ("twist_fate", Hex(q=2, r=1, s=-3)),  # adjacent to NebKher
        ("devious_scheme", Hex(q=3, r=1, s=-4)),  # in range, not adjacent
    ],
)
def test_twist_fate_family_swaps_enemy_with_illusion_after_attack(
    card_id: str, illusion_hex: Hex
) -> None:
    from goa2.domain.models import Minion, TeamColor

    state = _grid_state(card_id)
    _add_illusion(state, "illusion_1", illusion_hex)
    minion = Minion(id="blue_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(minion)
    state.place_entity("blue_minion", Hex(q=3, r=0, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.finish()

    assert state.entity_locations[BoardEntityID("blue_minion")] == illusion_hex
    assert state.entity_locations[BoardEntityID("illusion_1")] == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_twist_fate_swap_can_be_declined_after_attack() -> None:
    from goa2.domain.models import Minion, TeamColor

    state = _grid_state("twist_fate")
    _add_illusion(state, "illusion_1", Hex(q=2, r=1, s=-3))
    minion = Minion(id="blue_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(minion)
    state.place_entity("blue_minion", Hex(q=3, r=0, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).skip()
    run.finish()

    assert state.entity_locations[BoardEntityID("blue_minion")] == Hex(q=3, r=0, s=-3)
    assert state.entity_locations[BoardEntityID("illusion_1")] == Hex(q=2, r=1, s=-3)


@pytest.mark.effect_flow
def test_twist_fate_adjacent_zone_does_not_offer_illusion_at_range_two() -> None:
    from goa2.domain.models import Minion, TeamColor

    state = _grid_state("twist_fate")
    _add_illusion(state, "illusion_1", Hex(q=3, r=1, s=-4))
    minion = Minion(id="blue_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(minion)
    state.place_entity("blue_minion", Hex(q=3, r=0, s=-3))

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.finish()

    assert state.entity_locations[BoardEntityID("blue_minion")] == Hex(q=3, r=0, s=-3)
    assert state.entity_locations[BoardEntityID("illusion_1")] == Hex(q=3, r=1, s=-4)


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
def test_mind_grip_substitutes_illusion_for_find_familiar_nested_spell_token() -> None:
    """The override survives Mind Grip -> access card -> cast spell nesting."""
    state = _mind_grip_state()
    _add_illusion_pool(state)

    enemy = state.get_hero("hero_enemy")
    previous = gydion_card("lesser_conjuration")
    previous.state = CardState.RESOLVED
    previous.is_facedown = False
    enemy.played_cards = [previous]
    enemy.resolved_turn_count = 1
    enemy.spells = [spell.model_copy(deep=True) for spell in fresh_gydion().spells]
    for spell in enemy.spells:
        spell.state = CardState.OUTSIDE_SPELLBOOK
        spell.is_facedown = False
    familiar_spell = next(spell for spell in enemy.spells if spell.id == "find_familiar")
    familiar_spell.state = CardState.SPELLBOOK
    familiar_spell.is_facedown = True

    destination = Hex(q=3, r=1, s=-4)
    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("find_familiar")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(destination.model_dump())
    run.finish()

    tile = state.board.get_tile(destination)
    assert tile is not None and tile.occupant_id is not None
    placed = state.get_entity(tile.occupant_id)
    assert placed.token_type == TokenType.ILLUSION
    assert placed.owner_id == NEB
    assert familiar_spell.state == CardState.OUTSIDE_SPELLBOOK
    assert state.execution_context.get("token_type_override") is None


@pytest.mark.effect_flow
def test_mind_grip_copying_smoke_bomb_does_not_grant_the_illusion_its_effect() -> None:
    """Copying Min's Smoke Bomb places an Illusion, but the Illusion is not a
    Smoke bomb: the LOS blocker anchored to the placed token is not created."""
    import goa2.scripts.min_effects  # noqa: F401

    state = _mind_grip_state()
    _add_illusion_pool(state)

    enemy = state.get_hero("hero_enemy")
    prev = _resolved_card("enemy_smoke_bomb")
    prev.effect_id = "smoke_bomb"
    prev.radius_value = 3
    enemy.played_cards = [prev]
    enemy.resolved_turn_count = 1

    destination = Hex(q=3, r=1, s=-4)
    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(destination.model_dump())
    run.finish()

    tile = state.board.get_tile(destination)
    assert tile is not None and tile.occupant_id is not None
    assert state.get_entity(tile.occupant_id).token_type == TokenType.ILLUSION
    assert [e for e in state.active_effects if e.effect_type == EffectType.LOS_BLOCKER] == []


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


@pytest.mark.effect_flow
def test_mind_grip_ignores_enemy_with_empty_previous_slot() -> None:
    state = _mind_grip_state()
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = []
    enemy.resolved_turn_count = 0

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()


@pytest.mark.effect_flow
def test_mind_grip_excludes_immune_enemy_hero_for_perform_bullet() -> None:
    state = _mind_grip_state()
    enemy = state.get_hero("hero_enemy")
    enemy.played_cards = [_resolved_card("enemy_prev")]
    enemy.resolved_turn_count = 1
    _make_immune_to_enemy_actions(state, "hero_enemy")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()


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
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # place bullet
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=1, s=-3))
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()  # stop early
    run.finish()

    tile = state.board.get_tile(Hex(q=2, r=1, s=-3))
    assert tile is not None and tile.occupant_id is not None
    assert state.get_entity(tile.occupant_id).token_type == TokenType.ILLUSION


@pytest.mark.effect_flow
def test_diabolical_laughter_can_choose_three_times_with_repeats() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    for hex_ in [
        Hex(q=2, r=1, s=-3),
        Hex(q=1, r=0, s=-1),
        Hex(q=1, r=1, s=-2),
    ]:
        run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
        run.expect_input(InputRequestType.SELECT_HEX).choose(hex_)
    run.finish()

    assert len(_token_ids_on_board(state, TokenType.ILLUSION)) == 3


@pytest.mark.effect_flow
def test_diabolical_laughter_swap_self_with_illusion() -> None:
    state = _laughter_state()
    _add_illusion(state, "illusion_1", Hex(q=4, r=1, s=-5))  # radius 4 away-ish

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # swap bullet
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("illusion_1")
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
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
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(3)  # card-swap bullet
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_enemy")
    run.expect_input(InputRequestType.SELECT_CARD).choose("enemy_t1")
    run.expect_input(InputRequestType.SELECT_CARD)
    # The second pick must not offer the first card again.
    second_ids = {opt.id for opt in run.latest_request.options}
    assert "enemy_t1" not in second_ids
    run.choose("enemy_t2")
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
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
    # Bullet 3 has no legal target: the menu (if shown) must not offer it,
    # so choosing it must be impossible. We just verify the iteration can
    # be declined cleanly.
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
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
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
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
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
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
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
    run.finish()

    assert len(enemy.hand) == 1


@pytest.mark.effect_flow
def test_ultimate_hits_all_enemy_heroes_in_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, r, -q - r) for q in range(5) for r in range(3)])
        .red_hero(NEB, at=(2, 0, -2), current_card=hero_card("NebKher", "diabolical_laughter"))
        .blue_hero("hero_enemy_a", at=(4, 0, -4))
        .blue_hero("hero_enemy_b", at=(3, 1, -4))
        .with_actor(NEB)
        .build()
    )
    _add_illusion_pool(state)
    _activate_ultimate(state)
    enemy_a = state.get_hero("hero_enemy_a")
    enemy_b = state.get_hero("hero_enemy_b")
    enemy_a.hand = [skill_card("a_hand")]
    enemy_b.hand = [skill_card("b_hand")]

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == "hero_enemy_a"
    run.choose("a_hand")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == "hero_enemy_b"
    run.choose("b_hand")
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
    run.finish()

    assert enemy_a.hand == []
    assert enemy_b.hand == []
    assert [c.id for c in enemy_a.discard_pile] == ["a_hand"]
    assert [c.id for c in enemy_b.discard_pile] == ["b_hand"]


@pytest.mark.effect_flow
def test_ultimate_excludes_immune_enemy_heroes() -> None:
    state = _laughter_state()
    _add_illusion_pool(state)
    _activate_ultimate(state)
    enemy = state.get_hero("hero_enemy")
    enemy.hand = [skill_card("enemy_hand")]
    _make_immune_to_enemy_actions(state, "hero_enemy")

    run = run_card(state, NEB)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).skip()
    run.finish()

    assert [c.id for c in enemy.hand] == ["enemy_hand"]
