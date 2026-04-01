"""Tests for Ursafar Group A effects — simple conditionals.

Cards tested:
- Cold Ire (movement +1 if enraged)
- Eyes of Flame (movement +2 if enraged)
- Rip (attack + coin gain if enraged)
- Sniff Out (force discard if enraged)
- Eyes on the Prey (same as Sniff Out, different stats)
- Apex Predator (force discard or defeat if enraged)
"""

import pytest
import goa2.scripts.ursafar_effects  # noqa: F401 — registers effects

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.enums import TargetType
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import ResolveCardStep


# =============================================================================
# Card Factories
# =============================================================================


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id, name="Filler", tier=CardTier.UNTIERED, color=color,
        initiative=1, primary_action=ActionType.ATTACK, secondary_actions={},
        is_ranged=False, range_value=0, primary_action_value=1,
        effect_id="filler", effect_text="", is_facedown=False,
    )


def _make_cold_ire():
    return Card(
        id="cold_ire", name="Cold Ire", tier=CardTier.II, color=CardColor.BLUE,
        initiative=10, primary_action=ActionType.MOVEMENT, primary_action_value=1,
        secondary_actions={ActionType.DEFENSE: 6},
        effect_id="cold_ire", effect_text="", is_facedown=False,
    )


def _make_eyes_of_flame():
    return Card(
        id="eyes_of_flame", name="Eyes of Flame", tier=CardTier.III, color=CardColor.BLUE,
        initiative=10, primary_action=ActionType.MOVEMENT, primary_action_value=1,
        secondary_actions={ActionType.DEFENSE: 6},
        effect_id="eyes_of_flame", effect_text="", is_facedown=False,
    )


def _make_rip():
    return Card(
        id="rip", name="Rip", tier=CardTier.II, color=CardColor.RED,
        initiative=9, primary_action=ActionType.ATTACK, primary_action_value=5,
        secondary_actions={ActionType.DEFENSE: 6, ActionType.MOVEMENT: 3},
        effect_id="rip", effect_text="", is_facedown=False,
    )


def _make_sniff_out():
    return Card(
        id="sniff_out", name="Sniff Out", tier=CardTier.I, color=CardColor.GREEN,
        initiative=4, primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 2},
        is_ranged=True, range_value=2,
        effect_id="sniff_out", effect_text="", is_facedown=False,
    )


def _make_eyes_on_the_prey():
    return Card(
        id="eyes_on_the_prey", name="Eyes on the Prey", tier=CardTier.II, color=CardColor.GREEN,
        initiative=3, primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
        is_ranged=True, range_value=3,
        effect_id="eyes_on_the_prey", effect_text="", is_facedown=False,
    )


def _make_apex_predator():
    return Card(
        id="apex_predator", name="Apex Predator", tier=CardTier.III, color=CardColor.GREEN,
        initiative=3, primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 3, ActionType.MOVEMENT: 2},
        is_ranged=True, range_value=3,
        effect_id="apex_predator", effect_text="", is_facedown=False,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def board():
    b = Board()
    hexes = set()
    for q in range(-4, 5):
        for r in range(-4, 5):
            s = -q - r
            if abs(s) <= 4:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    b.zones = {"z1": z1}
    b.populate_tiles_from_zones()
    return b


