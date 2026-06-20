from __future__ import annotations

import pytest

import goa2.scripts.trinkets_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Token, TokenType, Turret
from goa2.domain.models.effect import EffectType
from goa2.domain.models.enums import StatType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.stats import compute_card_stats, get_computed_stat

from ..builders import EffectScenarioBuilder, hero_card, skill_card
from ..runner import run_card

TURRET_ID = BoardEntityID("trinkets_turret")


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _place_turret(state: GameState, at: Hex, owner_id: str = "hero_trinkets") -> None:
    state.register_entity(Turret(id=TURRET_ID, name="Turret", owner_id=owner_id))
    state.place_entity(TURRET_ID, at)


def _add_barrier_pool(state: GameState) -> None:
    state.token_pool[TokenType.BARRIER] = []
    for i in range(3):
        token = Token(
            id=f"barrier_{i + 1}",
            name="Barrier",
            token_type=TokenType.BARRIER,
        )
        state.register_entity(token)
        state.token_pool[TokenType.BARRIER].append(token)


def _combat_events(run) -> list:
    return [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]


@pytest.mark.effect_contract
def test_salvage_parts_is_registered() -> None:
    assert CardEffectRegistry.get("salvage_parts") is not None


@pytest.mark.effect_flow
def test_salvage_parts_places_unique_turret_as_obstacle() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_HEX)
    assert turret_hex in _option_set(run)

    run.choose(turret_hex).finish()

    turret = state.misc_entities[TURRET_ID]
    assert isinstance(turret, Turret)
    assert turret.owner_id == "hero_trinkets"
    assert state.entity_locations[TURRET_ID] == turret_hex
    assert state.board.get_tile(turret_hex).occupant_id == TURRET_ID
    assert TURRET_ID not in state.get_units_and_tokens()
    assert any(e.event_type == GameEventType.BOARD_ENTITY_PLACED for e in run.events)


@pytest.mark.effect_flow
def test_salvage_parts_remove_turret_and_move() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    move_hex = Hex(q=3, r=0, s=-3)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    state.register_entity(Turret(id=TURRET_ID, name="Turret", owner_id="hero_trinkets"))
    state.place_entity(TURRET_ID, turret_hex)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX)
    assert move_hex in _option_set(run)

    run.choose(move_hex).finish()

    assert TURRET_ID not in state.entity_locations
    assert state.board.get_tile(turret_hex).occupant_id is None
    assert state.entity_locations["hero_trinkets"] == move_hex
    assert any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)


@pytest.mark.effect_flow
def test_salvage_parts_remove_turret_and_retrieve_card() -> None:
    turret_hex = Hex(q=1, r=0, s=-1)
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    hero = state.get_hero("hero_trinkets")
    assert hero is not None
    discarded = skill_card("discarded_tool", "Discarded Tool")
    discarded.state = CardState.DISCARD
    hero.discard_pile.append(discarded)
    state.register_entity(Turret(id=TURRET_ID, name="Turret", owner_id="hero_trinkets"))
    state.place_entity(TURRET_ID, turret_hex)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(3)
    run.expect_input(InputRequestType.SELECT_CARD).choose("discarded_tool")
    run.finish()

    assert TURRET_ID not in state.entity_locations
    assert discarded in hero.hand
    assert discarded not in hero.discard_pile
    assert any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)
    assert any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
@pytest.mark.parametrize("choice", [2, 3])
def test_salvage_parts_remove_branches_abort_without_turret(choice: int) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "salvage_parts"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    hero = state.get_hero("hero_trinkets")
    assert hero is not None
    discarded = skill_card("discarded_tool", "Discarded Tool")
    discarded.state = CardState.DISCARD
    hero.discard_pile.append(discarded)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(choice)
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=0, r=0, s=0)
    assert discarded in hero.discard_pile
    assert discarded not in hero.hand
    assert not any(e.event_type == GameEventType.BOARD_ENTITY_REMOVED for e in run.events)


# =============================================================================
# Registration
# =============================================================================


@pytest.mark.effect_contract
@pytest.mark.parametrize(
    "effect_id",
    [
        "makeshift_minigun",
        "gatling_gun",
        "supercharged_cannon",
        "steam_discharge",
        "flame_belcher",
        "deployable_barrier",
        "deployable_bastion",
        "disruptor_jolt",
        "disruptor_pulse",
        "disruptor_grid",
        "self_destruct",
        "emergency_protocol",
        "early_prototype",
        "updated_design",
        "perfected_design",
        "rapid_redeployment",
        "unlimited_firepower",
    ],
)
def test_trinkets_effects_are_registered(effect_id: str) -> None:
    assert CardEffectRegistry.get(effect_id) is not None


