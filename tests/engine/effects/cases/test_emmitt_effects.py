"""
Emmitt card-effect tests (non-ultimate cards).

TDD paths: docs/superpowers/plans/2026-07-05-emmitt-tdd-paths.md.
Ultimate tests live in tests/engine/test_emmitt_ultimate.py.
"""

from __future__ import annotations

import pytest

import goa2.scripts.emmitt_effects  # noqa: F401
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.engine.rules import is_immune

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card

# =============================================================================
# P7 primitive: radius-scoped IMMUNITY_ENEMY_ACTIONS aura in is_immune()
# =============================================================================


def _aura_effect(origin_id: str, radius: int = 4) -> ActiveEffect:
    return ActiveEffect(
        id="aura_test",
        source_id=origin_id,
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=radius,
            origin_id=origin_id,
            affects=AffectsFilter.FRIENDLY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
        created_at_turn=1,
        created_at_round=1,
    )


def _aura_state():
    """Emmitt + ally (RED) vs enemy (BLUE, acting) on a line board."""
    state = (
        EffectScenarioBuilder()
        .line_board(8)
        .red_hero("hero_emmitt", at=(0, 0, 0))
        .red_hero("hero_ally", at=(1, 0, -1))
        .blue_hero("hero_enemy", at=(3, 0, -3))
        .with_actor("hero_enemy")
        .build()
    )
    state.active_effects.append(_aura_effect("hero_emmitt"))
    return state


@pytest.mark.effect_contract
class TestAuraImmunityPrimitive:
    def test_friendly_hero_in_radius_is_immune(self):
        state = _aura_state()
        ally = state.get_hero("hero_ally")
        assert is_immune(ally, state) is True

    def test_origin_hero_is_not_immune(self):
        """FRIENDLY_HEROES excludes the aura's owner (Emmitt himself)."""
        state = _aura_state()
        emmitt = state.get_hero("hero_emmitt")
        assert is_immune(emmitt, state) is False

    def test_hero_outside_radius_not_immune_until_entering(self):
        """Aura semantics: evaluated at check time from the origin's current
        position — entering the radius gains immunity, leaving loses it."""
        state = _aura_state()
        ally = state.get_hero("hero_ally")
        state.place_entity("hero_ally", Hex(q=6, r=0, s=-6))  # outside radius 4
        assert is_immune(ally, state) is False
        state.place_entity("hero_ally", Hex(q=2, r=0, s=-2))  # back inside
        assert is_immune(ally, state) is True

    def test_friendly_actor_not_blocked(self):
        """Immunity applies to ENEMY actions only."""
        state = _aura_state()
        state.current_actor_id = "hero_emmitt"
        ally = state.get_hero("hero_ally")
        assert is_immune(ally, state) is False

    def test_friendly_minion_not_covered(self):
        state = (
            EffectScenarioBuilder()
            .line_board(8)
            .red_hero("hero_emmitt", at=(0, 0, 0))
            .red_minion("minion_red", at=(1, 0, -1))
            .blue_hero("hero_enemy", at=(3, 0, -3))
            .with_actor("hero_enemy")
            .build()
        )
        state.active_effects.append(_aura_effect("hero_emmitt"))
        minion = next(m for m in state.teams[TeamColor.RED].minions if m.id == "minion_red")
        assert is_immune(minion, state) is False

    def test_inactive_aura_does_not_protect(self):
        state = _aura_state()
        state.active_effects[-1].is_active = False
        ally = state.get_hero("hero_ally")
        assert is_immune(ally, state) is False


# =============================================================================
# P4 primitive: turn-scoped discard log
# =============================================================================


@pytest.mark.effect_contract
class TestTurnDiscardLog:
    def _state_with_hand(self):
        from ..builders import skill_card

        state = (
            EffectScenarioBuilder()
            .line_board(6)
            .red_hero("hero_a", at=(0, 0, 0))
            .blue_hero("hero_b", at=(3, 0, -3))
            .with_actor("hero_a")
            .build()
        )
        hero = state.get_hero("hero_a")
        card = skill_card("logged_card")
        card.state = "HAND"
        hero.hand.append(card)
        return state, hero, card

    def test_discard_records_in_turn_log(self):
        from goa2.engine.handler import process_stack, push_steps
        from goa2.engine.steps import DiscardCardStep

        state, _hero, card = self._state_with_hand()
        push_steps(state, [DiscardCardStep(card_id=card.id, hero_id="hero_a")])
        process_stack(state)
        assert state.turn_discard_log.get("hero_a") == [card.id]

    def test_end_turn_clears_log(self):
        from goa2.engine.phases import end_turn

        state, _hero, card = self._state_with_hand()
        state.turn_discard_log = {"hero_a": [card.id]}
        state.unresolved_hero_ids = []
        end_turn(state)
        assert state.turn_discard_log == {}


# =============================================================================
# TIME CAPSULE (§8): "You, and friendly heroes in radius, may retrieve all
# cards discarded this turn."
# =============================================================================


def _capsule_state(ally_at=(2, 0, -2)):
    """Emmitt (with time_capsule, radius 4) + ally; both have one card
    discarded this turn and one discarded earlier."""
    from ..builders import skill_card

    state = (
        EffectScenarioBuilder()
        .line_board(10)
        .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "time_capsule"))
        .red_hero("hero_ally", at=ally_at)
        .blue_hero("hero_enemy", at=(5, 0, -5))
        .with_actor("hero_emmitt")
        .build()
    )
    for hid, prefix in (("hero_emmitt", "em"), ("hero_ally", "al")):
        hero = state.get_hero(hid)
        fresh = skill_card(f"{prefix}_fresh")
        old = skill_card(f"{prefix}_old")
        for c in (fresh, old):
            c.state = "DISCARD"
            hero.discard_pile.append(c)
        state.turn_discard_log.setdefault(hid, []).append(fresh.id)
    return state


