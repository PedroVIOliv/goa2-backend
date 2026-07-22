"""Tests for Brogan's Shield/Bolster/Fortify minion protection effects."""

import pytest

import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
from goa2.domain.board import Board, Zone
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Minion,
    MinionType,
    Team,
    TeamColor,
    Token,
    TokenType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.effect_manager import EffectManager
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import (
    DefeatUnitStep,
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
                color=TeamColor.RED,
                heroes=[brogan],
                minions=[minion],
                life_counters=10,
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[enemy],
                minions=[],
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


def _add_sacrifice_totem(state, *, owner_id="brogan", token_id="totem_1", totem_hex=None):
    """Place a Tali-style Totem (sacrifice protection) adjacent to the minion."""
    if totem_hex is None:
        totem_hex = Hex(q=1, r=-1, s=0)  # adjacent to minion at (1,0,-1)
    totem = Token(id=token_id, name="Totem", token_type=TokenType.TOTEM)
    state.register_entity(totem)
    state.place_entity(token_id, totem_hex)
    EffectManager.create_effect(
        state=state,
        source_id=owner_id,
        effect_type=EffectType.MINION_PROTECTION,
        scope=EffectScope(
            shape=Shape.ADJACENT,
            origin_id=token_id,
            affects=AffectsFilter.FRIENDLY_UNITS,
        ),
        duration=DurationType.PASSIVE,
        is_active=True,
        sacrifice_origin_token=True,
    )
    return totem


def _drain(state, events):
    res = process_stack(state)
    events.extend(res.events)
    while res.input_request is not None:
        res = process_stack(state)
        events.extend(res.events)
    return res


def test_totem_resolves_before_brogan_and_awards_no_coins(protection_state):
    """Audit §4.2: an applicable Totem replaces the defeat first.

    Brogan is never offered, the totem is consumed, the attacker gets no coins
    and no UNIT_DEFEATED fires (the minion was not defeated).
    """
    state = protection_state
    # Brogan created FIRST — the totem must still resolve first.
    _create_protection_effect(state)
    _add_sacrifice_totem(state)
    enemy = state.get_hero("enemy")
    brogan = state.get_hero("brogan")

    events = []
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    res = process_stack(state)
    events.extend(res.events)
    assert res.input_request is None, "the totem save is mandatory — nothing to ask"

    assert state.entity_locations.get("minion_red_1") is not None  # saved
    assert state.entity_locations.get("totem_1") is None  # totem consumed
    assert enemy.gold == 0  # no coins for a totem save
    assert not any(e.event_type == GameEventType.UNIT_DEFEATED for e in events)
    assert len(brogan.hand) == 2  # never asked to discard


def test_brogan_is_considered_when_no_totem_applies(protection_state):
    """Audit §4.2: Brogan is the fallback when the Totem cannot cover the minion.

    A melee-only Totem does not apply to a ranged minion.
    """
    state = protection_state
    minion = state.get_unit("minion_red_1")
    minion.type = MinionType.RANGED
    _create_protection_effect(state)
    totem_effect_owner = _add_sacrifice_totem(state)
    assert totem_effect_owner is not None
    for effect in state.active_effects:
        if effect.sacrifice_origin_token:
            effect.protected_minion_types = [MinionType.MELEE]
    enemy = state.get_hero("enemy")
    brogan = state.get_hero("brogan")

    events = []
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    res = process_stack(state)
    events.extend(res.events)
    req = res.input_request
    assert req is not None
    assert req["type"] == "SELECT_CARD"
    assert req["player_id"] == "brogan"

    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    _drain(state, events)

    assert state.entity_locations.get("minion_red_1") is not None  # saved
    assert state.entity_locations.get("totem_1") is not None  # totem untouched
    assert enemy.gold == 2  # Brogan's save still awards the kill coins
    assert any(e.event_type == GameEventType.UNIT_DEFEATED for e in events)
    assert len(brogan.hand) == 1


def test_totem_only_saves_minion_without_coins(protection_state):
    """Totem alone (no Brogan): minion saved, totem consumed, no coins, no UNIT_DEFEATED."""
    state = protection_state
    _add_sacrifice_totem(state)
    enemy = state.get_hero("enemy")

    events = []
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    _drain(state, events)

    assert state.entity_locations.get("minion_red_1") is not None
    assert state.entity_locations.get("totem_1") is None
    assert enemy.gold == 0
    assert not any(e.event_type == GameEventType.UNIT_DEFEATED for e in events)


def test_basic_protection_saves_minion(protection_state):
    """Minion in radius defeated, Brogan discards silver, minion stays."""
    state = protection_state
    _create_protection_effect(state)

    # Verify protection effect exists
    assert any(e.effect_type == EffectType.MINION_PROTECTION for e in state.active_effects)

    # Defeat the minion
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request

    # Should get CheckMinionProtectionStep asking Brogan to discard
    assert result is not None
    assert result["type"] == "SELECT_CARD"
    assert result["player_id"] == "brogan"

    # Brogan chooses to discard silver1
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    result = process_stack(state).input_request

    # Minion should still be on the board
    assert state.entity_locations.get("minion_red_1") is not None
    # Card was discarded
    brogan = state.get_hero("brogan")
    assert len(brogan.hand) == 1
    assert brogan.hand[0].id == "silver2"


def test_card_discard_protection_routes_through_discard_step(protection_state):
    """The protection cost is a real discard, so it flows through the single
    DiscardCardStep entry point (which records discard context and fires the
    AFTER_CARD_DISCARD trigger) rather than an inline discard_card call."""
    state = protection_state
    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    process_stack(state)

    # Minion saved and the card was discarded...
    assert state.entity_locations.get("minion_red_1") is not None
    brogan = state.get_hero("brogan")
    assert all(c.id != "silver1" for c in brogan.hand)
    assert any(c.id == "silver1" for c in brogan.discard_pile)
    # ...through the unified discard path, which records the discard in context.
    assert state.execution_context.get("discarded_card_id") == "silver1"


def test_gold_awarded_even_when_protected(protection_state):
    """Enemy killer still gets gold even when minion is saved."""
    state = protection_state
    _create_protection_effect(state)

    enemy = state.get_hero("enemy")
    gold_before = enemy.gold

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    _ = process_stack(state).input_request

    # Coins are awarded by outcome — not yet, while Brogan is still deciding.
    assert enemy.gold == gold_before

    # Protect the minion (Brogan discards a qualifying card)
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request

    # Minion stays, and the enemy still gains the kill coins (Brogan III rule).
    assert state.entity_locations.get("minion_red_1") is not None
    assert enemy.gold == gold_before + 2  # MELEE minion value = 2


def test_decline_protection_removes_minion(protection_state):
    """Brogan skips → minion is removed normally."""
    state = protection_state
    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request
    assert result is not None

    # Skip protection
    state.execution_stack[-1].pending_input = {"selected_card_id": "SKIP"}
    result = process_stack(state).input_request

    # Process RemoveUnitStep
    while result is not None:
        result = process_stack(state).input_request

    assert state.entity_locations.get("minion_red_1") is None


def test_no_qualifying_cards_auto_skips(protection_state):
    """Brogan has no silver cards → no prompt, minion removed."""
    state = protection_state
    brogan = state.get_hero("brogan")
    # Replace hand with non-silver cards
    brogan.hand = [_make_card("red_card", "Red Card", "filler", color=CardColor.RED)]

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    # Process everything — no input request expected
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request

    assert state.entity_locations.get("minion_red_1") is None


def test_out_of_radius_no_protection(protection_state):
    """Minion outside radius → no protection, normal removal."""
    state = protection_state

    # Move minion far away (radius=2, move to distance 3)
    from goa2.domain.types import UnitID

    state.move_unit(UnitID("minion_red_1"), Hex(q=3, r=0, s=-3))

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request

    assert state.entity_locations.get("minion_red_1") is None


def test_fortify_accepts_gold_card(protection_state):
    """Fortify allows discarding gold OR silver cards."""
    state = protection_state
    brogan = state.get_hero("brogan")
    brogan.hand = [_make_gold_card("gold1")]

    _create_protection_effect(state, allowed_colors=[CardColor.GOLD, CardColor.SILVER])

    # Defeat minion
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request
    assert result is not None
    assert result["type"] == "SELECT_CARD"

    # Discard gold card
    state.execution_stack[-1].pending_input = {"selected_card_id": "gold1"}
    result = process_stack(state).input_request

    # Minion saved
    assert state.entity_locations.get("minion_red_1") is not None
    assert len(brogan.hand) == 0


def test_multiple_defeats_protection_triggers_multiple_times(protection_state):
    """Protection can trigger multiple times in the same round."""
    state = protection_state

    # Add a second minion
    minion2 = Minion(
        id="minion_red_2",
        name="Red Minion 2",
        team=TeamColor.RED,
        type=MinionType.MELEE,
    )
    state.teams[TeamColor.RED].minions.append(minion2)
    state.place_entity("minion_red_2", Hex(q=0, r=1, s=-1))

    _create_protection_effect(state)

    # Defeat first minion — protect it
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request
    assert result is not None
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver1"}
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request
    assert state.entity_locations.get("minion_red_1") is not None

    # Defeat second minion — protect it too
    push_steps(state, [DefeatUnitStep(victim_id="minion_red_2", killer_id="enemy")])
    result = process_stack(state).input_request
    assert result is not None
    state.execution_stack[-1].pending_input = {"selected_card_id": "silver2"}
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request
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
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request

    assert state.entity_locations.get("minion_red_1") is None


def test_shield_silver_only_rejects_gold(protection_state):
    """Shield only accepts silver — gold cards not offered."""
    state = protection_state
    brogan = state.get_hero("brogan")
    brogan.hand = [_make_gold_card("gold_only")]

    _create_protection_effect(state)

    push_steps(state, [DefeatUnitStep(victim_id="minion_red_1", killer_id="enemy")])
    result = process_stack(state).input_request
    while result is not None:
        result = process_stack(state).input_request

    # Gold card not qualifying for Shield → minion removed
    assert state.entity_locations.get("minion_red_1") is None
    # Gold card still in hand
    assert len(brogan.hand) == 1