@pytest.fixture
def base_state(board):
    """Ursafar at origin, enemy adjacent at (1,0,-1). NOT enraged."""
    hero = Hero(id=HeroID("hero_ursafar"), name="Ursafar", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id=HeroID("enemy"), name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    enemy.hand = [_make_filler_card("enemy_card_1"), _make_filler_card("enemy_card_2")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_ursafar", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "hero_ursafar"
    return state


def _make_enraged(state):
    """Simulate enraged by placing a played card with is_active=True."""
    hero = state.get_hero(HeroID("hero_ursafar"))
    active_card = _make_filler_card("prev_active_card", color=CardColor.SILVER)
    active_card.is_active = True
    active_card.state = CardState.RESOLVED
    hero.played_cards = [active_card]


def _drive_choose_action(state, action: str):
    """Process stack and provide CHOOSE_ACTION input."""
    req = process_resolution_stack(state)
    assert req is not None, "Expected CHOOSE_ACTION request"
    assert req["type"] == "CHOOSE_ACTION"
    state.execution_stack[-1].pending_input = {"selection": action}


def _drive_select_unit(state, unit_id: str):
    """Process stack and provide SELECT_UNIT input."""
    req = process_resolution_stack(state)
    assert req is not None, "Expected SELECT_UNIT request"
    assert req["type"] == "SELECT_UNIT"
    state.execution_stack[-1].pending_input = {"selection": unit_id}


def _drive_select_hex(state, hex_: Hex):
    """Process stack and provide SELECT_HEX input."""
    req = process_resolution_stack(state)
    assert req is not None, "Expected SELECT_HEX request"
    assert req["type"] == "SELECT_HEX"
    state.execution_stack[-1].pending_input = {"selection": hex_.model_dump()}


def _drive_reaction_pass(state):
    """Process stack and pass on reaction window."""
    req = process_resolution_stack(state)
    assert req is not None, "Expected reaction window"
    assert req["type"] == "SELECT_CARD_OR_PASS"
    state.execution_stack[-1].pending_input = {"selection": "PASS"}


def _drive_select_card(state, card_id: str):
    """Process stack and provide SELECT_CARD input."""
    req = process_resolution_stack(state)
    assert req is not None, "Expected SELECT_CARD request"
    assert req["type"] == "SELECT_CARD"
    state.execution_stack[-1].pending_input = {"selection": card_id}


def _finish(state):
    """Process stack and assert it finishes."""
    req = process_resolution_stack(state)
    assert req is None, f"Expected stack to finish but got: {req}"


# =============================================================================
# COLD IRE — Movement +1 if enraged
# =============================================================================


class TestColdIre:
    def test_not_enraged_base_movement(self, base_state):
        """Not enraged: movement = base value (1)."""
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_cold_ire()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "MOVEMENT")

        # SELECT_HEX for movement — range=1 means adjacent hexes + current
        req = process_resolution_stack(base_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        # Move to adjacent hex
        dest = Hex(q=-1, r=0, s=1)
        base_state.execution_stack[-1].pending_input = {"selection": dest.model_dump()}

        # Finish (remaining steps auto-resolve)
        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert base_state.entity_locations["hero_ursafar"] == dest

    def test_enraged_bonus_movement(self, base_state):
        """Enraged: movement = base (1) + bonus (1) = 2."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_cold_ire()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "MOVEMENT")

        # SELECT_HEX — range=2 now
        req = process_resolution_stack(base_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        # Move 2 spaces away (should be valid with range 2)
        dest = Hex(q=-2, r=0, s=2)
        base_state.execution_stack[-1].pending_input = {"selection": dest.model_dump()}

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert base_state.entity_locations["hero_ursafar"] == dest

    def test_creates_enraged_effect(self, base_state):
        """Card always creates ENRAGED effect regardless of prior state."""
        from goa2.domain.models.effect import EffectType

        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_cold_ire()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "MOVEMENT")

        # Move to adjacent
        req = process_resolution_stack(base_state)
        dest = Hex(q=-1, r=0, s=1)
        base_state.execution_stack[-1].pending_input = {"selection": dest.model_dump()}

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        enraged_effects = [
            e for e in base_state.active_effects if e.effect_type == EffectType.ENRAGED
        ]
        assert len(enraged_effects) == 1
        assert enraged_effects[0].source_id == "hero_ursafar"


# =============================================================================
# EYES OF FLAME — Movement +2 if enraged
# =============================================================================


class TestEyesOfFlame:
    def test_not_enraged_base_movement(self, base_state):
        """Not enraged: movement = base value (1)."""
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_eyes_of_flame()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "MOVEMENT")

        req = process_resolution_stack(base_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        dest = Hex(q=-1, r=0, s=1)
        base_state.execution_stack[-1].pending_input = {"selection": dest.model_dump()}

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert base_state.entity_locations["hero_ursafar"] == dest

    def test_enraged_bonus_movement(self, base_state):
        """Enraged: movement = base (1) + bonus (2) = 3."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_eyes_of_flame()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "MOVEMENT")

        req = process_resolution_stack(base_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        # Move 3 spaces away
        dest = Hex(q=-3, r=0, s=3)
        base_state.execution_stack[-1].pending_input = {"selection": dest.model_dump()}

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert base_state.entity_locations["hero_ursafar"] == dest


# =============================================================================
# RIP — Attack adjacent + coin gain if enraged
# =============================================================================


class TestRip:
    def test_attack_not_enraged_no_bonus_coins(self, base_state):
        """Not enraged: attack resolves, no bonus coin (only defeat gold)."""
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_rip()
        assert hero.gold == 0

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "ATTACK")
        _drive_select_unit(base_state, "enemy")
        _drive_reaction_pass(base_state)

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        # 1 gold from defeating enemy, 0 from Rip effect (not enraged)
        assert hero.gold == 1

    def test_attack_enraged_gains_bonus_coin(self, base_state):
        """Enraged: attack resolves, gains 1 bonus coin on top of defeat gold."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_rip()
        assert hero.gold == 0

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "ATTACK")
        _drive_select_unit(base_state, "enemy")
        _drive_reaction_pass(base_state)

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        # 1 gold from defeating enemy + 1 from Rip effect (enraged)
        assert hero.gold == 2

    def test_creates_enraged_effect(self, base_state):
        """Attack always creates ENRAGED effect."""
        from goa2.domain.models.effect import EffectType

        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_rip()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "ATTACK")
        _drive_select_unit(base_state, "enemy")
        _drive_reaction_pass(base_state)

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        enraged_effects = [
            e for e in base_state.active_effects if e.effect_type == EffectType.ENRAGED
        ]
        assert len(enraged_effects) == 1


# =============================================================================
# SNIFF OUT — Force discard if enraged
# =============================================================================


class TestSniffOut:
    def test_not_enraged_does_nothing(self, base_state):
        """Not enraged: no steps, skill resolves immediately."""
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_sniff_out()
        enemy = base_state.get_hero(HeroID("enemy"))
        hand_size_before = len(enemy.hand)

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert len(enemy.hand) == hand_size_before

    def test_enraged_forces_discard(self, base_state):
        """Enraged: selects enemy hero in range, forces discard."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_sniff_out()
        enemy = base_state.get_hero(HeroID("enemy"))
        hand_size_before = len(enemy.hand)

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")

        # SELECT_UNIT — pick enemy hero
        _drive_select_unit(base_state, "enemy")

        # ForceDiscardStep — enemy selects card to discard
        _drive_select_card(base_state, "enemy_card_1")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert len(enemy.hand) == hand_size_before - 1
        assert any(c.id == "enemy_card_1" for c in enemy.discard_pile)

    def test_no_enraged_effect_created(self, base_state):
        """Green cards never create ENRAGED effect."""
        from goa2.domain.models.effect import EffectType

        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_sniff_out()

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")
        _drive_select_unit(base_state, "enemy")
        _drive_select_card(base_state, "enemy_card_1")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        enraged_effects = [
            e for e in base_state.active_effects if e.effect_type == EffectType.ENRAGED
        ]
        assert len(enraged_effects) == 0

    def test_enemy_out_of_range_no_target(self, base_state):
        """Enraged but enemy out of range (>2): mandatory select fails, aborts."""
        from goa2.domain.types import UnitID

        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_sniff_out()

        # Move enemy out of range (range=2, put at distance 3)
        base_state.move_unit(UnitID("enemy"), Hex(q=3, r=0, s=-3))

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")

        # Should abort since mandatory select has no valid targets
        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        enemy = base_state.get_hero(HeroID("enemy"))
        assert len(enemy.hand) == 2  # No discard happened


# =============================================================================
# EYES ON THE PREY — Same as Sniff Out (inherits), different range
# =============================================================================


class TestEyesOnThePrey:
    def test_enraged_forces_discard_at_range_3(self, base_state):
        """Enraged: enemy hero at range 3 is valid target (range=3)."""
        from goa2.domain.types import UnitID

        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_eyes_on_the_prey()

        # Move enemy to distance 3 (within range for Eyes on the Prey)
        base_state.move_unit(UnitID("enemy"), Hex(q=3, r=0, s=-3))

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")
        _drive_select_unit(base_state, "enemy")
        _drive_select_card(base_state, "enemy_card_1")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        enemy = base_state.get_hero(HeroID("enemy"))
        assert len(enemy.hand) == 1


# =============================================================================
# APEX PREDATOR — Force discard or defeat if enraged
# =============================================================================


class TestApexPredator:
    def test_not_enraged_does_nothing(self, base_state):
        """Not enraged: no steps."""
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_apex_predator()
        enemy = base_state.get_hero(HeroID("enemy"))

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert len(enemy.hand) == 2

    def test_enraged_forces_discard_when_has_cards(self, base_state):
        """Enraged + enemy has cards: forces discard (not defeat)."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_apex_predator()
        enemy = base_state.get_hero(HeroID("enemy"))

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")
        _drive_select_unit(base_state, "enemy")

        # ForceDiscardOrDefeatStep — enemy has cards, so they discard
        _drive_select_card(base_state, "enemy_card_1")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        assert len(enemy.hand) == 1
        assert any(c.id == "enemy_card_1" for c in enemy.discard_pile)

    def test_enraged_defeats_when_no_cards(self, base_state):
        """Enraged + enemy has no cards: defeats enemy."""
        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        hero.current_turn_card = _make_apex_predator()
        enemy = base_state.get_hero(HeroID("enemy"))
        enemy.hand = []  # No cards to discard

        push_steps(base_state, [ResolveCardStep(hero_id="hero_ursafar")])
        _drive_choose_action(base_state, "SKILL")
        _drive_select_unit(base_state, "enemy")

        result = process_resolution_stack(base_state)
        while result is not None:
            result = process_resolution_stack(base_state)

        # Enemy should be defeated (removed from board)
        assert base_state.entity_locations.get("enemy") is None


# =============================================================================
# ENRAGED OVERRIDE (Ultimate)
# =============================================================================


class TestEnragedActiveOverride:
    def test_override_keeps_is_active_true(self):
        """enraged_active_override prevents is_active from being set to False for resolved cards."""
        card = _make_filler_card()
        card.state = CardState.RESOLVED
        card.enraged_active_override = True

        card.is_active = False  # EffectManager would do this
        assert card.is_active is True

    def test_override_on_card_with_no_effect(self):
        """Resolved cards with override still show is_active=True."""
        card = _make_filler_card()
        assert card.is_active is False

        card.state = CardState.RESOLVED
        card.enraged_active_override = True
        assert card.is_active is True
        assert card.is_active_base is False  # raw value unchanged

    def test_override_requires_resolved_state(self):
        """enraged_active_override only works on RESOLVED cards."""
        card = _make_filler_card()
        card.enraged_active_override = True

        # DECK state — override doesn't apply
        assert card.state == CardState.DECK
        assert card.is_active is False

        # RESOLVED state — override applies
        card.state = CardState.RESOLVED
        assert card.is_active is True


# =============================================================================
# is_enraged helper
# =============================================================================


class TestIsEnraged:
    def test_not_enraged_no_active_cards(self, base_state):
        from goa2.scripts.ursafar_effects import is_enraged

        hero = base_state.get_hero(HeroID("hero_ursafar"))
        card = _make_cold_ire()
        assert is_enraged(hero, card) is False

    def test_enraged_via_active_played_card(self, base_state):
        from goa2.scripts.ursafar_effects import is_enraged

        _make_enraged(base_state)
        hero = base_state.get_hero(HeroID("hero_ursafar"))
        card = _make_cold_ire()
        assert is_enraged(hero, card) is True

    def test_enraged_via_ultimate(self, base_state):
        from goa2.scripts.ursafar_effects import is_enraged

        hero = base_state.get_hero(HeroID("hero_ursafar"))
        ultimate = Card(
            id="unbound_fury", name="Unbound Fury", tier=CardTier.IV,
            color=CardColor.PURPLE, initiative=0, primary_action=ActionType.SKILL,
            secondary_actions={}, effect_id="unbound_fury", effect_text="",
        )
        ultimate.state = CardState.PASSIVE
        hero.ultimate_card = ultimate
        hero.level = 8

        card = _make_cold_ire()
        assert is_enraged(hero, card) is True

    def test_current_card_active_counts(self, base_state):
        """A card's own is_active counts for is_enraged check."""
        from goa2.scripts.ursafar_effects import is_enraged

        hero = base_state.get_hero(HeroID("hero_ursafar"))
        card = _make_cold_ire()
        card.is_active = True
        card.state = CardState.RESOLVED
        hero.played_cards = [card]

        # The current card being active counts as enraged
        assert is_enraged(hero, card) is True
