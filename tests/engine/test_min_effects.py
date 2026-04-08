"""Tests for Min's card effects: defense cards, inner_strength, perfect_self, flurry_of_blows."""

import pytest

import goa2.scripts.min_effects  # noqa: F401

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    Card,
    Hero,
    Unit,
    Team,
)
from goa2.domain.models.enums import (
    CardState,
    StatType,
    TokenType,
    CardColor,
    CardTier,
    ActionType,
    TeamColor,
)
from goa2.domain.models.effect import EffectType
from goa2.domain.models.token import Token
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import ResolveCardStep
from goa2.domain.models.enums import StepType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_board():
    board = Board()
    hexes = set()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()
    return board


def _make_min_defense_card(card_id, effect_id, range_value=3):
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=2,
        primary_action=ActionType.DEFENSE,
        primary_action_value=None,
        secondary_actions={ActionType.MOVEMENT: 3},
        is_ranged=True,
        range_value=range_value,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


def _make_attack_card(card_id, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 5},
        is_ranged=False,
        range_value=0,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_skill_card(card_id, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=card_id,
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=2,
        primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 2, ActionType.MOVEMENT: 3},
        is_ranged=False,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _place_smoke_bomb(state, hex_coord, owner_id="hero_min"):
    """Place a smoke bomb token on the board and return its ID."""
    token = Token(
        id="smoke_bomb_1",
        name="Smoke Bomb",
        token_type=TokenType.SMOKE_BOMB,
        owner_id=HeroID(owner_id),
    )
    state.token_pool.setdefault(TokenType.SMOKE_BOMB, []).append(token)
    state.place_entity("smoke_bomb_1", hex_coord)
    return "smoke_bomb_1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def defense_state():
    """State with Min as defender being attacked by an enemy."""
    board = _make_board()

    poof_card = _make_min_defense_card("poof", "poof", range_value=3)
    vanish_card = _make_min_defense_card("vanish", "vanish", range_value=4)
    ruse_card = _make_min_defense_card("ruse", "ruse", range_value=4)

    hero = Hero(
        id=HeroID("hero_min"),
        name="Min",
        team=TeamColor.RED,
        deck=[],
        hand=[poof_card, vanish_card, ruse_card],
        level=1,
    )
    enemy = Hero(
        id=HeroID("enemy"),
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        hand=[_make_filler_card("enemy_card")],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_min", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "enemy"
    return state


# ===========================================================================
# 1. Smoke Bomb Defense Bug Fix
# ===========================================================================


class TestSmokeBombDefenseInvalid:
    """Defense cards return defense_invalid when no smoke bomb is in range."""

    def test_poof_defense_invalid_no_smoke_bomb(self, defense_state):
        """Poof should set defense_invalid when no smoke bomb exists."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[0]  # poof
        effect = CardEffectRegistry.get("poof")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        assert len(steps) == 6
        assert steps[0].type == StepType.COUNT
        assert steps[1].type == StepType.CHECK_CONTEXT_CONDITION
        assert steps[1].output_key == "has_smoke_bomb"
        assert steps[2].output_key == "defense_invalid"
        assert steps[3].active_if_key == "has_smoke_bomb"

    def test_vanish_defense_invalid_no_smoke_bomb(self, defense_state):
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[1]  # vanish
        effect = CardEffectRegistry.get("vanish")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        assert len(steps) == 6
        assert steps[0].type == StepType.COUNT
        assert steps[1].type == StepType.CHECK_CONTEXT_CONDITION

    def test_ruse_defense_invalid_no_smoke_bomb(self, defense_state):
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[2]  # ruse
        effect = CardEffectRegistry.get("ruse")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        assert (
            len(steps) == 8
        )  # CountStep + 2x CheckContextCondition + 5 conditional steps
        assert steps[0].type == StepType.COUNT

    def test_poof_defense_valid_with_smoke_bomb_in_range(self, defense_state):
        """Poof should produce swap steps when smoke bomb exists in range."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        _place_smoke_bomb(defense_state, Hex(q=2, r=0, s=-2))

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[0]  # poof (range 3)
        effect = CardEffectRegistry.get("poof")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        # CountStep + 2x CheckContextCondition + SelectStep + SwapUnitsStep + SetContextFlagStep
        assert len(steps) == 6
        assert steps[0].type == StepType.COUNT
        assert steps[1].type == StepType.CHECK_CONTEXT_CONDITION
        assert steps[1].output_key == "has_smoke_bomb"
        assert steps[2].output_key == "defense_invalid"
        assert steps[3].active_if_key == "has_smoke_bomb"
        assert steps[3].is_mandatory is True  # select is mandatory when active
        assert steps[4].active_if_key == "has_smoke_bomb"
        assert steps[5].key == "auto_block"
        assert steps[5].active_if_key == "has_smoke_bomb"

    def test_poof_defense_invalid_smoke_bomb_out_of_range(self, defense_state):
        """Poof range=3, smoke bomb at distance 4 → defense_invalid."""
        _place_smoke_bomb(defense_state, Hex(q=4, r=0, s=-4))

        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[0]  # poof (range 3)
        effect = CardEffectRegistry.get("poof")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        # CountStep + 2x CheckContextCondition + SelectStep + SwapUnitsStep + SetContextFlagStep
        assert len(steps) == 6
        assert steps[0].type == StepType.COUNT
        assert steps[1].type == StepType.CHECK_CONTEXT_CONDITION
        assert steps[1].output_key == "has_smoke_bomb"
        assert steps[2].output_key == "defense_invalid"
        # Conditional steps have active_if_key = "has_smoke_bomb" but won't run since count is 0

    def test_ruse_valid_has_replacement_steps(self, defense_state):
        """Ruse with smoke bomb in range should include replacement placement steps."""
        _place_smoke_bomb(defense_state, Hex(q=2, r=0, s=-2))

        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = defense_state.get_hero(HeroID("hero_min"))
        card = hero.hand[2]  # ruse (range 4)
        effect = CardEffectRegistry.get("ruse")
        stats = compute_card_stats(defense_state, hero.id, card)
        context = {
            "attack_is_ranged": False,
            "attacker_id": "enemy",
            "defender_id": "hero_min",
        }

        steps = effect.build_defense_steps(defense_state, hero, card, stats, context)
        # CountStep + 2x CheckContextCondition + Select + Swap + auto_block + SelectHex + PlaceToken = 8
        assert len(steps) == 8
        assert steps[0].type == StepType.COUNT
        assert steps[1].type == StepType.CHECK_CONTEXT_CONDITION


# ===========================================================================
# 2. Inner Strength
# ===========================================================================


@pytest.fixture
def inner_strength_state():
    board = _make_board()

    card = _make_skill_card("inner_strength", "inner_strength")
    hero = Hero(
        id=HeroID("hero_min"),
        name="Min",
        team=TeamColor.RED,
        deck=[],
        hand=[card],
        level=1,
        items={StatType.ATTACK: 2, StatType.DEFENSE: 1},
    )
    enemy = Hero(
        id=HeroID("enemy"),
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        hand=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_min", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=2, r=0, s=-2))
    state.current_actor_id = "hero_min"
    return state


class TestInnerStrength:
    def test_creates_double_items_effect(self, inner_strength_state):
        """Inner Strength should create a DOUBLE_ITEMS effect."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = inner_strength_state.get_hero(HeroID("hero_min"))
        card = hero.hand[0]
        effect = CardEffectRegistry.get("inner_strength")
        stats = compute_card_stats(inner_strength_state, hero.id, card)

        steps = effect.build_steps(inner_strength_state, hero, card, stats)
        assert len(steps) == 1
        assert steps[0].effect_type == EffectType.DOUBLE_ITEMS

    def test_double_items_effect_doubles_item_bonuses(self, inner_strength_state):
        """DOUBLE_ITEMS effect should double item bonuses in stat computation."""
        from goa2.engine.effect_manager import EffectManager
        from goa2.domain.models.effect import EffectScope, Shape, DurationType
        from goa2.engine.stats import get_computed_stat

        state = inner_strength_state
        hero = state.get_hero(HeroID("hero_min"))

        # Before effect: items give +2 attack, +1 defense
        assert (
            get_computed_stat(state, hero.id, StatType.ATTACK, 3) == 5
        )  # 3 base + 2 item
        assert (
            get_computed_stat(state, hero.id, StatType.DEFENSE, 2) == 3
        )  # 2 base + 1 item

        # Create DOUBLE_ITEMS effect
        EffectManager.create_effect(
            state=state,
            source_id="hero_min",
            effect_type=EffectType.DOUBLE_ITEMS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            is_active=True,
        )

        # After effect: items doubled
        assert (
            get_computed_stat(state, hero.id, StatType.ATTACK, 3) == 7
        )  # 3 base + 4 item
        assert (
            get_computed_stat(state, hero.id, StatType.DEFENSE, 2) == 4
        )  # 2 base + 2 item

    def test_double_items_does_not_affect_enemy(self, inner_strength_state):
        """DOUBLE_ITEMS only affects the source hero, not enemies."""
        from goa2.engine.effect_manager import EffectManager
        from goa2.domain.models.effect import EffectScope, Shape, DurationType
        from goa2.engine.stats import get_computed_stat

        state = inner_strength_state
        enemy = state.get_hero(HeroID("enemy"))
        enemy.items = {StatType.ATTACK: 1}

        EffectManager.create_effect(
            state=state,
            source_id="hero_min",
            effect_type=EffectType.DOUBLE_ITEMS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            is_active=True,
        )

        # Enemy's items should NOT be doubled
        assert (
            get_computed_stat(state, enemy.id, StatType.ATTACK, 3) == 4
        )  # 3 + 1 (not doubled)

    def test_double_items_no_effect_when_no_items(self, inner_strength_state):
        """DOUBLE_ITEMS has no effect when hero has 0 items for that stat."""
        from goa2.engine.effect_manager import EffectManager
        from goa2.domain.models.effect import EffectScope, Shape, DurationType
        from goa2.engine.stats import get_computed_stat

        state = inner_strength_state
        hero = state.get_hero(HeroID("hero_min"))
        hero.items = {}  # No items

        EffectManager.create_effect(
            state=state,
            source_id="hero_min",
            effect_type=EffectType.DOUBLE_ITEMS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            is_active=True,
        )

        assert (
            get_computed_stat(state, hero.id, StatType.ATTACK, 3) == 3
        )  # No items to double


# ===========================================================================
# 3. Perfect Self
# ===========================================================================


@pytest.fixture
def perfect_self_state():
    board = _make_board()

    card = _make_skill_card(
        "perfect_self",
        "perfect_self",
        tier=CardTier.III,
        color=CardColor.GREEN,
    )

    # Create retired Tier II cards in deck
    retired_card = _make_skill_card(
        "inner_strength",
        "inner_strength",
        tier=CardTier.II,
        color=CardColor.GREEN,
        item=StatType.ATTACK,
    )
    retired_card.state = CardState.RETIRED

    hero = Hero(
        id=HeroID("hero_min"),
        name="Min",
        team=TeamColor.RED,
        deck=[retired_card],
        hand=[card],
        level=1,
        items={StatType.DEFENSE: 1},
    )
    hero.current_turn_card = card
    enemy = Hero(
        id=HeroID("enemy"),
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        hand=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_min", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=2, r=0, s=-2))
    state.current_actor_id = "hero_min"
    return state


class TestPerfectSelf:
    def test_offers_choice_when_retired_tier2_exists(self, perfect_self_state):
        """Should offer 3 options when retired Tier II cards exist."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = perfect_self_state.get_hero(HeroID("hero_min"))
        card = hero.hand[0]
        effect = CardEffectRegistry.get("perfect_self")
        stats = compute_card_stats(perfect_self_state, hero.id, card)

        steps = effect.build_steps(perfect_self_state, hero, card, stats)
        # First step is a NUMBER select with options [1, 2, 3]
        assert steps[0].target_type.value == "NUMBER"
        assert steps[0].number_options == [1, 2, 3]

    def test_only_double_items_when_no_retired_tier2(self, perfect_self_state):
        """Should only return double items steps when no retired Tier II cards exist."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        hero = perfect_self_state.get_hero(HeroID("hero_min"))
        # Remove the retired card
        hero.deck = []
        card = hero.hand[0]
        effect = CardEffectRegistry.get("perfect_self")
        stats = compute_card_stats(perfect_self_state, hero.id, card)

        steps = effect.build_steps(perfect_self_state, hero, card, stats)
        # Should just be the CreateEffectStep for DOUBLE_ITEMS
        assert len(steps) == 1
        assert steps[0].effect_type == EffectType.DOUBLE_ITEMS

    def test_convert_card_to_item_step(self, perfect_self_state):
        """ConvertCardToItemStep should convert a card to a permanent item."""
        from goa2.engine.steps import ConvertCardToItemStep

        state = perfect_self_state
        hero = state.get_hero(HeroID("hero_min"))
        retired_card = hero.deck[0]
        assert retired_card.state == CardState.RETIRED

        context = {"convert_card_id": "inner_strength"}
        step = ConvertCardToItemStep(
            card_key="convert_card_id",
            hero_id="hero_min",
        )
        push_steps(state, [step])
        state.execution_stack[-1].pending_input = None
        # Manually inject context
        state.execution_context = context
        process_resolution_stack(state)

        assert retired_card.state == CardState.ITEM
        assert hero.items.get(StatType.ATTACK, 0) >= 1


# ===========================================================================
# 4. Flurry of Blows
# ===========================================================================


@pytest.fixture
def flurry_state():
    board = _make_board()

    attack_card = _make_attack_card("crane_stance", "crane_stance")
    attack_card.state = CardState.RESOLVED
    attack_card.is_facedown = False

    ultimate = Card(
        id="flurry_of_blows",
        name="Flurry of Blows",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="flurry_of_blows",
        effect_text="",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    hero = Hero(
        id=HeroID("hero_min"),
        name="Min",
        team=TeamColor.RED,
        deck=[],
        hand=[],
        level=8,
        ultimate_card=ultimate,
    )
    hero.played_cards = [attack_card]
    hero.current_turn_card = attack_card

    enemy1 = Hero(
        id=HeroID("enemy1"),
        name="Enemy1",
        team=TeamColor.BLUE,
        deck=[],
        hand=[_make_filler_card("e1_card")],
        level=1,
    )
    enemy2 = Hero(
        id=HeroID("enemy2"),
        name="Enemy2",
        team=TeamColor.BLUE,
        deck=[],
        hand=[_make_filler_card("e2_card")],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy1, enemy2], minions=[]
            ),
        },
    )
    state.place_entity("hero_min", Hex(q=0, r=0, s=0))
    state.place_entity("enemy1", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy2", Hex(q=0, r=1, s=-1))
    state.current_actor_id = "hero_min"
    return state


class TestFlurryOfBlows:
    def test_passive_config(self):
        """Flurry of Blows should have AFTER_ATTACK passive trigger."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        effect = CardEffectRegistry.get("flurry_of_blows")
        config = effect.get_passive_config()
        assert config is not None
        assert config.trigger == PassiveTrigger.AFTER_ATTACK
        assert config.uses_per_turn == 0  # unlimited
        assert config.is_optional is True

    def test_passive_steps_include_attack(self, flurry_state):
        """Passive steps should rebuild the attack with target exclusion."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        hero = flurry_state.get_hero(HeroID("hero_min"))
        effect = CardEffectRegistry.get("flurry_of_blows")

        context = {
            "attack_effect_id": "crane_stance",
            "attack_card_id": "crane_stance",
            "defender_id": "enemy1",
        }

        steps = effect.get_passive_steps(
            flurry_state,
            hero,
            hero.ultimate_card,
            PassiveTrigger.AFTER_ATTACK,
            context,
        )

        # Should have: SetContextFlag x2 (flurry_target, is_flurry_repeat),
        #              then rebuilt attack steps, then clear is_flurry_repeat
        assert len(steps) > 3
        # First two are context flags
        assert steps[0].key == "last_flurry_target"
        assert steps[0].value == "enemy1"
        assert steps[1].key == "is_flurry_repeat"
        assert steps[1].value is True
        # Last step clears the flurry flag
        assert steps[-1].key == "is_flurry_repeat"
        assert steps[-1].value is None

    def test_passive_skips_when_flurry_repeat(self, flurry_state):
        """Passive should not trigger when is_flurry_repeat is set (prevents recursion)."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        hero = flurry_state.get_hero(HeroID("hero_min"))
        effect = CardEffectRegistry.get("flurry_of_blows")

        context = {
            "attack_effect_id": "crane_stance",
            "attack_card_id": "crane_stance",
            "defender_id": "enemy1",
            "is_flurry_repeat": True,
        }

        steps = effect.get_passive_steps(
            flurry_state,
            hero,
            hero.ultimate_card,
            PassiveTrigger.AFTER_ATTACK,
            context,
        )
        assert steps == []

    def test_passive_skips_without_attack_info(self, flurry_state):
        """Passive returns no steps if attack_effect_id/attack_card_id not in context."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        hero = flurry_state.get_hero(HeroID("hero_min"))
        effect = CardEffectRegistry.get("flurry_of_blows")

        steps = effect.get_passive_steps(
            flurry_state,
            hero,
            hero.ultimate_card,
            PassiveTrigger.AFTER_ATTACK,
            {},
        )
        assert steps == []

    def test_attack_steps_have_exclude_filter(self, flurry_state):
        """Rebuilt attack steps should exclude the last target."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.filters import ExcludeIdentityFilter
        from goa2.engine.steps import AttackSequenceStep
        from goa2.domain.models.enums import PassiveTrigger

        hero = flurry_state.get_hero(HeroID("hero_min"))
        effect = CardEffectRegistry.get("flurry_of_blows")

        context = {
            "attack_effect_id": "crane_stance",
            "attack_card_id": "crane_stance",
            "defender_id": "enemy1",
        }

        steps = effect.get_passive_steps(
            flurry_state,
            hero,
            hero.ultimate_card,
            PassiveTrigger.AFTER_ATTACK,
            context,
        )

        # Find the AttackSequenceStep in the returned steps
        attack_steps = [s for s in steps if isinstance(s, AttackSequenceStep)]
        assert len(attack_steps) >= 1

        # It should have an ExcludeIdentityFilter and be non-mandatory
        for atk in attack_steps:
            exclude_filters = [
                f for f in atk.target_filters if isinstance(f, ExcludeIdentityFilter)
            ]
            assert len(exclude_filters) >= 1
            assert "last_flurry_target" in exclude_filters[0].exclude_keys
            assert atk.is_mandatory is True

    def test_flurry_no_target_aborts_turn(self, flurry_state):
        """If the flurry repeat finds no valid different target, the turn should abort (mandatory)."""
        from goa2.engine.steps import (
            SetContextFlagStep,
            CheckPassiveAbilitiesStep,
            FinalizeHeroTurnStep,
        )

        state = flurry_state
        # Remove enemy2 so only enemy1 is adjacent (and it will be excluded)
        state.teams[TeamColor.BLUE].heroes.pop()  # remove enemy2
        del state.entity_locations[BoardEntityID("enemy2")]

        # Simulate post-attack context
        push_steps(
            state,
            [
                SetContextFlagStep(key="attack_effect_id", value="crane_stance"),
                SetContextFlagStep(key="attack_card_id", value="crane_stance"),
                SetContextFlagStep(key="defender_id", value="enemy1"),
                CheckPassiveAbilitiesStep(trigger="after_attack"),
                # This step should NOT be reached (mandatory abort skips it)
                SetContextFlagStep(key="turn_continued", value=True),
            ],
        )

        # Drive: passive prompt -> YES
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "CONFIRM_PASSIVE"
        state.execution_stack[-1].pending_input = {"selection": "YES"}

        # Continue processing - mandatory step aborts the turn
        while process_resolution_stack(state) is not None:
            # Auto-skip any remaining prompts
            state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        # The "turn_continued" flag should NOT be set (turn was aborted)
        assert state.execution_context.get("turn_continued") is None
