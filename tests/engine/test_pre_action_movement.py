"""
Tests for PRE_ACTION_MOVEMENT effect resolution (Misa's green cards).

Covers:
- ResolvePreActionMovementStep spawns SelectStep + MoveUnitStep
- No effect -> step is a no-op
- Effect persists (not consumed; removed by normal expiry at end of turn)
- Works via ResolveCardStep offense path (primary action)
- Works via AttackSequenceStep defense path (primary defense)
"""

import pytest
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
from goa2.domain.models.effect import (
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
    ActiveEffect,
)
from goa2.engine.steps import (
    ResolvePreActionMovementStep,
    ResolveCardStep,
    MoveUnitStep,
    AttackSequenceStep,
    SelectStep,
)
from goa2.engine.handler import process_resolution_stack, push_steps

import goa2.scripts.misa_effects  # noqa: F401
import goa2.scripts.tigerclaw_effects  # noqa: F401


def _make_board():
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
    return board


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
        color=color,
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


def _add_pre_action_effect(state, hero_id, move_distance, is_active=True):
    effect = ActiveEffect(
        id="pam_effect",
        source_id=hero_id,
        effect_type=EffectType.PRE_ACTION_MOVEMENT,
        scope=EffectScope(
            shape=Shape.POINT,
            origin_id=hero_id,
            affects=AffectsFilter.SELF,
        ),
        duration=DurationType.NEXT_TURN,
        max_value=move_distance,
        is_active=is_active,
        created_at_turn=state.turn,
        created_at_round=state.round,
    )
    state.active_effects.append(effect)
    return effect


@pytest.fixture
def basic_state():
    board = _make_board()
    hero = Hero(id="hero_misa", name="Misa", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    enemy.hand = [_make_filler_card("enemy_card")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
        turn=2,
        round=1,
    )
    state.place_entity("hero_misa", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=3, r=0, s=-3))
    state.current_actor_id = "hero_misa"
    return state


class TestResolvePreActionMovementStepDirect:
    def test_no_effect_is_noop(self, basic_state):
        step = ResolvePreActionMovementStep(hero_id="hero_misa")
        result = step.resolve(basic_state, {})
        assert result.is_finished is True
        assert result.new_steps == []

    def test_inactive_effect_is_noop(self, basic_state):
        _add_pre_action_effect(basic_state, "hero_misa", 2, is_active=False)
        step = ResolvePreActionMovementStep(hero_id="hero_misa")
        result = step.resolve(basic_state, {})
        assert result.is_finished is True
        assert result.new_steps == []

    def test_effect_persists_after_use(self, basic_state):
        _add_pre_action_effect(basic_state, "hero_misa", 2)
        step = ResolvePreActionMovementStep(hero_id="hero_misa")
        step.resolve(basic_state, {})
        assert any(
            e.effect_type == EffectType.PRE_ACTION_MOVEMENT
            for e in basic_state.active_effects
        )

    def test_spawns_select_and_move(self, basic_state):
        _add_pre_action_effect(basic_state, "hero_misa", 2)
        step = ResolvePreActionMovementStep(hero_id="hero_misa")
        result = step.resolve(basic_state, {})

        assert len(result.new_steps) == 2
        select_step = result.new_steps[0]
        move_step = result.new_steps[1]

        assert isinstance(select_step, SelectStep)
        assert select_step.is_mandatory is False
        assert select_step.output_key == "pre_action_move_hex"

        assert isinstance(move_step, MoveUnitStep)
        assert move_step.unit_id == "hero_misa"
        assert move_step.range_val == 2
        assert move_step.is_mandatory is False
        assert move_step.is_movement_action is False

    def test_hero_key_from_context(self, basic_state):
        _add_pre_action_effect(basic_state, "hero_misa", 3)
        step = ResolvePreActionMovementStep(hero_key="some_hero")
        result = step.resolve(basic_state, {"some_hero": "hero_misa"})

        assert len(result.new_steps) == 2
        move_step = result.new_steps[1]
        assert move_step.range_val == 3

    def test_range_1(self, basic_state):
        _add_pre_action_effect(basic_state, "hero_misa", 1)
        step = ResolvePreActionMovementStep(hero_id="hero_misa")
        result = step.resolve(basic_state, {})
        move_step = result.new_steps[1]
        assert move_step.range_val == 1