@pytest.mark.effect_flow
class TestTimeCapsule:
    def test_both_heroes_retrieve_their_own_this_turn_discards(self):
        state = _capsule_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        # Emmitt decides first (choice routed to him), then the ally
        run.expect_input("SELECT_NUMBER")
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose(1)
        run.expect_input("SELECT_NUMBER")
        assert run.latest_request.player_id == "hero_ally"
        run.choose(1)
        run.finish()

        emmitt = state.get_hero("hero_emmitt")
        ally = state.get_hero("hero_ally")
        assert "em_fresh" in [c.id for c in emmitt.hand]
        assert "al_fresh" in [c.id for c in ally.hand]
        # Cards discarded on earlier turns stay put
        assert "em_old" in [c.id for c in emmitt.discard_pile]
        assert "al_old" in [c.id for c in ally.discard_pile]

    def test_decline_is_all_or_nothing(self):
        state = _capsule_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(0)  # Emmitt declines
        run.expect_input("SELECT_NUMBER").choose(1)  # ally accepts
        run.finish()
        emmitt = state.get_hero("hero_emmitt")
        assert "em_fresh" in [c.id for c in emmitt.discard_pile]
        assert "al_fresh" in [c.id for c in state.get_hero("hero_ally").hand]

    def test_ally_outside_radius_not_offered(self):
        state = _capsule_state(ally_at=(6, 0, -6))  # beyond radius 4
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER")
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose(1)
        run.finish()  # no second prompt
        assert "al_fresh" in [c.id for c in state.get_hero("hero_ally").discard_pile]

    def test_hero_without_this_turn_discards_not_prompted(self):
        state = _capsule_state()
        state.turn_discard_log.pop("hero_ally")
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(1)
        run.finish()  # ally never prompted
        assert "al_fresh" in [c.id for c in state.get_hero("hero_ally").discard_pile]

    def test_enemy_never_offered(self):
        state = _capsule_state()
        enemy = state.get_hero("hero_enemy")
        from ..builders import skill_card

        card = skill_card("en_fresh")
        card.state = "DISCARD"
        enemy.discard_pile.append(card)
        state.turn_discard_log["hero_enemy"] = [card.id]
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(1)
        run.expect_input("SELECT_NUMBER").choose(1)
        run.finish()
        assert "en_fresh" in [c.id for c in enemy.discard_pile]


# =============================================================================
# FUTURE PROOF (§9): Choose one — Time Capsule retrieval / aura immunity
# =============================================================================


@pytest.mark.effect_flow
class TestFutureProof:
    def _state(self):
        state = (
            EffectScenarioBuilder()
            .line_board(10)
            .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "future_proof"))
            .red_hero("hero_ally", at=(2, 0, -2))
            .blue_hero("hero_enemy", at=(5, 0, -5))
            .with_actor("hero_emmitt")
            .build()
        )
        return state

    def test_immunity_branch_creates_aura(self):
        state = self._state()
        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER")  # choose-one branch
        run.choose(2)  # immunity
        run.finish()

        auras = [
            e
            for e in state.active_effects
            if e.effect_type == EffectType.IMMUNITY_ENEMY_ACTIONS and e.scope.shape == Shape.RADIUS
        ]
        assert len(auras) == 1
        assert auras[0].scope.affects == AffectsFilter.FRIENDLY_HEROES
        assert auras[0].scope.range == 4
        assert auras[0].is_active

        state.current_actor_id = "hero_enemy"
        assert is_immune(state.get_hero("hero_ally"), state) is True
        assert is_immune(state.get_hero("hero_emmitt"), state) is False

    def test_immunity_expires_at_end_of_turn(self):
        from goa2.engine.phases import end_turn

        state = self._state()
        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(2)
        run.finish()
        state.unresolved_hero_ids = []
        end_turn(state)
        state.current_actor_id = "hero_enemy"
        assert is_immune(state.get_hero("hero_ally"), state) is False

    def test_retrieval_branch_behaves_like_time_capsule(self):
        from ..builders import skill_card

        state = self._state()
        emmitt = state.get_hero("hero_emmitt")
        card = skill_card("em_fresh")
        card.state = "DISCARD"
        emmitt.discard_pile.append(card)
        state.turn_discard_log["hero_emmitt"] = [card.id]

        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(1)  # retrieval branch
        run.expect_input("SELECT_NUMBER").choose(1)  # Emmitt accepts
        run.finish()
        assert "em_fresh" in [c.id for c in emmitt.hand]


# =============================================================================
# REVERSE TIME (§12): attack; next turn lower initiative acts first
# =============================================================================


def _order_state(init_a: int, init_b: int, *, items_a: int = 0):
    """Two opposing heroes with committed cards, ready for resolve_next_action."""
    from goa2.domain.models import StatType

    from ..builders import skill_card

    state = (
        EffectScenarioBuilder()
        .line_board(6)
        .red_hero("hero_a", at=(0, 0, 0), current_card=skill_card("card_a", initiative=init_a))
        .blue_hero("hero_b", at=(3, 0, -3), current_card=skill_card("card_b", initiative=init_b))
        .build()
    )
    if items_a:
        state.get_hero("hero_a").items[StatType.INITIATIVE] = items_a
    state.unresolved_hero_ids = ["hero_a", "hero_b"]
    state.current_actor_id = None
    return state


def _reversal(created_turn: int, created_round: int = 1) -> ActiveEffect:
    return ActiveEffect(
        id="rev_test",
        source_id="hero_emmitt_src",
        effect_type=EffectType.REVERSED_INITIATIVE,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.NEXT_TURN,
        is_active=True,
        created_at_turn=created_turn,
        created_at_round=created_round,
    )


