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
