"""Mrak's discard-shield (Stone Carapace / Rock Solid) reaction hook.

A played card carrying an active DISCARD_SHIELD effect may be used for its
Defense reaction as if it were in hand, and is then discarded from the played
area (not the hand).
"""

from __future__ import annotations

from goa2.data.heroes.mrak import create_mrak
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import CardState
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import ReactionWindowStep


def _carapace_card():
    card = next(c for c in create_mrak().deck if c.id == "stone_carapace")
    card.state = CardState.RESOLVED
    card.is_facedown = False
    return card


def _state(with_shield: bool):
    board = Board()
    hexes = [Hex(q=q, r=0, s=-q) for q in range(3)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    mrak = Hero(id="hero_mrak", name="Mrak", team=TeamColor.RED, deck=[])
    mrak.played_cards = [_carapace_card()]
    enemy = Hero(id="hero_enemy", name="Enemy", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mrak], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
        current_actor_id="hero_enemy",
        active_zone_id="Mid",
    )
    state.place_entity("hero_mrak", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=1, r=0, s=-1))
    if with_shield:
        state.active_effects.append(
            ActiveEffect(
                id="shield_1",
                source_id="hero_mrak",
                source_card_id="stone_carapace",
                effect_type=EffectType.DISCARD_SHIELD,
                scope=EffectScope(shape=Shape.POINT, origin_id="hero_mrak"),
                duration=DurationType.THIS_ROUND,
                created_at_turn=0,
                created_at_round=0,
                is_active=True,
            )
        )
    return state


def _drive_reaction(state):
    state.execution_context["target_id"] = "hero_mrak"
    state.execution_context["attacker_id"] = "hero_enemy"
    state.execution_context["attack_damage"] = 4
    push_steps(state, [ReactionWindowStep(target_player_key="target_id")])
    return process_stack(state)


def test_active_shield_card_is_offered_as_defense_and_discarded_from_played():
    state = _state(with_shield=True)
    result = _drive_reaction(state)

    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    assert "stone_carapace" in option_ids

    state.execution_stack[-1].pending_input = {"selection": "stone_carapace"}
    process_stack(state)

    mrak = state.get_hero("hero_mrak")
    assert state.execution_context["defense_card_id"] == "stone_carapace"
    assert state.execution_context["defense_value"] == 6  # Stone Carapace Defense
    # Discarded from the played area, not left there.
    assert any(c.id == "stone_carapace" for c in mrak.discard_pile)
    assert all(c is None or c.id != "stone_carapace" for c in mrak.played_cards)


def test_played_card_without_shield_is_not_a_defense_option():
    state = _state(with_shield=False)
    result = _drive_reaction(state)

    # No hand cards, no active shield -> only PASS is offered.
    option_ids = {o.id for o in result.input_request.options}
    assert "stone_carapace" not in option_ids


def _deck_card(card_id: str):
    card = next(c for c in create_mrak().deck if c.id == card_id)
    card.state = CardState.HAND
    card.is_facedown = False
    return card


def _drive_force_discard(state):
    state.execution_context["victim"] = "hero_mrak"
    from goa2.engine.steps import ForceDiscardStep

    push_steps(state, [ForceDiscardStep(victim_key="victim")])
    return process_stack(state)


def test_forced_hand_discard_can_be_redirected_onto_the_shield_card():
    state = _state(with_shield=True)
    mrak = state.get_hero("hero_mrak")
    mrak.hand = [_deck_card("boulder_rush")]

    result = _drive_force_discard(state)
    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    assert {"boulder_rush", "stone_carapace"} <= option_ids  # both offered

    state.execution_stack[-1].pending_input = {"selection": "stone_carapace"}
    process_stack(state)

    # The shield card absorbed the discard; the hand card is spared.
    assert any(c.id == "stone_carapace" for c in mrak.discard_pile)
    assert any(c.id == "boulder_rush" for c in mrak.hand)


def test_forced_hand_discard_without_shield_only_offers_hand_cards():
    state = _state(with_shield=False)
    mrak = state.get_hero("hero_mrak")
    mrak.hand = [_deck_card("boulder_rush")]

    result = _drive_force_discard(state)
    option_ids = {o.id for o in result.input_request.options}
    assert "boulder_rush" in option_ids
    assert "stone_carapace" not in option_ids  # played card not offered without a shield


def _make_current_turn_shield(state):
    """Move the shield card from played_cards to current_turn_card (unresolved),
    as it would be during the turn it is created, before turn finalization."""
    mrak = state.get_hero("hero_mrak")
    carapace = next(c for c in mrak.played_cards if c is not None and c.id == "stone_carapace")
    mrak.played_cards = []
    carapace.state = CardState.UNRESOLVED
    mrak.current_turn_card = carapace
    return mrak


def test_forced_discard_redirected_onto_current_turn_shield_is_actually_discarded():
    """A shield that is still the current_turn_card (created this turn, not yet
    resolved into played_cards) must still be discardable via the forced-discard
    redirect. DiscardCardStep previously searched only played_cards and would
    silently no-op, letting the victim dodge the discard and keep the shield."""
    state = _state(with_shield=True)
    mrak = _make_current_turn_shield(state)
    mrak.hand = [_deck_card("boulder_rush")]

    result = _drive_force_discard(state)
    option_ids = {o.id for o in result.input_request.options}
    assert "stone_carapace" in option_ids  # offered from current_turn_card

    state.execution_stack[-1].pending_input = {"selection": "stone_carapace"}
    process_stack(state)

    # Shield was actually discarded (not a silent no-op); current_turn_card cleared.
    assert mrak.current_turn_card is None
    assert any(c.id == "stone_carapace" for c in mrak.discard_pile)
    assert any(c.id == "boulder_rush" for c in mrak.hand)  # hand card spared


def test_current_turn_card_discard_is_not_labeled_played_source():
    """An unresolved current_turn_card discarded via DiscardCardStep must not
    report discard_source=PLAYED. That signal means a *resolved* card was
    discarded (Garrus's Battle Fury gate); an unresolved current-turn card is
    not resolved."""
    from goa2.domain.models.enums import CardContainerType

    state = _state(with_shield=True)
    mrak = _make_current_turn_shield(state)
    mrak.hand = [_deck_card("boulder_rush")]

    _drive_force_discard(state)
    state.execution_stack[-1].pending_input = {"selection": "stone_carapace"}
    process_stack(state)

    assert state.execution_context.get("discard_source") != CardContainerType.PLAYED.value
    assert state.execution_context.get("discard_source") == "current_turn"


def test_defending_with_shield_removes_the_discard_shield_effect_immediately():
    """Routing the defense discard through DiscardCardStep expires the bound
    DISCARD_SHIELD effect at once (premature removal), instead of leaving an
    orphaned active effect lingering until round end."""
    state = _state(with_shield=True)
    result = _drive_reaction(state)
    assert result.input_request is not None

    state.execution_stack[-1].pending_input = {"selection": "stone_carapace"}
    process_stack(state)

    assert not any(e.effect_type == EffectType.DISCARD_SHIELD for e in state.active_effects)