@pytest.mark.effect_contract
class TestReversedInitiativePrimitive:
    def test_reversed_order_next_turn(self):
        from goa2.engine.phases import resolve_next_action

        state = _order_state(3, 9)
        state.turn = 2
        state.active_effects.append(_reversal(created_turn=1))
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_a"  # lowest first

    def test_normal_order_without_effect(self):
        from goa2.engine.phases import resolve_next_action

        state = _order_state(3, 9)
        state.turn = 2
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_b"

    def test_reversal_dormant_on_creation_turn(self):
        from goa2.engine.phases import resolve_next_action

        state = _order_state(3, 9)
        state.turn = 1
        state.active_effects.append(_reversal(created_turn=1))
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_b"

    def test_reversal_over_after_next_turn(self):
        from goa2.engine.phases import resolve_next_action

        state = _order_state(3, 9)
        state.turn = 3
        state.active_effects.append(_reversal(created_turn=1))
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_b"

    def test_reversal_fizzles_across_round_boundary(self):
        from goa2.engine.phases import resolve_next_action

        state = _order_state(3, 9)
        state.round = 2
        state.turn = 1
        state.active_effects.append(_reversal(created_turn=4, created_round=1))
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_b"

    def test_reversed_order_uses_computed_initiative(self):
        from goa2.engine.phases import resolve_next_action

        # hero_a: card 5 + item 5 = 10; hero_b: 6 → reversed picks b (6 < 10)
        state = _order_state(5, 6, items_a=5)
        state.turn = 2
        state.active_effects.append(_reversal(created_turn=1))
        resolve_next_action(state)
        assert str(state.current_actor_id) == "hero_b"

    def test_ties_still_go_to_tie_breaker(self):
        from goa2.engine.phases import resolve_next_action
        from goa2.engine.steps import ResolveTieBreakerStep

        state = _order_state(4, 4)
        state.turn = 2
        state.active_effects.append(_reversal(created_turn=1))
        resolve_next_action(state)
        assert isinstance(state.execution_stack[-1], ResolveTieBreakerStep)


@pytest.mark.effect_flow
class TestReverseTime:
    def _state(self, with_target: bool = True):
        builder = (
            EffectScenarioBuilder()
            .line_board(8)
            .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "reverse_time"))
            .blue_hero("hero_far", at=(5, 0, -5))
            .with_actor("hero_emmitt")
        )
        if with_target:
            builder = builder.blue_minion("minion_target", at=(1, 0, -1))
        return builder.build()

    def test_attack_then_creates_next_turn_reversal(self):
        state = self._state()
        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.finish()

        reversals = [
            e for e in state.active_effects if e.effect_type == EffectType.REVERSED_INITIATIVE
        ]
        assert len(reversals) == 1
        assert reversals[0].duration == DurationType.NEXT_TURN
        assert reversals[0].source_id == "hero_emmitt"

    def test_no_effect_when_attack_aborts(self):
        state = self._state(with_target=False)
        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.finish()  # no adjacent unit → mandatory targeting fails → abort
        assert not [
            e for e in state.active_effects if e.effect_type == EffectType.REVERSED_INITIATIVE
        ]

    def test_defeat_of_emmitt_removes_reversal(self):
        from goa2.engine.handler import process_stack, push_steps
        from goa2.engine.steps import DefeatUnitStep

        state = self._state()
        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.finish()
        assert any(e.effect_type == EffectType.REVERSED_INITIATIVE for e in state.active_effects)

        state.current_actor_id = "hero_far"
        push_steps(state, [DefeatUnitStep(victim_id="hero_emmitt", killer_id="hero_far")])
        process_stack(state)
        assert not [
            e for e in state.active_effects if e.effect_type == EffectType.REVERSED_INITIATIVE
        ]


# =============================================================================
# P1 primitive: HasResolvedCardFilter — "has already resolved a card this turn"
# =============================================================================


def _resolved_card(card_id: str, initiative: int = 5):
    from goa2.domain.models.enums import CardState

    from ..builders import skill_card

    card = skill_card(card_id, initiative=initiative)
    card.state = CardState.RESOLVED
    return card


def _unresolved_card(card_id: str, initiative: int = 5):
    from goa2.domain.models.enums import CardState

    from ..builders import skill_card

    card = skill_card(card_id, initiative=initiative)
    card.state = CardState.UNRESOLVED
    return card


@pytest.mark.effect_contract
class TestHasResolvedCardFilterPrimitive:
    def _state(self):
        return (
            EffectScenarioBuilder()
            .line_board(8)
            .red_hero("hero_emmitt", at=(0, 0, 0))
            .blue_hero("hero_enemy", at=(3, 0, -3))
            .with_actor("hero_emmitt")
            .build()
        )

    def _passes(self, state, candidate="hero_enemy"):
        from goa2.engine.filters import HasResolvedCardFilter

        return HasResolvedCardFilter().apply(candidate, state, {})

    def test_enemy_finalized_this_turn_passes(self):
        """Turn 1 (actor resolved_turn_count=0): enemy's slot 0 is filled →
        they resolved a card this turn."""
        state = self._state()
        enemy = state.get_hero("hero_enemy")
        enemy.played_cards = [_resolved_card("prev_resolved")]
        enemy.resolved_turn_count = 1
        assert self._passes(state) is True

    def test_enemy_with_only_unresolved_card_fails(self):
        state = self._state()
        state.get_hero("hero_enemy").current_turn_card = _unresolved_card("pending")
        assert self._passes(state) is False

    def test_resolved_on_earlier_turn_only_fails(self):
        """Turn 2 (actor resolved_turn_count=1): enemy resolved on turn 1 but
        has an unresolved card THIS turn → 'this turn' condition fails."""
        state = self._state()
        state.get_hero("hero_emmitt").resolved_turn_count = 1
        enemy = state.get_hero("hero_enemy")
        enemy.played_cards = [_resolved_card("turn1_card")]
        enemy.resolved_turn_count = 1
        enemy.current_turn_card = _unresolved_card("pending")
        assert self._passes(state) is False

    def test_resolved_but_not_yet_finalized_passes(self):
        """current_turn_card RESOLVED (mid-finalization / action-control
        window) counts as resolved this turn."""
        state = self._state()
        state.get_hero("hero_enemy").current_turn_card = _resolved_card("just_done")
        assert self._passes(state) is True

    def test_non_hero_candidate_fails(self):
        state = self._state()
        assert self._passes(state, candidate="minion_1") is False


