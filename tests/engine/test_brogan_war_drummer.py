"""Tests for War Drummer / Master Skald effects, GainCoinsStep, and CheckHeroDefeatedThisRoundStep."""

import pytest
import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID
from goa2.domain.events import GameEventType
from goa2.engine.steps import (
    CheckHeroDefeatedThisRoundStep,
    DefeatUnitStep,
    GainCoinsStep,
    ResolveCardStep,
    RoundResetStep,
)
from goa2.engine.handler import process_resolution_stack, push_steps


def _make_card(card_id, name, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=5,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        range_value=2,
        primary_action_value=None,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


@pytest.fixture
def coin_state():
    board = Board()
    hexes = set()
    for q in range(5):
        hexes.add(Hex(q=q, r=0, s=-q))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    ally = Hero(id="ally", name="Ally", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

    red_team = Team(color=TeamColor.RED, heroes=[brogan, ally])
    blue_team = Team(color=TeamColor.BLUE, heroes=[enemy])

    state = GameState(board=board, teams={TeamColor.RED: red_team, TeamColor.BLUE: blue_team})
    state.entity_locations["brogan"] = Hex(q=0, r=0, s=0)
    state.entity_locations["ally"] = Hex(q=1, r=0, s=-1)
    state.entity_locations["enemy"] = Hex(q=3, r=0, s=-3)
    state.current_actor_id = HeroID("brogan")

    return state


# =====================================================================
# GainCoinsStep tests
# =====================================================================


class TestGainCoinsStep:
    def test_grants_gold_and_emits_event(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        assert ally.gold == 0

        state.execution_context["target"] = "ally"
        push_steps(state, [GainCoinsStep(hero_key="target", amount=3)])
        result = process_resolution_stack(state)

        assert ally.gold == 3
        assert result is None

    def test_missing_hero_key_is_noop(self, coin_state):
        state = coin_state
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5)])
        process_resolution_stack(state)

    def test_invalid_hero_id_is_noop(self, coin_state):
        state = coin_state
        state.execution_context["target"] = "nonexistent_hero"
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5)])
        process_resolution_stack(state)

    def test_amount_key_overrides_static(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        state.execution_context["dynamic_coins"] = 7
        push_steps(state, [GainCoinsStep(hero_key="target", amount=1, amount_key="dynamic_coins")])
        process_resolution_stack(state)
        assert ally.gold == 7

    def test_amount_key_falls_back_to_static(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        push_steps(state, [GainCoinsStep(hero_key="target", amount=2, amount_key="missing_key")])
        process_resolution_stack(state)
        assert ally.gold == 2

    def test_active_if_key_skips_when_none(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        state.execution_context["flag"] = None
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5, active_if_key="flag")])
        process_resolution_stack(state)
        assert ally.gold == 0

    def test_active_if_key_runs_when_set(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        state.execution_context["flag"] = True
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5, active_if_key="flag")])
        process_resolution_stack(state)
        assert ally.gold == 5

    def test_skip_if_key_skips_when_set(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        state.execution_context["flag"] = True
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5, skip_if_key="flag")])
        process_resolution_stack(state)
        assert ally.gold == 0

    def test_skip_if_key_runs_when_none(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        state.execution_context["target"] = "ally"
        state.execution_context["flag"] = None
        push_steps(state, [GainCoinsStep(hero_key="target", amount=5, skip_if_key="flag")])
        process_resolution_stack(state)
        assert ally.gold == 5


# =====================================================================
# CheckHeroDefeatedThisRoundStep tests
# =====================================================================


class TestCheckHeroDefeatedThisRoundStep:
    def test_no_defeats_sets_none(self, coin_state):
        state = coin_state
        push_steps(state, [CheckHeroDefeatedThisRoundStep(output_key="hero_died")])
        process_resolution_stack(state)
        assert state.execution_context["hero_died"] is None

    def test_with_defeats_sets_true(self, coin_state):
        state = coin_state
        state.heroes_defeated_this_round.append(HeroID("enemy"))
        push_steps(state, [CheckHeroDefeatedThisRoundStep(output_key="hero_died")])
        process_resolution_stack(state)
        assert state.execution_context["hero_died"] is True


# =====================================================================
# heroes_defeated_this_round state tracking
# =====================================================================


class TestHeroDefeatedTracking:
    def test_defeat_unit_step_records_hero(self, coin_state):
        state = coin_state
        assert state.heroes_defeated_this_round == []

        push_steps(state, [DefeatUnitStep(victim_id="enemy", killer_id="brogan")])
        process_resolution_stack(state)

        assert HeroID("enemy") in state.heroes_defeated_this_round

    def test_defeat_does_not_duplicate(self, coin_state):
        state = coin_state
        state.heroes_defeated_this_round.append(HeroID("enemy"))

        push_steps(state, [DefeatUnitStep(victim_id="enemy", killer_id="brogan")])
        process_resolution_stack(state)

        assert state.heroes_defeated_this_round.count(HeroID("enemy")) == 1

    def test_round_reset_clears_list(self, coin_state):
        state = coin_state
        state.heroes_defeated_this_round.append(HeroID("enemy"))

        push_steps(state, [RoundResetStep()])
        process_resolution_stack(state)

        assert state.heroes_defeated_this_round == []


# =====================================================================
# War Drummer integration tests
# =====================================================================


class TestWarDrummerIntegration:
    def _choose_action_and_select(self, state, ally_id="ally"):
        """Drive through CHOOSE_ACTION → SELECT_UNIT prompts."""
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "CHOOSE_ACTION"
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": ally_id}
        return process_resolution_stack(state)

    def test_no_hero_died_grants_1_coin(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))
        assert ally.gold == 0

        card = _make_card("war_drummer", "War Drummer", "war_drummer")
        brogan = state.get_hero(HeroID("brogan"))
        brogan.current_turn_card = card

        push_steps(state, [ResolveCardStep(hero_id="brogan")])
        req = self._choose_action_and_select(state)

        assert req is None
        assert ally.gold == 1

    def test_hero_died_grants_3_coins(self, coin_state):
        state = coin_state
        state.heroes_defeated_this_round.append(HeroID("enemy"))

        ally = state.get_hero(HeroID("ally"))
        assert ally.gold == 0

        card = _make_card("war_drummer", "War Drummer", "war_drummer")
        brogan = state.get_hero(HeroID("brogan"))
        brogan.current_turn_card = card

        push_steps(state, [ResolveCardStep(hero_id="brogan")])
        req = self._choose_action_and_select(state)

        assert req is None
        assert ally.gold == 3