# =============================================================================
# Cannon family
# =============================================================================


@pytest.mark.effect_flow
def test_gatling_gun_requires_range_of_both_origins() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "gatling_gun"),
        )
        .blue_minion("minion_in", at=(2, 0, -2))
        .blue_minion("minion_turret_only", at=(4, 0, -4))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=1, s=-2))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"minion_in"}
    run.choose("minion_in").finish()


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "expected_attack"),
    [
        ("makeshift_minigun", 5),
        ("gatling_gun", 5),
        ("supercharged_cannon", 7),
    ],
)
def test_cannon_gains_bonus_when_aligned_with_both_origins(
    card_id: str, expected_attack: int
) -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", card_id),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion").finish()

    combat = _combat_events(run)
    assert combat
    assert combat[-1].metadata["attack_value"] == expected_attack


@pytest.mark.effect_flow
def test_cannon_no_bonus_when_not_aligned_with_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "gatling_gun"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    # Turret at (0,1,-1): in range 2 of the target but NOT in a straight line.
    _place_turret(state, Hex(q=0, r=1, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion").finish()

    combat = _combat_events(run)
    assert combat
    assert combat[-1].metadata["attack_value"] == 3


@pytest.mark.effect_flow
def test_cannon_aborts_without_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=4)
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "gatling_gun"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.finish()

    assert not _combat_events(run)


# =============================================================================
# Turret-adjacent attacks (Steam Discharge / Flame Belcher)
# =============================================================================


@pytest.mark.effect_flow
def test_steam_discharge_targets_must_be_adjacent_to_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "steam_discharge"),
        )
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(2, 1, -3))
        .blue_minion("minion_far", at=(4, 0, -4))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"minion_a", "minion_b"}
    run.choose("minion_a")
    run.expect_input(InputRequestType.SELECT_OPTION).confirm()
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"minion_b"}
    run.choose("minion_b").finish()

    assert len(_combat_events(run)) == 2


@pytest.mark.effect_flow
def test_flame_belcher_repeats_up_to_two_times() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "flame_belcher"),
        )
        .blue_minion("minion_a", at=(1, 0, -1))
        .blue_minion("minion_b", at=(2, 1, -3))
        .blue_minion("minion_c", at=(3, 0, -3))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("minion_a")
    run.expect_input(InputRequestType.SELECT_OPTION).confirm()
    run.expect_input(InputRequestType.SELECT_UNIT).choose("minion_b")
    run.expect_input(InputRequestType.SELECT_OPTION).confirm()
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"minion_c"}
    run.choose("minion_c").finish()

    assert len(_combat_events(run)) == 3


# =============================================================================
# Barrier family
# =============================================================================


@pytest.mark.effect_flow
def test_deployable_barrier_places_tokens_and_grants_defense() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "deployable_barrier"),
        )
        .red_hero("hero_friend", at=(1, 1, -2))
        .blue_hero("hero_enemy", at=(3, 0, -3))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))
    _add_barrier_pool(state)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX)
    # First token must be adjacent to the Turret (free hexes only).
    assert _option_set(run) == {Hex(q=2, r=0, s=-2), Hex(q=0, r=1, s=-1)}
    run.choose(Hex(q=2, r=0, s=-2))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=0, r=1, s=-1))
    run.finish()

    placed = [
        t
        for t in state.token_pool[TokenType.BARRIER]
        if BoardEntityID(str(t.id)) in state.entity_locations
    ]
    assert len(placed) == 2

    auras = [e for e in state.active_effects if e.effect_type == EffectType.AREA_STAT_MODIFIER]
    assert len(auras) == 2

    # Friend is adjacent to both tokens, Trinkets to one, the enemy gets nothing.
    assert get_computed_stat(state, UnitID("hero_friend"), StatType.DEFENSE, 0) == 2
    assert get_computed_stat(state, UnitID("hero_trinkets"), StatType.DEFENSE, 0) == 1
    assert get_computed_stat(state, UnitID("hero_enemy"), StatType.DEFENSE, 0) == 0


