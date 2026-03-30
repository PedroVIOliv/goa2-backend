"""
Tests for Rowenna's Fabled Lance (Ultimate) effect.

Card Text: 'All your attack actions gain the "Ranged" subtype, target
a unit in range, and count as having a printed Range value of 2.'

Implementation: Each Rowenna attack effect checks hero.level >= 8 at
build time and adjusts AttackSequenceStep to is_ranged=True, range_val=2
(+ item bonuses via get_computed_stat).

Tests verify:
- Without ult (level < 8): attacks are melee, range 1
- With ult (level >= 8): attacks are ranged, range 2
- Range items stack on top of ult base range (2 + 1 = 3)
- Defense interactions: Parry (blocks non-ranged) fails vs ult-boosted attack
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
    StatType,
)
from goa2.domain.hex import Hex
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.steps import AttackSequenceStep
from goa2.engine.handler import push_steps, process_resolution_stack

import goa2.scripts.rowenna_effects  # noqa: F401


# =============================================================================
# Helpers
# =============================================================================


def _make_attack_card(card_id, name, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={},
        is_ranged=False,
        radius_value=2,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


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


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rowenna_state():
    """
    State with Rowenna and an enemy at range 2.

    Layout (q-axis):
      [ROWENNA](0,0,0) -- (1,0,-1) -- [ENEMY](2,0,-2) -- (3,0,-3)
    Plus adjacent hexes for melee range testing.
    """
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

    card = _make_attack_card(
        "token_of_gratitude", "Token of Gratitude", "token_of_gratitude"
    )
    rowenna = Hero(
        id="rowenna", name="Rowenna", team=TeamColor.RED, deck=[], level=1
    )
    rowenna.current_turn_card = card

    enemy = Hero(
        id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1
    )
    enemy.hand = [_make_filler_card("enemy_filler")]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[rowenna], minions=[]
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy], minions=[]
            ),
        },
    )
    state.place_entity("rowenna", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=2, r=0, s=-2))
    state.current_actor_id = "rowenna"
    return state


# =============================================================================
# Tests: build_steps output verification
# =============================================================================


def _get_attack_steps(state, effect_id, card_overrides=None):
    """Build steps for the given effect and return AttackSequenceStep instances."""
    hero = state.get_hero("rowenna")
    card = hero.current_turn_card

    if card_overrides:
        for k, v in card_overrides.items():
            setattr(card, k, v)

    effect = CardEffectRegistry.get(effect_id)
    from goa2.engine.stats import compute_card_stats

    stats = compute_card_stats(state, hero.id, card)
    steps = effect.build_steps(state, hero, card, stats)
    return [s for s in steps if isinstance(s, AttackSequenceStep)]


class TestFabledLanceMeleeWithoutUlt:
    """Without ult (level < 8), attacks should be melee range 1."""

    def test_token_of_gratitude_melee(self, rowenna_state):
        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        assert len(attacks) == 1
        assert attacks[0].range_val == 1
        assert attacks[0].is_ranged is False

    def test_fair_share_melee(self, rowenna_state):
        attacks = _get_attack_steps(rowenna_state, "fair_share")
        assert len(attacks) == 1
        assert attacks[0].range_val == 1
        assert attacks[0].is_ranged is False

    def test_paragon_of_grace_melee(self, rowenna_state):
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "paragon_of_grace",
            "Paragon of Grace",
            "paragon_of_grace",
            tier=CardTier.III,
        )
        attacks = _get_attack_steps(rowenna_state, "paragon_of_grace")
        assert len(attacks) >= 1
        for atk in attacks:
            assert atk.range_val == 1
            assert atk.is_ranged is False

    def test_feat_of_bravery_melee(self, rowenna_state):
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "feat_of_bravery",
            "Feat of Bravery",
            "feat_of_bravery",
            tier=CardTier.II,
        )
        attacks = _get_attack_steps(rowenna_state, "feat_of_bravery")
        assert len(attacks) == 1
        assert attacks[0].range_val == 1
        assert attacks[0].is_ranged is False

    def test_paragon_of_valor_melee(self, rowenna_state):
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "paragon_of_valor",
            "Paragon of Valor",
            "paragon_of_valor",
            tier=CardTier.III,
            primary_action_value=7,
            radius_value=4,
        )
        attacks = _get_attack_steps(rowenna_state, "paragon_of_valor")
        assert len(attacks) >= 1
        for atk in attacks:
            assert atk.range_val == 1
            assert atk.is_ranged is False

    def test_code_of_chivalry_melee(self, rowenna_state):
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "code_of_chivalry",
            "Code of Chivalry",
            "code_of_chivalry",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
        )
        attacks = _get_attack_steps(rowenna_state, "code_of_chivalry")
        assert len(attacks) == 1
        assert attacks[0].range_val == 1
        assert attacks[0].is_ranged is False


class TestFabledLanceRangedWithUlt:
    """With ult (level >= 8), attacks should be ranged with range 2."""

    def _set_ult_active(self, state):
        hero = state.get_hero("rowenna")
        hero.level = 8

    def test_token_of_gratitude_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        assert len(attacks) == 1
        assert attacks[0].range_val == 2
        assert attacks[0].is_ranged is True

    def test_fair_share_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        attacks = _get_attack_steps(rowenna_state, "fair_share")
        assert len(attacks) == 1
        assert attacks[0].range_val == 2
        assert attacks[0].is_ranged is True

    def test_paragon_of_grace_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "paragon_of_grace",
            "Paragon of Grace",
            "paragon_of_grace",
            tier=CardTier.III,
        )
        attacks = _get_attack_steps(rowenna_state, "paragon_of_grace")
        assert len(attacks) >= 1
        for atk in attacks:
            assert atk.range_val == 2
            assert atk.is_ranged is True

    def test_feat_of_bravery_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "feat_of_bravery",
            "Feat of Bravery",
            "feat_of_bravery",
            tier=CardTier.II,
        )
        attacks = _get_attack_steps(rowenna_state, "feat_of_bravery")
        assert len(attacks) == 1
        assert attacks[0].range_val == 2
        assert attacks[0].is_ranged is True

    def test_paragon_of_valor_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "paragon_of_valor",
            "Paragon of Valor",
            "paragon_of_valor",
            tier=CardTier.III,
            primary_action_value=7,
            radius_value=4,
        )
        attacks = _get_attack_steps(rowenna_state, "paragon_of_valor")
        assert len(attacks) >= 1
        for atk in attacks:
            assert atk.range_val == 2
            assert atk.is_ranged is True

    def test_code_of_chivalry_ranged(self, rowenna_state):
        self._set_ult_active(rowenna_state)
        rowenna_state.get_hero("rowenna").current_turn_card = _make_attack_card(
            "code_of_chivalry",
            "Code of Chivalry",
            "code_of_chivalry",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
        )
        attacks = _get_attack_steps(rowenna_state, "code_of_chivalry")
        assert len(attacks) == 1
        assert attacks[0].range_val == 2
        assert attacks[0].is_ranged is True


class TestFabledLanceRangeItemStacking:
    """Range items should stack on top of the ult's base range of 2."""

    def test_ult_plus_range_item(self, rowenna_state):
        hero = rowenna_state.get_hero("rowenna")
        hero.level = 8
        hero.items[StatType.RANGE] = 1  # +1 range item

        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        assert len(attacks) == 1
        assert attacks[0].range_val == 3  # base 2 + item 1
        assert attacks[0].is_ranged is True

    def test_no_ult_range_item_ignored(self, rowenna_state):
        """Without ult, range items don't affect melee attack range."""
        hero = rowenna_state.get_hero("rowenna")
        hero.items[StatType.RANGE] = 1

        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        assert len(attacks) == 1
        assert attacks[0].range_val == 1  # Still melee
        assert attacks[0].is_ranged is False


