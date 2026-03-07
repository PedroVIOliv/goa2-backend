"""Tests for Brogan's Throwing Spear card effect."""

import pytest
import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
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
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps


def _make_card(card_id, name, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=True,
        range_value=3,
        primary_action_value=4,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_filler_card(card_id="filler_card"):
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


@pytest.fixture
def spear_state():
    board = Board()
    hexes = set()
    # Create a line of hexes: (0,0,0) to (4,0,-4)
    for q in range(5):
        hexes.add(Hex(q=q, r=0, s=-q))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    spear_card = _make_card("throwing_spear", "Throwing Spear", "throwing_spear")

    hero = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    hero.current_turn_card = spear_card

    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    # Give enemy some hand cards so reactions can work
    enemy.hand = [_make_filler_card("enemy_card")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "brogan"

    return state


def test_throwing_spear_melee_attacks_adjacent(spear_state):
    """Option 1 (melee): attacks adjacent enemy."""
    push_steps(spear_state, [ResolveCardStep(hero_id="brogan")])

    # CHOOSE_ACTION
    req = process_resolution_stack(spear_state)
    assert req["type"] == "CHOOSE_ACTION"
    spear_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # SELECT_NUMBER: choose melee (1)
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_NUMBER"
    spear_state.execution_stack[-1].pending_input = {"selection": 1}

    # SELECT_UNIT: select adjacent enemy
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy" in req["valid_options"]
    spear_state.execution_stack[-1].pending_input = {"selection": "enemy"}

    # SELECT_CARD_OR_PASS: reaction window
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    spear_state.execution_stack[-1].pending_input = {"selection": "PASS"}

    # Resolve combat
    res = process_resolution_stack(spear_state)
    # Stack should be empty
    assert res is None


def test_throwing_spear_ranged_with_discard(spear_state):
    """Option 2 with discard: discards a card, then attacks in range."""
    # Move enemy to range 3
    spear_state.place_entity("enemy", Hex(q=3, r=0, s=-3))

    hero = spear_state.get_hero("brogan")
    filler = _make_filler_card("hand_card")
    hero.hand = [filler]

    push_steps(spear_state, [ResolveCardStep(hero_id="brogan")])

    # CHOOSE_ACTION
    req = process_resolution_stack(spear_state)
    assert req["type"] == "CHOOSE_ACTION"
    spear_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # SELECT_NUMBER: choose ranged (2)
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_NUMBER"
    spear_state.execution_stack[-1].pending_input = {"selection": 2}

    # SELECT_CARD: optional discard from hand
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_CARD"
    assert "hand_card" in req["valid_options"]
    spear_state.execution_stack[-1].pending_input = {"selection": "hand_card"}

    # SELECT_UNIT: select target in range (enemy at range 3)
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy" in req["valid_options"]
    spear_state.execution_stack[-1].pending_input = {"selection": "enemy"}

    # SELECT_CARD_OR_PASS: reaction window
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    spear_state.execution_stack[-1].pending_input = {"selection": "PASS"}

    # Resolve combat
    res = process_resolution_stack(spear_state)
    assert res is None

    # Verify card was discarded
    assert len(hero.discard_pile) == 1
    assert hero.discard_pile[0].id == "hand_card"


def test_throwing_spear_ranged_no_discard_but_existing_discard(spear_state):
    """Option 2 without discard but with existing card in discard: attacks in range."""
    # Move enemy to range 3
    spear_state.place_entity("enemy", Hex(q=3, r=0, s=-3))

    hero = spear_state.get_hero("brogan")
    # Put a card in the discard pile already
    existing_discard = _make_filler_card("existing_discard")
    hero.discard_card(existing_discard, from_hand=False)

    push_steps(spear_state, [ResolveCardStep(hero_id="brogan")])

    # CHOOSE_ACTION
    req = process_resolution_stack(spear_state)
    assert req["type"] == "CHOOSE_ACTION"
    spear_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # SELECT_NUMBER: choose ranged (2)
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_NUMBER"
    spear_state.execution_stack[-1].pending_input = {"selection": 2}

    # SELECT_CARD: optional discard — skip it
    req = process_resolution_stack(spear_state)
    # Could be SELECT_CARD if hand has cards, or might skip if hand empty
    # With empty hand, the SelectStep for card should auto-skip
    # Let's check what happens — with empty hand it should skip
    # Actually the hero has no hand cards, so SelectStep should produce no valid options
    # and since is_mandatory=False, it auto-skips

    # SELECT_UNIT: select target in range (enemy at range 3)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy" in req["valid_options"]
    spear_state.execution_stack[-1].pending_input = {"selection": "enemy"}

    # SELECT_CARD_OR_PASS: reaction window
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    spear_state.execution_stack[-1].pending_input = {"selection": "PASS"}

    # Resolve combat
    res = process_resolution_stack(spear_state)
    assert res is None

    # Discard pile still has the original card
    assert len(hero.discard_pile) == 1
    assert hero.discard_pile[0].id == "existing_discard"


def test_throwing_spear_ranged_no_discard_empty_pile_no_attack(spear_state):
    """Option 2 without discard and empty discard pile: no attack happens."""
    # Move enemy to range 3
    spear_state.place_entity("enemy", Hex(q=3, r=0, s=-3))

    hero = spear_state.get_hero("brogan")
    # No hand cards, no discard pile — ranged attack should not happen

    push_steps(spear_state, [ResolveCardStep(hero_id="brogan")])

    # CHOOSE_ACTION
    req = process_resolution_stack(spear_state)
    assert req["type"] == "CHOOSE_ACTION"
    spear_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # SELECT_NUMBER: choose ranged (2)
    req = process_resolution_stack(spear_state)
    assert req["type"] == "SELECT_NUMBER"
    spear_state.execution_stack[-1].pending_input = {"selection": 2}

    # With empty hand, optional card select auto-skips
    # With empty discard, CountCardsStep stores 0, condition fails
    # AttackSequenceStep skipped due to active_if_key="has_discard" being None
    res = process_resolution_stack(spear_state)
    assert res is None  # Stack finishes with no attack