@pytest.mark.effect_flow
def test_deployable_bastion_skipping_a_placement_ends_the_sequence() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "deployable_bastion"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))
    _add_barrier_pool(state)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.finish()

    placed = [
        t
        for t in state.token_pool[TokenType.BARRIER]
        if BoardEntityID(str(t.id)) in state.entity_locations
    ]
    assert len(placed) == 1


@pytest.mark.effect_flow
def test_deployable_barrier_skipping_first_token_places_nothing() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "deployable_barrier"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))
    _add_barrier_pool(state)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.finish()

    placed = [
        t
        for t in state.token_pool[TokenType.BARRIER]
        if BoardEntityID(str(t.id)) in state.entity_locations
    ]
    assert not placed
    assert not state.active_effects


@pytest.mark.effect_flow
def test_deployable_barrier_in_radius_is_measured_from_trinkets_not_turret() -> None:
    """ "In radius" (bare) means in radius of Trinkets, not the Turret.

    The card text says "Place ... Barrier tokens in radius, with at least one
    of them adjacent to the Turret." Only the explicit "adjacent to the Turret"
    is Turret-anchored; the bare "in radius" is measured from Trinkets (the
    acting hero). This separates the two origins by placing the Turret far from
    Trinkets and checking the second (non-first) token placement options.
    """
    # Radius-5 hex disk so distances equal cube distance (fully connected).
    disk = [
        (q, r, -q - r)
        for q in range(-5, 6)
        for r in range(-5, 6)
        if max(abs(q), abs(r), abs(q + r)) <= 5
    ]
    state = (
        EffectScenarioBuilder()
        .with_hexes(disk)
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "deployable_barrier"),  # radius 3
        )
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=4, r=0, s=-4))
    _add_barrier_pool(state)

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    # First token: must be adjacent to the Turret AND within Trinkets' radius 3.
    run.expect_input(InputRequestType.SELECT_HEX)
    first = Hex(q=3, r=0, s=-3)  # dist 1 from Turret, dist 3 from Trinkets
    assert first in _option_set(run)
    run.choose(first)

    # Second token: only "in radius" of Trinkets applies.
    run.expect_input(InputRequestType.SELECT_HEX)
    options = _option_set(run)
    # In Trinkets' radius 3 but OUTSIDE the Turret's radius 3 → must be allowed.
    hero_only = Hex(q=0, r=3, s=-3)  # dist 3 from Trinkets, dist 4 from Turret
    assert hero_only in options
    # In the Turret's radius but OUTSIDE Trinkets' radius 3 → must NOT be allowed.
    turret_only = Hex(q=5, r=0, s=-5)  # dist 1 from Turret, dist 5 from Trinkets
    assert turret_only not in options


# =============================================================================
# Disruptor family
# =============================================================================


def _disruptor_state(card_id: str, *, enemy_hand: bool) -> GameState:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", card_id),
        )
        .blue_hero(
            "hero_blue",
            at=(3, 0, -3),
            current_card=skill_card("enemy_skill", "Enemy Skill"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=2, r=0, s=-2))
    if enemy_hand:
        blue = state.get_hero("hero_blue")
        assert blue is not None
        blue.hand.append(skill_card("blue_filler", "Blue Filler"))
    return state


def _play_disruptor(state: GameState, card_id: str) -> None:
    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()
    # Normally done by ConfirmResolutionStep at end of the hero's turn.
    EffectManager.activate_effects_by_card(state, card_id)


@pytest.mark.effect_flow
def test_disruptor_pulse_forces_discard_before_enemy_primary_action() -> None:
    state = _disruptor_state("disruptor_pulse", enemy_hand=True)
    _play_disruptor(state, "disruptor_pulse")

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.PRE_ACTION_DISCARD)
    assert effect.is_active

    state.current_actor_id = "hero_blue"
    run = run_card(state, "hero_blue")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("blue_filler")
    run.finish()

    blue = state.get_hero("hero_blue")
    assert blue is not None
    assert not blue.hand
    assert any(c.id == "blue_filler" for c in blue.discard_pile)
    # A discard consumes the effect: it is removed from active_effects and the
    # Trinkets card is no longer marked active (untapped).
    assert not any(e.effect_type == EffectType.PRE_ACTION_DISCARD for e in state.active_effects)
    disruptor_card = state.get_card_by_id("disruptor_pulse")
    assert disruptor_card is not None
    assert disruptor_card.is_active is False