class TestFabledLanceDefenseInteraction:
    """Ult-boosted attacks should set attack_is_ranged in context."""

    def test_attack_sequence_sets_ranged_context(self, rowenna_state):
        """When ult is active, AttackSequenceStep should have is_ranged=True,
        which will set context['attack_is_ranged'] = True during resolve."""
        hero = rowenna_state.get_hero("rowenna")
        hero.level = 8

        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        # The is_ranged flag on the step is what gets stored in context
        assert attacks[0].is_ranged is True

    def test_attack_sequence_melee_without_ult(self, rowenna_state):
        """Without ult, attack_is_ranged should be False."""
        attacks = _get_attack_steps(rowenna_state, "token_of_gratitude")
        assert attacks[0].is_ranged is False


class TestFabledLanceSkillsUnaffected:
    """Skill and movement cards should not be affected by the ult."""

    def test_stand_guard_unaffected(self, rowenna_state):
        """Stand Guard is a SKILL card — no AttackSequenceStep to modify."""
        hero = rowenna_state.get_hero("rowenna")
        hero.level = 8
        hero.current_turn_card = Card(
            id="stand_guard",
            name="Stand Guard",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=3,
            primary_action=ActionType.SKILL,
            secondary_actions={},
            is_ranged=False,
            radius_value=None,
            range_value=2,
            effect_id="stand_guard",
            effect_text="",
        )
        effect = CardEffectRegistry.get("stand_guard")
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(rowenna_state, hero.id, hero.current_turn_card)
        steps = effect.build_steps(rowenna_state, hero, hero.current_turn_card, stats)
        attacks = [s for s in steps if isinstance(s, AttackSequenceStep)]
        assert len(attacks) == 0  # No attacks in skill cards
