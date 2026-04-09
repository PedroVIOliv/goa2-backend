"""
Tests for Xargatha's Devoted Followers and Fresh Converts card effects,
plus the generic CountStep, CheckContextConditionStep, and RetrieveCardStep.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
    CardState,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    CheckContextConditionStep,
    CountStep,
    RetrieveCardStep,
    SelectStep,
)
from goa2.engine.filters import RangeFilter, TeamFilter, UnitTypeFilter
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.domain.models.enums import TargetType, CardContainerType, StepType

# Ensure step_types patching is applied
import goa2.engine.step_types  # noqa: F401

# Register xargatha effects
import goa2.scripts.xargatha_effects  # noqa: F401


def _make_discardable_card(card_id="card_a", name="Card A"):
    c = Card(
        id=card_id,
        name=name,
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )
    c.state = CardState.DISCARD
    return c


@pytest.fixture
def retrieve_state():
    """
    Board:
    - Xargatha (hero_xargatha, RED) at (0,0,0)
    - Enemy melee minion (melee_1, BLUE) at (1,0,-1) — adjacent
    - Enemy hero (hero_enemy, BLUE) at (0,1,-1) — adjacent
    - Friendly minion (ally_melee, RED) at (0,-1,1) — adjacent
    - Active zone with all hexes
    """
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
        Hex(q=0, r=-1, s=1),
        Hex(q=-1, r=0, s=1),
        Hex(q=1, r=-1, s=0),
        Hex(q=2, r=-1, s=-1),
    }
    board = Board()
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Create discarded cards
    discard_a = _make_discardable_card("card_a", "Card A")
    discard_b = _make_discardable_card("card_b", "Card B")

    hero = Hero(
        id="hero_xargatha",
        name="Xargatha",
        team=TeamColor.RED,
        deck=[],
        level=1,
    )
    hero.discard_pile = [discard_a, discard_b]

    enemy_hero = Hero(
        id="hero_enemy",
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )

    melee = Minion(
        id="melee_1", name="Melee", type=MinionType.MELEE, team=TeamColor.BLUE
    )
    ally_melee = Minion(
        id="ally_melee", name="AllyMelee", type=MinionType.MELEE, team=TeamColor.RED
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[hero], minions=[ally_melee]
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy_hero], minions=[melee]
            ),
        },
    )
    state.place_entity("hero_xargatha", Hex(q=0, r=0, s=0))
    state.place_entity("melee_1", Hex(q=1, r=0, s=-1))
    state.place_entity("hero_enemy", Hex(q=0, r=1, s=-1))
    state.place_entity("ally_melee", Hex(q=0, r=-1, s=1))
    state.active_zone_id = "z1"
    state.current_actor_id = "hero_xargatha"

    return state


# ---------------------------------------------------------------------------
# CountStep tests
# ---------------------------------------------------------------------------


class TestCountStep:
    def test_counts_matching_units(self, retrieve_state):
        """CountStep counts enemy units adjacent to actor."""
        push_steps(
            retrieve_state,
            [
                CountStep(
                    target_type=TargetType.UNIT,
                    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
                    output_key="enemy_count",
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        # melee_1 + hero_enemy = 2 adjacent enemies
        assert retrieve_state.execution_context["enemy_count"] == 2

    def test_counts_with_unit_type_filter(self, retrieve_state):
        """CountStep with UnitTypeFilter(MINION) counts only minions."""
        push_steps(
            retrieve_state,
            [
                CountStep(
                    target_type=TargetType.UNIT,
                    filters=[
                        RangeFilter(max_range=1),
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="MINION"),
                    ],
                    output_key="minion_count",
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        # Only melee_1 is an enemy minion
        assert retrieve_state.execution_context["minion_count"] == 1

    def test_counts_zero_when_no_match(self, retrieve_state):
        """CountStep returns 0 when no candidates match."""
        # Remove all enemies
        retrieve_state.remove_entity("melee_1")
        retrieve_state.remove_entity("hero_enemy")

        push_steps(
            retrieve_state,
            [
                CountStep(
                    target_type=TargetType.UNIT,
                    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
                    output_key="enemy_count",
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert retrieve_state.execution_context["enemy_count"] == 0

    def test_skipped_when_active_if_key_missing(self, retrieve_state):
        """CountStep is skipped entirely when active_if_key is missing from context."""
        push_steps(
            retrieve_state,
            [
                CountStep(
                    target_type=TargetType.UNIT,
                    filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
                    output_key="enemy_count",
                    active_if_key="nonexistent_key",
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert "enemy_count" not in retrieve_state.execution_context


# ---------------------------------------------------------------------------
# CheckContextConditionStep tests
# ---------------------------------------------------------------------------


class TestCheckContextConditionStep:
    def test_gte_true(self, retrieve_state):
        retrieve_state.execution_context["val"] = 3
        push_steps(
            retrieve_state,
            [
                CheckContextConditionStep(
                    input_key="val", operator=">=", threshold=1, output_key="result"
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert retrieve_state.execution_context["result"] is True

    def test_gte_false(self, retrieve_state):
        retrieve_state.execution_context["val"] = 0
        push_steps(
            retrieve_state,
            [
                CheckContextConditionStep(
                    input_key="val", operator=">=", threshold=1, output_key="result"
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        # Stores None (not False) so active_if_key checks work
        assert retrieve_state.execution_context["result"] is None

    def test_eq_operator(self, retrieve_state):
        retrieve_state.execution_context["val"] = 5
        push_steps(
            retrieve_state,
            [
                CheckContextConditionStep(
                    input_key="val", operator="==", threshold=5, output_key="result"
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert retrieve_state.execution_context["result"] is True

    def test_lt_operator(self, retrieve_state):
        retrieve_state.execution_context["val"] = 0
        push_steps(
            retrieve_state,
            [
                CheckContextConditionStep(
                    input_key="val", operator="<", threshold=1, output_key="result"
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert retrieve_state.execution_context["result"] is True

    def test_missing_key_defaults_to_zero(self, retrieve_state):
        push_steps(
            retrieve_state,
            [
                CheckContextConditionStep(
                    input_key="nonexistent",
                    operator=">=",
                    threshold=1,
                    output_key="result",
                )
            ],
        )
        process_resolution_stack(retrieve_state)
        assert retrieve_state.execution_context["result"] is None


# ---------------------------------------------------------------------------
# RetrieveCardStep tests
# ---------------------------------------------------------------------------


class TestRetrieveCardStep:
    def test_retrieves_card_from_discard(self, retrieve_state):
        hero = retrieve_state.get_hero("hero_xargatha")
        assert len(hero.discard_pile) == 2
        assert len(hero.hand) == 0

        retrieve_state.execution_context["card_sel"] = "card_a"
        push_steps(
            retrieve_state,
            [RetrieveCardStep(card_key="card_sel")],
        )
        result = process_resolution_stack(retrieve_state)

        assert len(hero.discard_pile) == 1
        assert any(c.id == "card_a" for c in hero.hand)
        # Card state should be HAND
        card = next(c for c in hero.hand if c.id == "card_a")
        assert card.state == CardState.HAND

    def test_skips_when_no_card_key(self, retrieve_state):
        """RetrieveCardStep does nothing if card_key not in context."""
        hero = retrieve_state.get_hero("hero_xargatha")
        push_steps(
            retrieve_state,
            [RetrieveCardStep(card_key="missing_key")],
        )
        process_resolution_stack(retrieve_state)
        assert len(hero.discard_pile) == 2

    def test_skips_when_active_if_key_missing(self, retrieve_state):
        hero = retrieve_state.get_hero("hero_xargatha")
        retrieve_state.execution_context["card_sel"] = "card_a"
        push_steps(
            retrieve_state,
            [RetrieveCardStep(card_key="card_sel", active_if_key="nope")],
        )
        process_resolution_stack(retrieve_state)
        assert len(hero.discard_pile) == 2


# ---------------------------------------------------------------------------
# Devoted Followers integration tests
# ---------------------------------------------------------------------------


class TestDevotedFollowers:
    def _run_devoted_followers(self, state):
        """Push devoted_followers steps and process."""
        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get("devoted_followers")
        hero = state.get_hero("hero_xargatha")
        steps = effect.build_steps(state, hero, None, _make_fake_stats())
        push_steps(state, steps)
        return process_resolution_stack(state)

    def test_adjacent_enemy_hero_retrieves_card(self, retrieve_state):
        """Adjacent enemy hero → can retrieve a discarded card."""
        # Remove minion, keep hero_enemy adjacent
        retrieve_state.remove_entity("melee_1")

        req = self._run_devoted_followers(retrieve_state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        assert "card_a" in req["valid_options"]
        assert "card_b" in req["valid_options"]

        # Select card_a
        retrieve_state.execution_stack[-1].pending_input = {
            "selection": "card_a"
        }
        process_resolution_stack(retrieve_state)

        hero = retrieve_state.get_hero("hero_xargatha")
        assert any(c.id == "card_a" for c in hero.hand)
        assert len(hero.discard_pile) == 1

    def test_adjacent_enemy_minion_retrieves_card(self, retrieve_state):
        """Adjacent enemy minion → can retrieve a discarded card."""
        # Remove hero, keep melee_1 adjacent
        retrieve_state.remove_entity("hero_enemy")

        req = self._run_devoted_followers(retrieve_state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"

        retrieve_state.execution_stack[-1].pending_input = {
            "selection": "card_b"
        }
        process_resolution_stack(retrieve_state)

        hero = retrieve_state.get_hero("hero_xargatha")
        assert any(c.id == "card_b" for c in hero.hand)

    def test_no_adjacent_enemies_skips(self, retrieve_state):
        """No adjacent enemies → no card selection prompt."""
        retrieve_state.remove_entity("melee_1")
        retrieve_state.remove_entity("hero_enemy")

        req = self._run_devoted_followers(retrieve_state)
        assert req is None

    def test_empty_discard_pile_skips(self, retrieve_state):
        """Adjacent enemy but empty discard pile → skips gracefully."""
        hero = retrieve_state.get_hero("hero_xargatha")
        hero.discard_pile.clear()

        req = self._run_devoted_followers(retrieve_state)
        # No cards to select → optional step skips
        assert req is None

    def test_player_skips_selection(self, retrieve_state):
        """Player chooses to skip optional card retrieval."""
        req = self._run_devoted_followers(retrieve_state)
        assert req is not None

        # Submit SKIP
        retrieve_state.execution_stack[-1].pending_input = {
            "selection": "SKIP"
        }
        process_resolution_stack(retrieve_state)

        hero = retrieve_state.get_hero("hero_xargatha")
        assert len(hero.hand) == 0
        assert len(hero.discard_pile) == 2


# ---------------------------------------------------------------------------
# Fresh Converts integration tests
# ---------------------------------------------------------------------------


class TestFreshConverts:
    def _run_fresh_converts(self, state):
        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get("fresh_converts")
        hero = state.get_hero("hero_xargatha")
        steps = effect.build_steps(state, hero, None, _make_fake_stats())
        push_steps(state, steps)
        return process_resolution_stack(state)

    def test_adjacent_enemy_minion_retrieves_card(self, retrieve_state):
        """Adjacent enemy minion → can retrieve a discarded card."""
        req = self._run_fresh_converts(retrieve_state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"

        retrieve_state.execution_stack[-1].pending_input = {
            "selection": "card_a"
        }
        process_resolution_stack(retrieve_state)

        hero = retrieve_state.get_hero("hero_xargatha")
        assert any(c.id == "card_a" for c in hero.hand)

    def test_adjacent_enemy_hero_only_skips(self, retrieve_state):
        """Adjacent enemy hero but no enemy minion → skips."""
        retrieve_state.remove_entity("melee_1")

        req = self._run_fresh_converts(retrieve_state)
        assert req is None

    def test_no_adjacent_enemies_skips(self, retrieve_state):
        """No adjacent enemies at all → skips."""
        retrieve_state.remove_entity("melee_1")
        retrieve_state.remove_entity("hero_enemy")

        req = self._run_fresh_converts(retrieve_state)
        assert req is None

    def test_empty_discard_pile_skips(self, retrieve_state):
        """Adjacent enemy minion but empty discard → skips."""
        hero = retrieve_state.get_hero("hero_xargatha")
        hero.discard_pile.clear()

        req = self._run_fresh_converts(retrieve_state)
        assert req is None

    def test_player_skips_selection(self, retrieve_state):
        """Player skips optional card retrieval."""
        req = self._run_fresh_converts(retrieve_state)
        assert req is not None

        retrieve_state.execution_stack[-1].pending_input = {
            "selection": "SKIP"
        }
        process_resolution_stack(retrieve_state)

        hero = retrieve_state.get_hero("hero_xargatha")
        assert len(hero.hand) == 0


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerializationRoundTrip:
    def test_count_step_round_trip(self):
        step = CountStep(
            target_type=TargetType.UNIT,
            filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
            output_key="count",
        )
        data = step.model_dump()
        restored = CountStep.model_validate(data)
        assert restored.type == StepType.COUNT
        assert len(restored.filters) == 2

    def test_check_context_condition_step_round_trip(self):
        step = CheckContextConditionStep(
            input_key="count", operator=">=", threshold=1, output_key="result"
        )
        data = step.model_dump()
        restored = CheckContextConditionStep.model_validate(data)
        assert restored.type == StepType.CHECK_CONTEXT_CONDITION
        assert restored.operator == ">="

    def test_retrieve_card_step_round_trip(self):
        step = RetrieveCardStep(card_key="card_sel", active_if_key="flag")
        data = step.model_dump()
        restored = RetrieveCardStep.model_validate(data)
        assert restored.type == StepType.RETRIEVE_CARD
        assert restored.card_key == "card_sel"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class _FakeStats:
    primary_value = 0
    range = None
    radius = None


def _make_fake_stats():
    return _FakeStats()