# =============================================================================
# TIME LOOP (§4): "Swap with an enemy hero in range who has already resolved
# a card this turn." (range 4)
# =============================================================================


def _swap_block_effect(origin_id: str) -> ActiveEffect:
    """Bulwark-style area effect: enemy actors cannot SWAP covered heroes."""
    from goa2.domain.models.enums import DisplacementType

    return ActiveEffect(
        id="swap_block_test",
        source_id=origin_id,
        effect_type=EffectType.PLACEMENT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=1,
            origin_id=origin_id,
            affects=AffectsFilter.FRIENDLY_HEROES,
        ),
        duration=DurationType.THIS_ROUND,
        is_active=True,
        created_at_turn=1,
        created_at_round=1,
        displacement_blocks=[DisplacementType.SWAP],
        blocks_enemy_actors=True,
    )


def _loop_state(card_id: str = "time_loop", *, enemy_resolved: bool = True, enemy_at=(3, 0, -3)):
    state = (
        EffectScenarioBuilder()
        .line_board(8)
        .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", card_id))
        .blue_hero("hero_enemy", at=enemy_at)
        .with_actor("hero_emmitt")
        .build()
    )
    enemy = state.get_hero("hero_enemy")
    if enemy_resolved:
        enemy.played_cards = [_resolved_card("prev_resolved", initiative=9)]
        enemy.resolved_turn_count = 1
    else:
        enemy.current_turn_card = _unresolved_card("pending")
    return state


@pytest.mark.effect_flow
class TestTimeLoop:
    def test_swap_with_resolved_enemy(self):
        from goa2.domain.events import GameEventType

        state = _loop_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.finish()

        assert state.get_position("hero_emmitt") == Hex(q=3, r=0, s=-3)
        assert state.get_position("hero_enemy") == Hex(q=0, r=0, s=0)
        assert any(e.event_type == GameEventType.UNITS_SWAPPED for e in run.events)

    def test_no_resolved_enemy_aborts(self):
        state = _loop_state(enemy_resolved=False)
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.finish()  # mandatory select has no candidates → abort
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)
        assert state.get_position("hero_enemy") == Hex(q=3, r=0, s=-3)

    def test_enemy_out_of_range_aborts(self):
        state = _loop_state(enemy_at=(5, 0, -5))  # range 4
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.finish()
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)

    def test_swap_prevention_denies_and_aborts(self):
        """Displacement validation: a swap-blocking area effect on the target
        denies the swap; mandatory → abort, positions unchanged."""
        state = _loop_state()
        # Guard next to the enemy projects the swap-blocking aura over them.
        state = (
            EffectScenarioBuilder()
            .line_board(8)
            .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "time_loop"))
            .blue_hero("hero_enemy", at=(3, 0, -3))
            .blue_hero("hero_guard", at=(4, 0, -4))
            .with_actor("hero_emmitt")
            .build()
        )
        enemy = state.get_hero("hero_enemy")
        enemy.played_cards = [_resolved_card("prev_resolved")]
        enemy.resolved_turn_count = 1
        state.active_effects.append(_swap_block_effect("hero_guard"))

        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.finish()
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)
        assert state.get_position("hero_enemy") == Hex(q=3, r=0, s=-3)

    def test_immune_enemy_excluded(self):
        state = _loop_state()
        state.active_effects.append(
            ActiveEffect(
                id="imm_test",
                source_id="hero_enemy",
                effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
                scope=EffectScope(shape=Shape.POINT, origin_id="hero_enemy"),
                duration=DurationType.THIS_ROUND,
                is_active=True,
                created_at_turn=1,
                created_at_round=1,
            )
        )
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.finish()  # only candidate immune → abort
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)


# =============================================================================
# TIME WARP (§5): Choose one — (A) Time Loop position swap / (B) enemy swaps
# their unresolved card with one of their resolved cards, of THEIR choice.
# =============================================================================


def _warp_state(*, enemy_has_resolved: bool = True, enemy_at=(3, 0, -3)):
    """Enemy with an unresolved card this turn (bullet B shape); optionally
    one resolved card from an earlier turn to swap in."""
    state = (
        EffectScenarioBuilder()
        .line_board(8)
        .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "time_warp"))
        .blue_hero("hero_enemy", at=enemy_at)
        .with_actor("hero_emmitt")
        .build()
    )
    enemy = state.get_hero("hero_enemy")
    enemy.current_turn_card = _unresolved_card("enemy_pending", initiative=7)
    if enemy_has_resolved:
        enemy.played_cards = [_resolved_card("enemy_prev", initiative=2)]
        enemy.resolved_turn_count = 1
    return state