@pytest.mark.effect_flow
def test_disruptor_pulse_no_discard_when_enemy_has_no_cards() -> None:
    state = _disruptor_state("disruptor_pulse", enemy_hand=False)
    _play_disruptor(state, "disruptor_pulse")

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.PRE_ACTION_DISCARD)

    state.current_actor_id = "hero_blue"
    run = run_card(state, "hero_blue")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    # "If able" — no cards, no penalty, effect stays active.
    assert BoardEntityID("hero_blue") in state.entity_locations
    assert effect.is_active is True


@pytest.mark.effect_flow
def test_disruptor_grid_defeats_enemy_with_no_cards() -> None:
    state = _disruptor_state("disruptor_grid", enemy_hand=False)
    _play_disruptor(state, "disruptor_grid")

    effect = next(e for e in state.active_effects if e.effect_type == EffectType.PRE_ACTION_DISCARD)

    trinkets = state.get_hero("hero_trinkets")
    assert trinkets is not None
    gold_before = trinkets.gold

    state.current_actor_id = "hero_blue"
    run = run_card(state, "hero_blue")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    assert BoardEntityID("hero_blue") not in state.entity_locations
    # Only a discard deactivates the effect; a defeat does not.
    assert effect.is_active is True
    # The defeat is credited to the disruptor's source (Trinkets), not the
    # victim — current_actor_id is the victim when the disruptor fires.
    defeated = [e for e in run.events if e.event_type == GameEventType.UNIT_DEFEATED]
    assert defeated
    assert defeated[-1].actor_id == "hero_trinkets"
    # Trinkets actually receives the kill gold (level-1 victim -> +1).
    assert trinkets.gold == gold_before + 1
    assert any(
        e.event_type == GameEventType.GOLD_GAINED
        and e.actor_id == "hero_trinkets"
        and e.metadata.get("reason") == "kill"
        for e in run.events
    )


@pytest.mark.effect_flow
def test_disruptor_jolt_ignores_enemy_outside_turret_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "disruptor_jolt"),
        )
        .blue_hero(
            "hero_blue",
            at=(5, 0, -5),
            current_card=skill_card("enemy_skill", "Enemy Skill"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    # Jolt radius 3; enemy at distance 4 from the turret.
    _place_turret(state, Hex(q=1, r=0, s=-1))
    blue = state.get_hero("hero_blue")
    assert blue is not None
    blue.hand.append(skill_card("blue_filler", "Blue Filler"))
    _play_disruptor(state, "disruptor_jolt")

    state.current_actor_id = "hero_blue"
    run = run_card(state, "hero_blue")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    assert len(blue.hand) == 1


# =============================================================================
# Self-destruct family
# =============================================================================


@pytest.mark.effect_flow
def test_self_destruct_discards_and_removes_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "self_destruct"),
        )
        .blue_hero("hero_blue_a", at=(1, 0, -1))
        .blue_hero("hero_blue_b", at=(3, 0, -3))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=2, r=0, s=-2))
    blue_a = state.get_hero("hero_blue_a")
    assert blue_a is not None
    blue_a.hand.append(skill_card("blue_card_a", "Blue Card A"))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert _option_set(run) == {"hero_blue_a", "hero_blue_b"}
    run.choose("hero_blue_a")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_blue_b")
    run.expect_input(InputRequestType.SELECT_CARD).choose("blue_card_a")
    run.finish()

    assert not blue_a.hand
    # Tier II is "discard, if able": no cards means no penalty.
    assert BoardEntityID("hero_blue_b") in state.entity_locations
    assert TURRET_ID not in state.entity_locations


@pytest.mark.effect_flow
def test_emergency_protocol_defeats_hero_without_cards() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "emergency_protocol"),
        )
        .blue_hero("hero_blue_a", at=(1, 0, -1))
        .blue_hero("hero_blue_b", at=(3, 0, -3))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=2, r=0, s=-2))
    blue_a = state.get_hero("hero_blue_a")
    blue_b = state.get_hero("hero_blue_b")
    trinkets = state.get_hero("hero_trinkets")
    assert blue_a is not None and blue_b is not None and trinkets is not None
    blue_a.hand.append(skill_card("blue_card_a", "Blue Card A"))
    blue_b.level = 3  # worth 3 gold if defeated and credited

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_blue_a")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_blue_b")
    run.expect_input(InputRequestType.SELECT_CARD).choose("blue_card_a")
    run.finish()

    assert not blue_a.hand
    # Tier III is "discard, or be defeated".
    assert BoardEntityID("hero_blue_b") not in state.entity_locations
    assert TURRET_ID not in state.entity_locations
    # The kill is credited to Trinkets — NOT to blue_a (who just acted on the
    # discard) nor to blue_b (the victim). This pins that the victim-chooses
    # discard flow does not drift current_actor_id within the multi-victim loop.
    assert trinkets.gold == 3
    assert blue_a.gold == 0
    defeated = [e for e in run.events if e.event_type == GameEventType.UNIT_DEFEATED]
    assert defeated and defeated[-1].actor_id == "hero_trinkets"


