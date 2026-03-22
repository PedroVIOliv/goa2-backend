"""Tests for Sabina's Big Sodding Gun ultimate passive."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Hero,
    Minion,
    MinionType,
    StatType,
)
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps import PushUnitStep, CheckPassiveAbilitiesStep
from goa2.engine.handler import process_resolution_stack, push_steps

# Ensure sabina effects are registered
import goa2.scripts.sabina_effects  # noqa: F401


def _make_ultimate_card(effect_id: str = "big_sodding_gun") -> Card:
    return Card(
        id="sabina_ultimate",
        name="Big Sodding Gun",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        primary_action=ActionType.SKILL,
        effect_id=effect_id,
        effect_text="Your basic attack has +2 Range and +2 Attack. If you push an enemy hero, that hero discards a card, or is defeated.",
        initiative=0,
        is_facedown=False,
    )


def _make_basic_attack_card(card_id="basic_atk", attack_value=3, range_value=2):
    return Card(
        id=card_id,
        name="Basic Attack",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=3,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=True,
        range_value=range_value,
        primary_action_value=attack_value,
        effect_id="basic_attack",
        effect_text="",
        is_facedown=False,
    )


def _make_nonbasic_attack_card(card_id="quickdraw_card"):
    return Card(
        id=card_id,
        name="Quickdraw",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=True,
        range_value=3,
        primary_action_value=4,
        effect_id="quickdraw",
        effect_text="",
        is_facedown=False,
    )


def _make_basic_skill_card(card_id="basic_skill"):
    return Card(
        id=card_id,
        name="Basic Skill",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=2,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        radius_value=2,
        effect_id="back_to_back",
        effect_text="",
        is_facedown=False,
    )


def _make_filler_card(card_id="filler"):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


def _make_board_with_hexes(*hexes: Hex) -> Board:
    board = Board()
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    return board


# ---------------------------------------------------------------------------
# Part 1: Stat Aura Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def aura_state():
    """Sabina at level 8 with Big Sodding Gun ultimate."""
    center = Hex(q=0, r=0, s=0)
    adj = Hex(q=1, r=0, s=-1)
    far = Hex(q=2, r=0, s=-2)

    board = _make_board_with_hexes(center, adj, far)

    sabina = Hero(
        id="hero_sabina",
        name="Sabina",
        team=TeamColor.RED,
        deck=[],
        level=8,
        ultimate_card=_make_ultimate_card(),
    )
    enemy = Hero(
        id="enemy",
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[sabina], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_sabina", center)
    state.place_entity("enemy", adj)
    state.current_actor_id = "hero_sabina"
    return state


def test_flat_bonus_applies_during_basic_attack(aura_state):
    """Flat +2 Attack and +2 Range should apply when current card is basic attack."""
    sabina = aura_state.get_hero("hero_sabina")
    basic_card = _make_basic_attack_card(attack_value=3, range_value=2)
    sabina.current_turn_card = basic_card

    attack_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.ATTACK, 3
    )
    range_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.RANGE, 2
    )

    assert attack_stat == 5  # 3 + 2
    assert range_stat == 4  # 2 + 2


def test_flat_bonus_does_not_apply_to_nonbasic_attack(aura_state):
    """Non-basic attack cards (e.g. Quickdraw) should NOT get the bonus."""
    sabina = aura_state.get_hero("hero_sabina")
    sabina.current_turn_card = _make_nonbasic_attack_card()

    attack_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.ATTACK, 4
    )
    range_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.RANGE, 3
    )

    assert attack_stat == 4  # No bonus
    assert range_stat == 3  # No bonus


def test_flat_bonus_does_not_apply_to_basic_skill(aura_state):
    """Basic skill cards should NOT get attack/range bonus."""
    sabina = aura_state.get_hero("hero_sabina")
    sabina.current_turn_card = _make_basic_skill_card()

    attack_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.ATTACK, 0
    )
    range_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.RANGE, 0
    )

    assert attack_stat == 0  # No bonus
    assert range_stat == 0  # No bonus


def test_flat_bonus_does_not_apply_without_card(aura_state):
    """When no current_turn_card is set, bonus should not apply."""
    sabina = aura_state.get_hero("hero_sabina")
    sabina.current_turn_card = None

    attack_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.ATTACK, 3
    )

    assert attack_stat == 3  # No bonus


def test_flat_bonus_not_active_below_level_8(aura_state):
    """Ultimate auras only active at level 8+."""
    sabina = aura_state.get_hero("hero_sabina")
    sabina.level = 7
    sabina.current_turn_card = _make_basic_attack_card()

    attack_stat = get_computed_stat(
        aura_state, UnitID("hero_sabina"), StatType.ATTACK, 3
    )

    assert attack_stat == 3  # No bonus — level too low


# ---------------------------------------------------------------------------
# Part 2: AFTER_PUSH Passive Trigger Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def push_state():
    """Sabina with Big Sodding Gun, enemy hero adjacent, line of hexes for push."""
    hexes = [Hex(q=q, r=0, s=-q) for q in range(-3, 4)]
    board = _make_board_with_hexes(*hexes)

    sabina = Hero(
        id="hero_sabina",
        name="Sabina",
        team=TeamColor.RED,
        deck=[],
        level=8,
        ultimate_card=_make_ultimate_card(),
    )

    enemy_hero = Hero(
        id="enemy_hero",
        name="Enemy Hero",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_hero.hand = [_make_filler_card("enemy_card_1")]

    enemy_minion = Minion(
        id="enemy_minion",
        name="Enemy Minion",
        team=TeamColor.BLUE,
        type=MinionType.MELEE,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[sabina], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[enemy_hero],
                minions=[enemy_minion],
            ),
        },
    )
    state.place_entity("hero_sabina", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_hero", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy_minion", Hex(q=-1, r=0, s=1))
    state.current_actor_id = "hero_sabina"
    return state


def test_push_enemy_hero_triggers_discard_or_defeat(push_state):
    """Pushing an enemy hero should trigger ForceDiscardOrDefeatStep."""
    push_steps(
        push_state,
        [PushUnitStep(target_id="enemy_hero", distance=2)],
    )

    # Process the push
    result = process_resolution_stack(push_state)

    # Enemy hero should have been pushed
    enemy_loc = push_state.entity_locations.get("enemy_hero")
    assert enemy_loc == Hex(q=3, r=0, s=-3)

    # The AFTER_PUSH passive fires automatically (is_optional=False)
    # and spawns ForceDiscardOrDefeatStep.
    # Enemy has 1 card in hand, so they must choose to discard it.
    # Process until we get the discard card selection input request.
    assert result is not None
    assert result["type"] == "SELECT_CARD"

    # Provide card selection (enemy chooses to discard their card)
    push_state.execution_stack[-1].pending_input = {
        "selection": "enemy_card_1"
    }
    result = process_resolution_stack(push_state)

    # Should be done now
    assert result is None

    # Verify enemy hero discarded their card
    enemy = push_state.get_hero("enemy_hero")
    assert len(enemy.hand) == 0


def test_push_minion_does_not_trigger_passive(push_state):
    """Pushing a minion should NOT trigger discard/defeat."""
    push_steps(
        push_state,
        [PushUnitStep(target_id="enemy_minion", distance=1)],
    )

    result = process_resolution_stack(push_state)

    # No input should be requested — passive doesn't fire for minions
    assert result is None

    # Minion was pushed
    minion_loc = push_state.entity_locations.get("enemy_minion")
    assert minion_loc == Hex(q=-2, r=0, s=2)


def test_push_friendly_hero_does_not_trigger_passive(push_state):
    """Pushing a friendly hero should NOT trigger discard/defeat."""
    # Add a friendly hero to push
    friendly = Hero(
        id="friendly_hero",
        name="Friendly",
        team=TeamColor.RED,
        deck=[],
        level=1,
    )
    friendly.hand = [_make_filler_card("friendly_card")]
    push_state.teams[TeamColor.RED].heroes.append(friendly)

    # Remove enemy minion from that hex first
    push_state.remove_unit(UnitID("enemy_minion"))
    push_state.place_entity("friendly_hero", Hex(q=-1, r=0, s=1))

    push_steps(
        push_state,
        [PushUnitStep(target_id="friendly_hero", distance=1)],
    )

    result = process_resolution_stack(push_state)

    # No discard triggered
    assert result is None

    # Friendly hero still has their card
    assert len(friendly.hand) == 1


def test_push_zero_distance_still_triggers(push_state):
    """Push with 0 distance (blocked immediately) still counts as a push."""
    # Remove hex behind enemy so push can't move them (off board)
    del push_state.board.tiles[Hex(q=2, r=0, s=-2)]

    push_steps(
        push_state,
        [PushUnitStep(target_id="enemy_hero", distance=1)],
    )

    result = process_resolution_stack(push_state)

    # Enemy hero still at original position (couldn't move)
    enemy_loc = push_state.entity_locations.get("enemy_hero")
    assert enemy_loc == Hex(q=1, r=0, s=-1)

    # But AFTER_PUSH still fires — enemy must discard
    assert result is not None
    assert result["type"] == "SELECT_CARD"

    push_state.execution_stack[-1].pending_input = {
        "selection": "enemy_card_1"
    }
    result = process_resolution_stack(push_state)
    assert result is None

    enemy = push_state.get_hero("enemy_hero")
    assert len(enemy.hand) == 0


def test_push_enemy_hero_no_cards_defeats(push_state):
    """Pushing enemy hero with no cards should defeat them."""
    # Empty enemy hand
    enemy = push_state.get_hero("enemy_hero")
    enemy.hand = []

    push_steps(
        push_state,
        [PushUnitStep(target_id="enemy_hero", distance=1)],
    )

    # Process everything
    result = process_resolution_stack(push_state)
    while result is not None:
        result = process_resolution_stack(push_state)

    # Enemy hero should be defeated (removed from board)
    assert push_state.entity_locations.get("enemy_hero") is None