@pytest.mark.effect_flow
class TestTimeWarp:
    def test_bullet_a_swaps_positions_like_time_loop(self):
        state = _loop_state("time_warp")
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(1)
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.finish()
        assert state.get_position("hero_emmitt") == Hex(q=3, r=0, s=-3)
        assert state.get_position("hero_enemy") == Hex(q=0, r=0, s=0)

    def test_bullet_b_enemy_picks_resolved_card_and_swaps(self):
        from goa2.domain.models.enums import CardState

        state = _warp_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(2)
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.expect_input("SELECT_CARD")
        assert run.latest_request.player_id == "hero_enemy"  # THEIR choice
        run.choose("enemy_prev")
        run.finish()

        enemy = state.get_hero("hero_enemy")
        # Old resolved card is now the (unresolved) current turn card…
        assert enemy.current_turn_card is not None
        assert enemy.current_turn_card.id == "enemy_prev"
        assert enemy.current_turn_card.state == CardState.UNRESOLVED
        # …and the swapped-out card sits RESOLVED in the played slot (U3:
        # it never resolves its action).
        assert [c.id for c in enemy.played_cards if c is not None] == ["enemy_pending"]
        assert enemy.played_cards[0].state == CardState.RESOLVED

    def test_bullet_b_resolution_order_follows_swapped_in_card(self):
        """H3/H4: after the swap the enemy still acts this turn, ordered by
        the swapped-in card's initiative (7→2 drops them behind an init-5
        hero)."""
        state = (
            EffectScenarioBuilder()
            .line_board(8)
            .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "time_warp"))
            .blue_hero("hero_enemy", at=(3, 0, -3))
            .blue_hero("hero_other", at=(5, 0, -5))
            .with_actor("hero_emmitt")
            .build()
        )
        enemy = state.get_hero("hero_enemy")
        enemy.current_turn_card = _unresolved_card("enemy_pending", initiative=7)
        enemy.played_cards = [_resolved_card("enemy_prev", initiative=2)]
        enemy.resolved_turn_count = 1
        state.get_hero("hero_other").current_turn_card = _unresolved_card(
            "other_card", initiative=5
        )

        run = run_card(state, "hero_emmitt", finalize_turn=True)
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(2)
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.expect_input("SELECT_CARD").choose("enemy_prev")

        # Finalizing Emmitt's turn hands over to the next actor: without the
        # swap hero_enemy (init 7) would act before hero_other (init 5); with
        # the swapped-in init-2 card, hero_other goes first.
        run.expect_input("CHOOSE_ACTION")
        assert run.latest_request.player_id == "hero_other"
        assert str(state.current_actor_id) == "hero_other"

    def test_bullet_b_enemy_without_resolved_card_not_targetable(self):
        state = _warp_state(enemy_has_resolved=False)
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(2)
        run.finish()  # no valid target → mandatory → abort
        enemy = state.get_hero("hero_enemy")
        assert enemy.current_turn_card is not None
        assert enemy.current_turn_card.id == "enemy_pending"

    def test_bullet_b_no_enemy_in_range_aborts(self):
        state = _warp_state(enemy_at=(6, 0, -6))  # beyond range 4
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.expect_input("SELECT_NUMBER").choose(2)
        run.finish()
        enemy = state.get_hero("hero_enemy")
        assert enemy.current_turn_card is not None
        assert enemy.current_turn_card.id == "enemy_pending"


# =============================================================================
# P8 primitive: TokenType.GLITCH, supply 3, non-persistent
# =============================================================================


@pytest.mark.effect_contract
def test_glitch_token_supply_is_three():
    from goa2.domain.models import TokenType
    from goa2.domain.models.token import TOKEN_SUPPLY
    from goa2.engine.setup import GameSetup

    assert TOKEN_SUPPLY[TokenType.GLITCH] == 3

    state = (
        EffectScenarioBuilder()
        .line_board(4)
        .red_hero("hero_a", at=(0, 0, 0))
        .blue_hero("hero_b", at=(2, 0, -2))
        .build()
    )
    GameSetup._initialize_token_pool(state)
    glitch = state.token_pool[TokenType.GLITCH]
    assert len(glitch) == 3
    assert all(not t.persists_end_of_round for t in glitch)
    assert all(not t.is_passable for t in glitch)  # tokens are obstacles (U6)


# =============================================================================
# P10 primitive: PlaceTokenBatchStep — upfront supply reconciliation, batch
# spacing, all-or-nothing feasibility, optional opt-in prompt
# =============================================================================


def _add_glitch_pool(state, on_board=()) -> list[str]:
    from goa2.domain.models import TokenType
    from goa2.domain.models.token import Token

    state.token_pool[TokenType.GLITCH] = []
    ids: list[str] = []
    for i in range(3):
        token = Token(id=f"glitch_{i + 1}", name="Glitch", token_type=TokenType.GLITCH)
        state.register_entity(token)
        state.token_pool[TokenType.GLITCH].append(token)
        ids.append(f"glitch_{i + 1}")
    for i, at in enumerate(on_board):
        state.place_entity(f"glitch_{i + 1}", Hex(q=at[0], r=at[1], s=at[2]))
    return ids


def _glitch_on_board(state) -> dict[str, Hex]:
    from goa2.domain.models import TokenType

    out = {}
    for token in state.token_pool.get(TokenType.GLITCH, []):
        pos = state.get_position(str(token.id))
        if pos is not None:
            out[str(token.id)] = pos
    return out


def _batch_state(board_len: int = 12, on_board=(), actor: str = "hero_emmitt"):
    state = (
        EffectScenarioBuilder()
        .line_board(board_len)
        .red_hero("hero_emmitt", at=(0, 0, 0))
        .blue_hero("hero_enemy", at=(board_len - 1, 0, -(board_len - 1)))
        .with_actor(actor)
        .build()
    )
    _add_glitch_pool(state, on_board=on_board)
    return state


