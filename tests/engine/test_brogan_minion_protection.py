"""Tests for Brogan's Shield/Bolster/Fortify minion protection effects."""

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
from goa2.engine.steps import (
    DefeatUnitStep,
)
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effect_manager import EffectManager
from goa2.domain.models.effect import (
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)


def _make_card(card_id, name, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        radius_value=2,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_silver_card(card_id="silver_card"):
    return Card(
        id=card_id,
        name="Silver Card",
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
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


def _make_gold_card(card_id="gold_card"):
    return Card(
        id=card_id,
        name="Gold Card",
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
def protection_state():
    """State with Brogan, enemy hero, and a friendly minion in a small board."""
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

    shield_card = _make_card("shield_card", "Shield", "shield", radius_value=2)

    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    brogan.current_turn_card = shield_card
    brogan.hand = [_make_silver_card("silver1"), _make_silver_card("silver2")]

    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

    minion = Minion(
        id="minion_red_1",
        name="Red Minion",
        team=TeamColor.RED,
        type=MinionType.MELEE,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[brogan], minions=[minion],
                life_counters=10,
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy], minions=[],
                life_counters=10,
            ),
        },
    )

    # Place units: Brogan at (0,0,0), minion at (1,0,-1), enemy at (2,0,-2)
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("minion_red_1", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy", Hex(q=2, r=0, s=-2))

    state.current_actor_id = "brogan"
    return state


def _create_protection_effect(state, allowed_colors=None, radius=2):
    """Directly create a MINION_PROTECTION effect for Brogan."""
    if allowed_colors is None:
        allowed_colors = [CardColor.SILVER]
    EffectManager.create_effect(
        state=state,
        source_id="brogan",
        effect_type=EffectType.MINION_PROTECTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=radius,
            origin_id="brogan",
            affects=AffectsFilter.FRIENDLY_UNITS,
        ),
        duration=DurationType.THIS_ROUND,
        is_active=True,
        allowed_discard_colors=allowed_colors,
    )


def test_basic_protection_saves_minion(protection_state):
    """Minion in radius defeated, Brogan discards silver, minion stays."""
    state = protection_state
    _create_protection_effect(state)

    # Verify protection effect exists
    assert any(e.effect_type == EffectType.MINION_PROTECTION for e in state.active_effects)

    # Defeat the minion
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)

    # Should get CheckMinionProtectionStep asking Brogan to discard
    assert result is not None
    assert result["type"] == "SELECT_CARD"
    assert result["player_id"] == "brogan"

    # Brogan chooses to discard silver1
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    result = process_resolution_stack(state)

    # Minion should still be on the board
    assert state.entity_locations.get("minion_red_1") is not None
    # Card was discarded
    brogan = state.get_hero("brogan")
    assert len(brogan.hand) == 1
    assert brogan.hand[0].id == "silver2"


def test_gold_awarded_even_when_protected(protection_state):
    """Enemy killer still gets gold even when minion is saved."""
    state = protection_state
    _create_protection_effect(state)

    enemy = state.get_hero("enemy")
    gold_before = enemy.gold

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)

    # Gold was awarded in DefeatUnitStep before protection check
    assert enemy.gold == gold_before + 2  # MELEE minion value = 2

    # Protect the minion
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    process_resolution_stack(state)

    # Minion stays, gold stays
    assert state.entity_locations.get("minion_red_1") is not None
    assert enemy.gold == gold_before + 2


def test_decline_protection_removes_minion(protection_state):
    """Brogan skips → minion is removed normally."""
    state = protection_state
    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    assert result is not None

    # Skip protection
    state.execution_stack[-1].pending_input = {"selected_card_id": "SKIP"}
    result = process_resolution_stack(state)

    # Process RemoveUnitStep
    while result is not None:
        result = process_resolution_stack(state)

    assert state.entity_locations.get("minion_red_1") is None


def test_no_qualifying_cards_auto_skips(protection_state):
    """Brogan has no silver cards → no prompt, minion removed."""
    state = protection_state
    brogan = state.get_hero("brogan")
    # Replace hand with non-silver cards
    brogan.hand = [
        _make_card("red_card", "Red Card", "filler", color=CardColor.RED)
    ]

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    # Process everything — no input request expected
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)

    assert state.entity_locations.get("minion_red_1") is None


def test_out_of_radius_no_protection(protection_state):
    """Minion outside radius → no protection, normal removal."""
    state = protection_state

    # Move minion far away (radius=2, move to distance 3)
    from goa2.domain.types import UnitID
    state.move_unit(UnitID("minion_red_1"), Hex(q=3, r=0, s=-3))

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)

    assert state.entity_locations.get("minion_red_1") is None


def test_fortify_accepts_gold_card(protection_state):
    """Fortify allows discarding gold OR silver cards."""
    state = protection_state
    brogan = state.get_hero("brogan")
    brogan.hand = [_make_gold_card("gold1")]

    _create_protection_effect(state, allowed_colors=[CardColor.GOLD, CardColor.SILVER])

    # Defeat minion
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    assert result is not None
    assert result["type"] == "SELECT_CARD"

    # Discard gold card
    state.execution_stack[-1].pending_input = {"selected_card_id": "gold1"}
    result = process_resolution_stack(state)

    # Minion saved
    assert state.entity_locations.get("minion_red_1") is not None
    assert len(brogan.hand) == 0


def test_multiple_defeats_protection_triggers_multiple_times(protection_state):
    """Protection can trigger multiple times in the same round."""
    state = protection_state

    # Add a second minion
    minion2 = Minion(
        id="minion_red_2", name="Red Minion 2", team=TeamColor.RED,
        type=MinionType.MELEE,
    )
    state.teams[TeamColor.RED].minions.append(minion2)
    state.place_entity("minion_red_2", Hex(q=0, r=1, s=-1))

    _create_protection_effect(state)

    # Defeat first minion — protect it
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    assert result is not None
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)
    assert state.entity_locations.get("minion_red_1") is not None

    # Defeat second minion — protect it too
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_2", killer_id="enemy")])
    result = process_resolution_stack(state)
    assert result is not None
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver2"}
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)
    assert state.entity_locations.get("minion_red_2") is not None

    # Both cards discarded
    brogan = state.get_hero("brogan")
    assert len(brogan.hand) == 0


def test_empty_hand_no_prompt(protection_state):
    """Brogan has no cards at all → no prompt, minion removed."""
    state = protection_state
    brogan = state.get_hero("brogan")
    brogan.hand = []

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)

    assert state.entity_locations.get("minion_red_1") is None


def test_shield_silver_only_rejects_gold(protection_state):
    """Shield only accepts silver — gold cards not offered."""
    state = protection_state
    brogan = state.get_hero("brogan")
    brogan.hand = [_make_gold_card("gold_only")]

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)

    # Gold card not qualifying for Shield → minion removed
    assert state.entity_locations.get("minion_red_1") is None
    # Gold card still in hand
    assert len(brogan.hand) == 1