@pytest.mark.effect_flow
def test_self_destruct_without_turret_does_nothing() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "self_destruct"),
        )
        .blue_hero("hero_blue_a", at=(1, 0, -1))
        .with_actor("hero_trinkets")
        .build()
    )
    blue_a = state.get_hero("hero_blue_a")
    assert blue_a is not None
    blue_a.hand.append(skill_card("blue_card_a", "Blue Card A"))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    assert len(blue_a.hand) == 1


# =============================================================================
# Design family
# =============================================================================


@pytest.mark.effect_flow
def test_updated_design_swaps_with_unit_in_turret_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "updated_design"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    # The Turret itself must never be selectable.
    assert str(TURRET_ID) not in _option_set(run)
    run.choose("blue_minion").finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["blue_minion"] == Hex(q=0, r=0, s=0)
    assert TURRET_ID in state.entity_locations


@pytest.mark.effect_flow
def test_updated_design_does_nothing_outside_turret_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(4, 0, -4),
            current_card=hero_card("Trinkets", "updated_design"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    # Radius 2 card; Trinkets is at distance 3 from the turret.
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=4, r=0, s=-4)
    assert state.entity_locations["blue_minion"] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_early_prototype_swaps_then_removes_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "early_prototype"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("blue_minion")
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["blue_minion"] == Hex(q=0, r=0, s=0)
    assert TURRET_ID not in state.entity_locations


@pytest.mark.effect_flow
def test_perfected_design_can_place_self_in_turret_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "perfected_design"),
        )
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=1, s=-3))
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=2, r=1, s=-3)


@pytest.mark.effect_flow
def test_perfected_design_can_swap_instead() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "perfected_design"),
        )
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_trinkets")
        .build()
    )
    _place_turret(state, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("blue_minion")
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["blue_minion"] == Hex(q=0, r=0, s=0)


# =============================================================================
# Rapid Redeployment
# =============================================================================


@pytest.mark.effect_flow
def test_rapid_redeployment_move_and_place_turret() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=5)
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "rapid_redeployment"),
        )
        .with_actor("hero_trinkets")
        .build()
    )

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.finish()

    assert state.entity_locations["hero_trinkets"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations[TURRET_ID] == Hex(q=3, r=0, s=-3)
    turret = state.misc_entities[TURRET_ID]
    assert isinstance(turret, Turret)
    assert turret.owner_id == "hero_trinkets"


@pytest.mark.effect_flow
def test_rapid_redeployment_defeat_adjacent_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=4)
        .red_hero(
            "hero_trinkets",
            at=(0, 0, 0),
            current_card=hero_card("Trinkets", "rapid_redeployment"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_trinkets")
        .build()
    )

    run = run_card(state, "hero_trinkets")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion")
    run.finish()

    assert BoardEntityID("blue_minion") not in state.entity_locations
    assert TURRET_ID not in state.entity_locations


# =============================================================================
# Ultimate — Unlimited Firepower
# =============================================================================


@pytest.mark.effect_contract
def test_unlimited_firepower_grants_range_and_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=3)
        .red_hero("hero_trinkets", at=(0, 0, 0))
        .with_actor("hero_trinkets")
        .build()
    )
    hero = state.get_hero("hero_trinkets")
    assert hero is not None

    gatling = hero_card("Trinkets", "gatling_gun")  # Range 3
    pulse = hero_card("Trinkets", "disruptor_pulse")  # Radius 4
    assert compute_card_stats(state, hero.id, gatling).range == 3
    assert compute_card_stats(state, hero.id, pulse).radius == 4

    hero.ultimate_card = hero_card("Trinkets", "unlimited_firepower")
    hero.level = 8

    assert compute_card_stats(state, hero.id, gatling).range == 4
    assert compute_card_stats(state, hero.id, pulse).radius == 5