def _push_batch(state, **kwargs):
    from goa2.domain.models import TokenType
    from goa2.engine.handler import process_stack, push_steps
    from goa2.engine.steps import PlaceTokenBatchStep

    kwargs.setdefault("token_type", TokenType.GLITCH)
    kwargs.setdefault("min_spacing", 3)
    kwargs.setdefault("is_mandatory", False)
    kwargs.setdefault("placed_flag_key", "glitch_placed")
    push_steps(state, [PlaceTokenBatchStep(**kwargs)])
    return process_stack(state)


def _answer(state, value):
    from goa2.engine.handler import process_stack

    state.execution_stack[-1].pending_input = {"selection": value}
    return process_stack(state)


def _hex_dict(q: int) -> dict:
    return {"q": q, "r": 0, "s": -q}


def _option_qs(request) -> set[int]:
    """Extract q coordinates from a SELECT_HEX request's options."""
    qs = set()
    for option in request.options:
        meta = getattr(option, "metadata", None) or {}
        raw = meta.get("hex") or meta.get("raw")
        if raw is None:
            continue
        qs.add(raw["q"] if isinstance(raw, dict) else raw.q)
    return qs


@pytest.mark.effect_contract
class TestPlaceTokenBatchStep:
    def test_count_exceeding_total_supply_fails(self):
        state = _batch_state()
        result = _push_batch(state, count=4)
        assert result.input_request is None
        assert _glitch_on_board(state) == {}
        assert state.execution_context.get("glitch_placed") is None

    def test_places_all_from_free_supply(self):
        state = _batch_state()
        result = _push_batch(state, count=3)
        for q in (1, 4, 7):
            assert result.input_request is not None
            assert result.input_request.request_type.value == "SELECT_HEX"
            result = _answer(state, _hex_dict(q))
        assert result.input_request is None
        placed = _glitch_on_board(state)
        assert len(placed) == 3
        assert {h.q for h in placed.values()} == {1, 4, 7}
        assert state.execution_context.get("glitch_placed") is True

    def test_spacing_enforced_between_batch_picks(self):
        state = _batch_state()
        result = _push_batch(state, count=2)
        result = _answer(state, _hex_dict(4))  # first token at q=4
        assert result.input_request is not None
        qs = _option_qs(result.input_request)
        # distance ≥ 3 from q=4: q ∈ {1, 7, 8, 9, 10} (0 and 11 occupied)
        assert qs == {1, 7, 8, 9, 10}

    def test_removal_of_preexisting_prompted_before_placement(self):
        state = _batch_state(on_board=[(9, 0, -9)])
        result = _push_batch(state, count=3)
        # Free supply is 2 < 3 → first prompt removes a pre-existing token.
        assert result.input_request is not None
        assert result.input_request.request_type.value != "SELECT_HEX"
        option_ids = {o.id for o in result.input_request.options}
        assert option_ids == {"glitch_1"}  # only the pre-existing token
        result = _answer(state, "glitch_1")
        for q in (1, 4, 7):
            assert result.input_request is not None
            assert result.input_request.request_type.value == "SELECT_HEX"
            result = _answer(state, _hex_dict(q))
        placed = _glitch_on_board(state)
        assert len(placed) == 3
        assert {h.q for h in placed.values()} == {1, 4, 7}  # q=9 freed
        assert state.execution_context.get("glitch_placed") is True

    def test_infeasible_spacing_skips_without_prompts(self):
        state = _batch_state(board_len=4)  # q 0..3, 0 and 3 occupied
        result = _push_batch(state, count=2)  # q1/q2 are distance 1 apart
        assert result.input_request is None
        assert _glitch_on_board(state) == {}
        assert state.execution_context.get("glitch_placed") is None

    def test_opt_in_decline_places_nothing(self):
        state = _batch_state()
        result = _push_batch(state, count=2, opt_in_prompt="Place Glitch tokens?")
        assert result.input_request is not None
        assert result.input_request.request_type.value == "SELECT_NUMBER"
        result = _answer(state, 0)
        assert result.input_request is None
        assert _glitch_on_board(state) == {}
        assert state.execution_context.get("glitch_placed") is None

    def test_opt_in_accept_flows_to_placement(self):
        state = _batch_state()
        result = _push_batch(state, count=2, opt_in_prompt="Place Glitch tokens?")
        result = _answer(state, 1)
        for q in (1, 4):
            assert result.input_request is not None
            assert result.input_request.request_type.value == "SELECT_HEX"
            result = _answer(state, _hex_dict(q))
        assert len(_glitch_on_board(state)) == 2
        assert state.execution_context.get("glitch_placed") is True

    def test_opt_in_not_offered_when_infeasible(self):
        state = _batch_state(board_len=4)
        result = _push_batch(state, count=2, opt_in_prompt="Place Glitch tokens?")
        assert result.input_request is None
        assert _glitch_on_board(state) == {}

    def test_prompts_routed_to_owner_not_actor(self):
        """Defense mode: the enemy is the current actor but Emmitt owns the
        placement — every prompt goes to Emmitt."""
        state = _batch_state(on_board=[(9, 0, -9)], actor="hero_enemy")
        result = _push_batch(state, count=3, owner_id="hero_emmitt")
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_emmitt"  # removal
        result = _answer(state, "glitch_1")
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_emmitt"  # hex select


# =============================================================================
# FLASHBACK / DÉJÀ VU (§10): attack adjacent; after the attack you may place
# 3/2 Glitch tokens in radius (spacing ≥ 3); if you do, up to 1 enemy hero in
# radius swaps with a Glitch token of their choice. End of turn: remove all.
# =============================================================================