class TestPreActionMovementViaOffense:
    def _make_attack_card(self):
        return Card(
            id="attack_card",
            name="Test Attack",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=5,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            secondary_actions={},
            is_ranged=False,
            range_value=1,
            effect_id="hit_and_run",
            effect_text="Target a unit adjacent to you.",
            is_facedown=False,
        )

    def test_pre_action_move_before_card_text(self, basic_state):
        card = self._make_attack_card()
        hero = basic_state.get_hero("hero_misa")
        hero.current_turn_card = card
        hero.played_cards = [card]

        _add_pre_action_effect(basic_state, "hero_misa", 1)
        basic_state.place_entity("enemy", Hex(q=1, r=0, s=-1))

        push_steps(basic_state, [ResolveCardStep(hero_id="hero_misa")])

        req = process_resolution_stack(basic_state)
        assert req["type"] == "CHOOSE_ACTION"

        basic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_HEX"

        basic_state.execution_stack[-1].pending_input = {
            "selection": {"q": 1, "r": -1, "s": 0}
        }

        process_resolution_stack(basic_state)

        assert basic_state.entity_locations.get("hero_misa") == Hex(q=1, r=-1, s=0)
        assert any(
            e.effect_type == EffectType.PRE_ACTION_MOVEMENT
            for e in basic_state.active_effects
        )

    def test_no_effect_skips_move(self, basic_state):
        card = self._make_attack_card()
        hero = basic_state.get_hero("hero_misa")
        hero.current_turn_card = card
        hero.played_cards = [card]
        basic_state.place_entity("enemy", Hex(q=1, r=0, s=-1))

        push_steps(basic_state, [ResolveCardStep(hero_id="hero_misa")])

        req = process_resolution_stack(basic_state)
        assert req["type"] == "CHOOSE_ACTION"

        basic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_UNIT"

    def test_skip_pre_action_move(self, basic_state):
        card = self._make_attack_card()
        hero = basic_state.get_hero("hero_misa")
        hero.current_turn_card = card
        hero.played_cards = [card]

        _add_pre_action_effect(basic_state, "hero_misa", 1)
        basic_state.place_entity("enemy", Hex(q=1, r=0, s=-1))

        push_steps(basic_state, [ResolveCardStep(hero_id="hero_misa")])

        req = process_resolution_stack(basic_state)
        assert req["type"] == "CHOOSE_ACTION"

        basic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_HEX"

        basic_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_UNIT"

        assert basic_state.entity_locations.get("hero_misa") == Hex(q=0, r=0, s=0)


class TestPreActionMovementViaDefense:
    def test_pre_action_move_before_defense_text(self, basic_state):
        enemy = basic_state.get_hero("enemy")
        defender_card = Card(
            id="def_card",
            name="Block",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=ActionType.DEFENSE,
            primary_action_value=3,
            secondary_actions={ActionType.MOVEMENT: 3},
            effect_id="filler",
            effect_text="Block.",
            is_facedown=False,
        )
        enemy.hand = [defender_card]

        _add_pre_action_effect(basic_state, "enemy", 2)

        basic_state.current_actor_id = "hero_misa"
        basic_state.place_entity("enemy", Hex(q=1, r=0, s=-1))

        push_steps(
            basic_state,
            [
                AttackSequenceStep(
                    damage=3,
                    range_val=3,
                    target_id_key="victim",
                )
            ],
        )

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_UNIT"

        basic_state.execution_stack[-1].pending_input = {"selection": "enemy"}

        req = process_resolution_stack(basic_state)
        assert req["type"] == "SELECT_CARD_OR_PASS"

        basic_state.execution_stack[-1].pending_input = {"selection": defender_card.id}

        req = process_resolution_stack(basic_state)
        assert req is not None
        assert req["type"] == "SELECT_HEX"

        basic_state.execution_stack[-1].pending_input = {
            "selection": {"q": 2, "r": 0, "s": -2}
        }

        process_resolution_stack(basic_state)

        assert basic_state.entity_locations.get("enemy") == Hex(q=2, r=0, s=-2)
        assert any(
            e.effect_type == EffectType.PRE_ACTION_MOVEMENT
            for e in basic_state.active_effects
        )