# =====================================================================
# Master Skald integration tests
# =====================================================================


class TestMasterSkaldIntegration:
    def _choose_action_and_select(self, state, ally_id="ally"):
        """Drive through CHOOSE_ACTION → SELECT_UNIT prompts."""
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "CHOOSE_ACTION"
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": ally_id}
        return process_resolution_stack(state)

    def test_no_hero_died_grants_2_coins(self, coin_state):
        state = coin_state
        ally = state.get_hero(HeroID("ally"))

        card = _make_card(
            "master_skald", "Master Skald", "master_skald",
            tier=CardTier.III,
        )
        brogan = state.get_hero(HeroID("brogan"))
        brogan.current_turn_card = card

        push_steps(state, [ResolveCardStep(hero_id="brogan")])
        req = self._choose_action_and_select(state)

        assert req is None
        assert ally.gold == 2

    def test_hero_died_grants_4_coins(self, coin_state):
        state = coin_state
        state.heroes_defeated_this_round.append(HeroID("enemy"))

        ally = state.get_hero(HeroID("ally"))

        card = _make_card(
            "master_skald", "Master Skald", "master_skald",
            tier=CardTier.III,
        )
        brogan = state.get_hero(HeroID("brogan"))
        brogan.current_turn_card = card

        push_steps(state, [ResolveCardStep(hero_id="brogan")])
        req = self._choose_action_and_select(state)

        assert req is None
        assert ally.gold == 4