def _disc_hexes(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(max(-radius, -radius - q), min(radius, radius - q) + 1)
    ]


_TOKEN_SPOTS = [(3, 0, -3), (0, 3, -3), (-3, 0, 3)]  # pairwise distance ≥ 3


def _glitch_card_state(
    card_id: str = "flashback",
    *,
    board_radius: int = 4,
    with_minion: bool = True,
    with_far_hero: bool = False,
):
    builder = (
        EffectScenarioBuilder()
        .with_hexes(_disc_hexes(board_radius))
        .red_hero("hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", card_id))
        .blue_hero("hero_victim", at=(0, -2, 2))
        .with_actor("hero_emmitt")
    )
    if with_minion:
        builder = builder.blue_minion("minion_target", at=(1, 0, -1))
    if with_far_hero:
        builder = builder.blue_hero("hero_far", at=(4, 0, -4))
    state = builder.build()
    _add_glitch_pool(state)
    return state


@pytest.mark.effect_flow
class TestFlashback:
    def _run_through_placement(self, state, count: int = 3):
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.expect_input("SELECT_NUMBER")  # opt-in
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose(1)
        for q, r, s in _TOKEN_SPOTS[:count]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        return run

    def test_full_flow_place_three_then_enemy_swaps(self):
        state = _glitch_card_state(with_far_hero=True)
        run = self._run_through_placement(state)

        # Rider: Emmitt may pick 1 enemy hero in radius (far hero excluded, U4)
        run.expect_input("SELECT_UNIT")
        victim_options = {o.id for o in run.latest_request.options}
        assert "hero_victim" in victim_options
        assert "hero_far" not in victim_options
        run.choose("hero_victim")

        # That hero's player picks the Glitch token (U3-style routing)
        run.expect_input("SELECT_UNIT_OR_TOKEN")
        assert run.latest_request.player_id == "hero_victim"
        run.choose("glitch_1")  # placed at (3, 0, -3)
        run.finish()

        assert state.get_position("hero_victim") == Hex(q=3, r=0, s=-3)
        assert state.get_position("glitch_1") == Hex(q=0, r=-2, s=2)
        assert len(_glitch_on_board(state)) == 3

    def test_rider_is_optional(self):
        """H4: 'up to 1' — Emmitt may skip the swap after placing."""
        state = _glitch_card_state()
        run = self._run_through_placement(state)
        run.expect_input("SELECT_UNIT").skip()
        run.finish()
        assert state.get_position("hero_victim") == Hex(q=0, r=-2, s=2)
        assert len(_glitch_on_board(state)) == 3

    def test_decline_placement_no_tokens_no_rider(self):
        """U2: opting out places nothing and never offers the swap."""
        state = _glitch_card_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.expect_input("SELECT_NUMBER").choose(0)
        run.finish()
        assert _glitch_on_board(state) == {}

    def test_attack_abort_skips_everything(self):
        """U1: no adjacent unit → attack aborts → no placement offer."""
        state = _glitch_card_state(with_minion=False)  # victim is 2 away
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.finish()
        assert _glitch_on_board(state) == {}

    def test_infeasible_board_never_offers_placement(self):
        """U3/U8: board can't fit all 3 with spacing → option unavailable."""
        state = _glitch_card_state(board_radius=1)
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.finish()  # no opt-in prompt, no rider
        assert _glitch_on_board(state) == {}

    def test_end_of_turn_removes_all_glitch_tokens(self):
        """H5: THIS_TURN cleanup through the real end_turn."""
        from goa2.engine.handler import process_stack
        from goa2.engine.phases import end_turn

        state = _glitch_card_state()
        run = self._run_through_placement(state)
        run.expect_input("SELECT_UNIT").skip()
        run.finish()
        assert len(_glitch_on_board(state)) == 3

        state.unresolved_hero_ids = []
        end_turn(state)
        process_stack(state)
        assert _glitch_on_board(state) == {}


@pytest.mark.effect_flow
class TestDejaVu:
    def test_places_two_tokens_then_rider(self):
        state = _glitch_card_state("deja_vu")
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("minion_target")
        run.expect_input("SELECT_NUMBER").choose(1)
        for q, r, s in _TOKEN_SPOTS[:2]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        run.expect_input("SELECT_UNIT").skip()  # rider offered after 2 tokens
        run.finish()
        assert len(_glitch_on_board(state)) == 2


# =============================================================================
# UNSTABLE TIMELINE (§11): place 2 Glitch tokens in radius (3 as a defense);
# an enemy hero in play (Emmitt picks which) chooses one; EMMITT swaps with
# that token. End of turn: remove all Glitch tokens.
# =============================================================================


