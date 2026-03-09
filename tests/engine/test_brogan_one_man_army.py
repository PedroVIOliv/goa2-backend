"""Tests for Brogan's One Man Army ultimate effect."""

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
    Minion,
    MinionType,
)
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID
from goa2.engine.steps import MinionBattleStep
from goa2.engine.handler import process_resolution_stack, push_steps


def _make_ultimate_card():
    return Card(
        id="brogan_ult",
        name="One Man Army",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=None,
        effect_id="one_man_army",
        effect_text="During minion battle you count as a heavy minion.",
        is_facedown=False,
    )


@pytest.fixture
def battle_state():
    board = Board()
    hexes = set()
    for q in range(8):
        hexes.add(Hex(q=q, r=0, s=-q))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    brogan = Hero(
        id="brogan",
        name="Brogan",
        team=TeamColor.RED,
        deck=[],
        level=8,
        ultimate_card=_make_ultimate_card(),
    )
    enemy_hero = Hero(
        id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[], level=1
    )

    red_team = Team(color=TeamColor.RED, heroes=[brogan])
    blue_team = Team(color=TeamColor.BLUE, heroes=[enemy_hero])

    state = GameState(
        teams={TeamColor.RED: red_team, TeamColor.BLUE: blue_team},
        board=board,
    )
    state.active_zone_id = "z1"

    # Place brogan in the zone
    state.entity_locations[HeroID("brogan")] = Hex(q=0, r=0, s=0)

    return state


def _add_minions(state, team, count, start_q=1):
    """Add minions of a given team to the zone."""
    for i in range(count):
        mid = f"{team.value.lower()}_minion_{i}"
        minion = Minion(id=mid, name=f"Minion {mid}", team=team, type=MinionType.MELEE)
        state.register_entity(minion, collection_type="minion")
        state.entity_locations[mid] = Hex(q=start_q + i, r=0, s=-(start_q + i))


def _count_minions_in_zone(state, team):
    """Count minions of a team still in the active zone."""
    zone = state.board.zones[state.active_zone_id]
    count = 0
    for unit_id, loc in state.unit_locations.items():
        if loc in zone.hexes:
            unit = state.get_unit(unit_id)
            if unit and isinstance(unit, Minion) and unit.team == team:
                count += 1
    return count


class TestOneManArmy:
    def test_brogan_adds_one_to_team_count(self, battle_state):
        """2 red minions + Brogan(+1) vs 3 blue → 3 vs 3 → tie, no removals."""
        _add_minions(battle_state, TeamColor.RED, 2, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 3, start_q=3)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # Tied — no removals
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 2
        assert _count_minions_in_zone(battle_state, TeamColor.BLUE) == 3

    def test_no_bonus_when_level_below_8(self, battle_state):
        """Without one_man_army active (level < 8), 2 red vs 3 blue → red loses 1."""
        brogan = battle_state.teams[TeamColor.RED].heroes[0]
        brogan.level = 7  # Below ultimate threshold

        _add_minions(battle_state, TeamColor.RED, 2, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 3, start_q=3)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # No bonus → 2 vs 3 → red loses 1
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 1
        assert _count_minions_in_zone(battle_state, TeamColor.BLUE) == 3

    def test_no_bonus_when_brogan_outside_zone(self, battle_state):
        """Brogan outside the active zone doesn't get the bonus."""
        # Move brogan outside the zone
        battle_state.entity_locations[HeroID("brogan")] = Hex(q=10, r=0, s=-10)

        _add_minions(battle_state, TeamColor.RED, 2, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 3, start_q=3)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # No bonus → 2 vs 3 → red loses 1
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 1
        assert _count_minions_in_zone(battle_state, TeamColor.BLUE) == 3

    def test_bonus_creates_advantage(self, battle_state):
        """3 red minions + Brogan(+1) vs 2 blue → 4 vs 2 → blue loses 2."""
        _add_minions(battle_state, TeamColor.RED, 3, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 2, start_q=4)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # Blue loses 2 — all blue minions removed
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 3
        assert _count_minions_in_zone(battle_state, TeamColor.BLUE) == 0

    def test_no_bonus_without_ultimate_card(self, battle_state):
        """Hero at level 8 but without an ultimate card gets no bonus."""
        brogan = battle_state.teams[TeamColor.RED].heroes[0]
        brogan.ultimate_card = None

        _add_minions(battle_state, TeamColor.RED, 2, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 3, start_q=3)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # No bonus → 2 vs 3 → red loses 1
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 1

    def test_no_bonus_for_different_effect_id(self, battle_state):
        """Hero with a different ultimate effect_id gets no bonus."""
        brogan = battle_state.teams[TeamColor.RED].heroes[0]
        brogan.ultimate_card = Card(
            id="other_ult",
            name="Other Ult",
            tier=CardTier.IV,
            color=CardColor.PURPLE,
            initiative=0,
            primary_action=ActionType.SKILL,
            secondary_actions={},
            is_ranged=False,
            range_value=0,
            primary_action_value=None,
            effect_id="some_other_effect",
            effect_text="",
            is_facedown=False,
        )

        _add_minions(battle_state, TeamColor.RED, 2, start_q=1)
        _add_minions(battle_state, TeamColor.BLUE, 3, start_q=3)

        push_steps(battle_state, [MinionBattleStep()])
        process_resolution_stack(battle_state)

        # No bonus → 2 vs 3 → red loses 1
        assert _count_minions_in_zone(battle_state, TeamColor.RED) == 1
