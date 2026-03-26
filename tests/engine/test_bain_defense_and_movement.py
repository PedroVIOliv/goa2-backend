"""
Tests for Bain's defense cards (Close Call, Narrow Escape) and
movement cards (Vantage Point, High Ground).
"""

import pytest
import goa2.scripts.bain_effects  # noqa: F401 — registers effects

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
from goa2.domain.models.marker import MarkerType
from goa2.engine.steps import MoveSequenceStep
from goa2.engine.stats import CardStats


# =============================================================================
# Card Factories
# =============================================================================


def _make_defense_card(card_id, name, effect_id):
    return Card(
        id=card_id,
        name=name,
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.DEFENSE,
        secondary_actions={},
        is_ranged=False,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


def _make_movement_card(card_id, name, effect_id, tier=CardTier.II):
    return Card(
        id=card_id,
        name=name,
        tier=tier,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        secondary_actions={},
        is_ranged=False,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def game_state():
    board = Board()
    hexes = set()
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            if abs(s) <= 3:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(
        id="hero_bain", name="Bain", team=TeamColor.RED, deck=[], level=1
    )
    enemy = Hero(
        id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[], level=1
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy], minions=[]
            ),
        },
    )
    state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_hero", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "hero_bain"
    return state


# =============================================================================
# Close Call Tests
# =============================================================================


def test_close_call_blocks_and_transfers_bounty(game_state):
    """Close Call blocks and places bounty marker on defender (Bain)."""
    from goa2.scripts.bain_effects import CloseCallEffect

    marker = game_state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = CloseCallEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_defense_card("cc", "Close Call", "close_call")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": False, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(game_state, hero, card, stats, context)

    assert len(steps) == 2
    assert steps[0].key == "auto_block"
    assert steps[0].value is True
    # Second step transfers marker to defender
    assert steps[1].marker_type == MarkerType.BOUNTY
    assert steps[1].target_id == "hero_bain"


def test_close_call_invalid_without_bounty(game_state):
    """Close Call is invalid when no bounty marker in play."""
    from goa2.scripts.bain_effects import CloseCallEffect

    effect = CloseCallEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_defense_card("cc", "Close Call", "close_call")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": False, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(game_state, hero, card, stats, context)

    assert len(steps) == 1
    assert steps[0].key == "defense_invalid"
    assert steps[0].value is True


def test_close_call_works_when_bounty_on_any_hero(game_state):
    """Close Call works when bounty is on a different hero (not attacker)."""
    from goa2.scripts.bain_effects import CloseCallEffect

    other = Hero(id="other", name="Other", team=TeamColor.RED, deck=[], level=1)
    game_state.teams[TeamColor.RED].heroes.append(other)
    game_state.place_entity("other", Hex(q=-1, r=0, s=1))

    marker = game_state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="other", value=0, source_id="hero_bain")

    effect = CloseCallEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_defense_card("cc", "Close Call", "close_call")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": False, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(game_state, hero, card, stats, context)

    assert len(steps) == 2
    assert steps[0].key == "auto_block"
    assert steps[1].target_id == "hero_bain"


# =============================================================================
# Narrow Escape Tests
# =============================================================================


def test_narrow_escape_blocks_and_removes_bounty(game_state):
    """Narrow Escape blocks and removes the bounty marker from play."""
    from goa2.scripts.bain_effects import NarrowEscapeEffect

    marker = game_state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = NarrowEscapeEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_defense_card("ne", "Narrow Escape", "narrow_escape")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": True, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(game_state, hero, card, stats, context)

    assert len(steps) == 2
    assert steps[0].key == "auto_block"
    assert steps[0].value is True
    assert steps[1].marker_type == MarkerType.BOUNTY


def test_narrow_escape_invalid_without_bounty(game_state):
    """Narrow Escape is invalid when no bounty marker in play."""
    from goa2.scripts.bain_effects import NarrowEscapeEffect

    effect = NarrowEscapeEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_defense_card("ne", "Narrow Escape", "narrow_escape")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": True, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(game_state, hero, card, stats, context)

    assert len(steps) == 1
    assert steps[0].key == "defense_invalid"
    assert steps[0].value is True


# =============================================================================
# Vantage Point Tests
# =============================================================================


def test_vantage_point_base_movement(game_state):
    """Vantage Point returns MoveSequenceStep with pass_through_obstacles."""
    from goa2.scripts.bain_effects import VantagePointEffect

    effect = VantagePointEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_movement_card("vp", "Vantage Point", "vantage_point")
    stats = CardStats(primary_value=2, range=0)

    steps = effect.build_steps(game_state, hero, card, stats)

    assert len(steps) == 1
    assert isinstance(steps[0], MoveSequenceStep)
    assert steps[0].pass_through_obstacles is True
    assert steps[0].range_val == 2


def test_vantage_point_bonus_with_bounty(game_state):
    """Vantage Point gets +1 movement when bounty marker is in play."""
    from goa2.scripts.bain_effects import VantagePointEffect

    marker = game_state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = VantagePointEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_movement_card("vp", "Vantage Point", "vantage_point")
    stats = CardStats(primary_value=2, range=0)

    steps = effect.build_steps(game_state, hero, card, stats)

    assert len(steps) == 1
    assert steps[0].range_val == 3  # 2 base + 1 bounty bonus


# =============================================================================
# High Ground Tests
# =============================================================================


def test_high_ground_base_movement(game_state):
    """High Ground returns MoveSequenceStep with pass_through_obstacles."""
    from goa2.scripts.bain_effects import HighGroundEffect

    effect = HighGroundEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_movement_card(
        "hg", "High Ground", "high_ground", tier=CardTier.III
    )
    stats = CardStats(primary_value=2, range=0)

    steps = effect.build_steps(game_state, hero, card, stats)

    assert len(steps) == 1
    assert isinstance(steps[0], MoveSequenceStep)
    assert steps[0].pass_through_obstacles is True
    assert steps[0].range_val == 2


def test_high_ground_bonus_with_bounty(game_state):
    """High Ground gets +2 movement when bounty marker is in play."""
    from goa2.scripts.bain_effects import HighGroundEffect

    marker = game_state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = HighGroundEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_movement_card(
        "hg", "High Ground", "high_ground", tier=CardTier.III
    )
    stats = CardStats(primary_value=2, range=0)

    steps = effect.build_steps(game_state, hero, card, stats)

    assert len(steps) == 1
    assert steps[0].range_val == 4  # 2 base + 2 bounty bonus


def test_high_ground_no_bonus_without_bounty(game_state):
    """High Ground has no bonus when bounty marker is not in play."""
    from goa2.scripts.bain_effects import HighGroundEffect

    effect = HighGroundEffect()
    hero = game_state.get_hero("hero_bain")
    card = _make_movement_card(
        "hg", "High Ground", "high_ground", tier=CardTier.III
    )
    stats = CardStats(primary_value=2, range=0)

    steps = effect.build_steps(game_state, hero, card, stats)

    assert steps[0].range_val == 2  # No bonus