def _attack_card(card_id: str = "enemy_attack", value: int = 5):
    from goa2.domain.models import ActionType, Card, CardColor, CardTier

    return Card(
        id=card_id,
        name="Enemy Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=value,
        secondary_actions={},
        is_ranged=False,
        range_value=1,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _timeline_skill_state(*, board_radius: int = 5, with_enemy: bool = True):
    builder = (
        EffectScenarioBuilder()
        .with_hexes(_disc_hexes(board_radius))
        .red_hero(
            "hero_emmitt", at=(0, 0, 0), current_card=hero_card("Emmitt", "unstable_timeline")
        )
        .with_actor("hero_emmitt")
    )
    if with_enemy:
        # Distance 5 from Emmitt — outside the card's radius 4, proving the
        # chooser has no range limit ("an enemy hero in play").
        builder = builder.blue_hero("hero_enemy", at=(0, -5, 5))
    state = builder.build()
    _add_glitch_pool(state)
    return state


@pytest.mark.effect_flow
class TestUnstableTimelineSkill:
    def test_place_two_enemy_chooses_emmitt_swaps(self):
        state = _timeline_skill_state()
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        for q, r, s in _TOKEN_SPOTS[:2]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        # Emmitt picks the chooser — even beyond any range (distance 5)
        run.expect_input("SELECT_UNIT")
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose("hero_enemy")
        # The chosen enemy picks the token
        run.expect_input("SELECT_UNIT_OR_TOKEN")
        assert run.latest_request.player_id == "hero_enemy"
        run.choose("glitch_2")  # placed at (0, 3, -3)
        run.finish()

        assert state.get_position("hero_emmitt") == Hex(q=0, r=3, s=-3)
        assert state.get_position("glitch_2") == Hex(q=0, r=0, s=0)
        assert len(_glitch_on_board(state)) == 2

    def test_infeasible_placement_stops_text(self):
        """U1: tokens can't all be placed → whole text stops, no swap."""
        state = _timeline_skill_state(board_radius=1)
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        run.finish()  # no placement, no chooser
        assert _glitch_on_board(state) == {}
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)

    def test_no_enemy_hero_in_play_stops_before_swap(self):
        """U2: tokens are placed but stay; no chooser, no swap."""
        state = _timeline_skill_state()
        state.remove_entity("hero_enemy")  # defeated / not in play
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        for q, r, s in _TOKEN_SPOTS[:2]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        run.finish()  # no chooser prompt
        assert len(_glitch_on_board(state)) == 2  # tokens remain (U2)
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)

    def test_end_of_turn_removes_tokens(self):
        from goa2.engine.handler import process_stack
        from goa2.engine.phases import end_turn

        state = _timeline_skill_state()
        state.remove_entity("hero_enemy")
        run = run_card(state, "hero_emmitt")
        run.expect_input("CHOOSE_ACTION").choose("SKILL")
        for q, r, s in _TOKEN_SPOTS[:2]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        run.finish()

        state.unresolved_hero_ids = []
        end_turn(state)
        process_stack(state)
        assert _glitch_on_board(state) == {}


@pytest.mark.effect_flow
class TestUnstableTimelineDefense:
    def _state(self, *, board_radius: int = 4):
        from goa2.domain.models.enums import CardState

        state = (
            EffectScenarioBuilder()
            .with_hexes(_disc_hexes(board_radius))
            .blue_hero("hero_enemy", at=(1, 0, -1), current_card=_attack_card())
            .red_hero("hero_emmitt", at=(0, 0, 0))
            .with_actor("hero_enemy")
            .build()
        )
        emmitt = state.get_hero("hero_emmitt")
        defense = hero_card("Emmitt", "unstable_timeline")
        defense.state = CardState.HAND
        emmitt.hand = [defense]
        _add_glitch_pool(state)
        return state

    def test_defense_places_three_swaps_then_blocks(self):
        """H2: defense text resolves before the combat total; 3 tokens; the
        attack then resolves vs defense 6 with Emmitt at his new location."""
        state = self._state()
        run = run_card(state, "hero_enemy")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("hero_emmitt")
        run.expect_input("SELECT_CARD_OR_PASS")
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose("unstable_timeline")

        for q, r, s in _TOKEN_SPOTS[:3]:  # defense mode: 3 tokens
            run.expect_input("SELECT_HEX")
            assert run.latest_request.player_id == "hero_emmitt"
            run.choose({"q": q, "r": r, "s": s})

        run.expect_input("SELECT_UNIT")  # Emmitt picks the chooser
        assert run.latest_request.player_id == "hero_emmitt"
        run.choose("hero_enemy")
        run.expect_input("SELECT_UNIT_OR_TOKEN")  # attacker picks the token
        assert run.latest_request.player_id == "hero_enemy"
        run.choose("glitch_1")  # at (3, 0, -3)
        run.finish()

        # Swap happened before combat; attack 5 vs defense 6 → blocked.
        assert state.get_position("hero_emmitt") == Hex(q=3, r=0, s=-3)
        assert state.get_position("glitch_1") == Hex(q=0, r=0, s=0)
        assert len(_glitch_on_board(state)) == 3

    def test_defense_infeasible_still_blocks_with_value_six(self):
        """U1 (defense): text stops but the defense value 6 still counts."""
        state = self._state(board_radius=1)
        run = run_card(state, "hero_enemy")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("hero_emmitt")
        run.expect_input("SELECT_CARD_OR_PASS").choose("unstable_timeline")
        run.finish()  # no placement prompts; combat resolves

        assert _glitch_on_board(state) == {}
        # Attack 5 < defense 6 → blocked; Emmitt survives in place.
        assert state.get_position("hero_emmitt") == Hex(q=0, r=0, s=0)

    def test_defense_tokens_removed_at_end_of_enemy_turn(self):
        """H3: tokens placed during the enemy's turn are removed at the end
        of THAT turn."""
        from goa2.engine.handler import process_stack
        from goa2.engine.phases import end_turn

        state = self._state()
        run = run_card(state, "hero_enemy")
        run.expect_input("CHOOSE_ACTION").choose("ATTACK")
        run.expect_input("SELECT_UNIT").choose("hero_emmitt")
        run.expect_input("SELECT_CARD_OR_PASS").choose("unstable_timeline")
        for q, r, s in _TOKEN_SPOTS[:3]:
            run.expect_input("SELECT_HEX").choose({"q": q, "r": r, "s": s})
        run.expect_input("SELECT_UNIT").choose("hero_enemy")
        run.expect_input("SELECT_UNIT_OR_TOKEN").choose("glitch_1")
        run.finish()
        assert len(_glitch_on_board(state)) == 3

        state.unresolved_hero_ids = []
        end_turn(state)
        process_stack(state)
        assert _glitch_on_board(state) == {}
