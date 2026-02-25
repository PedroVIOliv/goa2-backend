"""
Tests for Living Tsunami passive ability.

Living Tsunami (Arien's Ultimate):
"Once per turn, before performing an Attack action, you may move 1 space."

Key behaviors:
1. Passive triggers BEFORE_ATTACK for any Attack action (primary or secondary)
2. Only active when hero level >= 8
3. Usage limited to once per turn
4. Optional - player can decline
5. Resets at turn end
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    CardState,
    TeamColor,
    Team,
    PassiveTrigger,
)
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID, UnitID
from goa2.engine.steps import (
    CheckPassiveAbilitiesStep,
    OfferPassiveStep,
    MarkPassiveUsedStep,
    MoveSequenceStep,
)

# Import to register the effect
import goa2.scripts.arien_effects  # noqa: F401


@pytest.fixture
def level_8_arien():
    """Creates an Arien hero at level 8 with the ultimate card active."""
    # Create the ultimate card
    ultimate = Card(
        id="living_tsunami",
        name="Living Tsunami",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="living_tsunami",
        effect_text="Once per turn, before performing an Attack action, you may move 1 space.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    # Create a basic attack card for testing
    attack_card = Card(
        id="test_attack",
        name="Test Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=5,
        secondary_actions={},
        effect_id="",
        effect_text="Basic attack for testing.",
    )

    hero = Hero(
        id=HeroID("hero_arien"),
        name="Arien",
        level=8,  # Level 8 - ultimate is active
        deck=[attack_card],
        hand=[attack_card],
        items={},
        ultimate_card=ultimate,
    )
    return hero


@pytest.fixture
def level_7_arien():
    """Creates an Arien hero at level 7 (ultimate NOT active)."""
    ultimate = Card(
        id="living_tsunami",
        name="Living Tsunami",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="living_tsunami",
        effect_text="Once per turn, before performing an Attack action, you may move 1 space.",
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    attack_card = Card(
        id="test_attack",
        name="Test Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=5,
        secondary_actions={},
        effect_id="",
        effect_text="Basic attack for testing.",
    )

    hero = Hero(
        id=HeroID("hero_arien"),
        name="Arien",
        level=7,  # Level 7 - ultimate NOT active
        deck=[attack_card],
        hand=[attack_card],
        items={},
        ultimate_card=ultimate,
    )
    return hero


@pytest.fixture
def game_state_with_hero(level_8_arien):
    """Creates a minimal game state with the level 8 Arien."""
    from goa2.domain.board import Zone

    # Create minimal board
    board = Board(
        zones={
            "center": Zone(
                id="center",
                name="Center",
                hexes=[
                    Hex(q=0, r=0, s=0),
                    Hex(q=1, r=-1, s=0),
                    Hex(q=-1, r=1, s=0),
                    Hex(q=0, r=-1, s=1),
                ],
                spawn_points=[],
            )
        }
    )

    state = GameState(board=board, teams={})

    # Set up team
    team = Team(color=TeamColor.BLUE, heroes=[level_8_arien])
    level_8_arien.team = TeamColor.BLUE
    state.teams[TeamColor.BLUE] = team

    # Place hero on board (don't register again - team registration handles it)
    state.entity_locations[UnitID(level_8_arien.id)] = Hex(q=0, r=0, s=0)

    return state


class TestCheckPassiveAbilitiesStep:
    """Tests for CheckPassiveAbilitiesStep."""

    def test_finds_ultimate_passive_at_level_8(self, game_state_with_hero):
        """Ultimate passive should be found when hero is level 8+."""
        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 1
        assert isinstance(result.new_steps[0], OfferPassiveStep)
        assert result.new_steps[0].card_id == "living_tsunami"

    def test_no_passive_at_level_7(self, level_7_arien):
        """Ultimate passive should NOT be found when hero is level 7."""
        from goa2.domain.board import Zone

        board = Board(
            zones={
                "center": Zone(
                    id="center",
                    name="Center",
                    hexes=[Hex(q=0, r=0, s=0)],
                    spawn_points=[],
                )
            }
        )
        state = GameState(board=board, teams={})

        team = Team(color=TeamColor.BLUE, heroes=[level_7_arien])
        level_7_arien.team = TeamColor.BLUE
        state.teams[TeamColor.BLUE] = team

        # Place hero on board
        state.entity_locations[UnitID(level_7_arien.id)] = Hex(q=0, r=0, s=0)
        state.current_actor_id = HeroID("hero_arien")

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0  # No passive found

    def test_no_passive_for_wrong_trigger(self, game_state_with_hero):
        """Passive should not trigger for BEFORE_MOVEMENT."""
        state = game_state_with_hero
        state.current_actor_id = HeroID("hero_arien")

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_MOVEMENT.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0  # Wrong trigger

    def test_passive_usage_limit(self, game_state_with_hero):
        """Passive should not trigger if already used this turn."""
        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        # Mark the ultimate as already used
        hero.ultimate_card.passive_uses_this_turn = 1

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0  # Already used


class TestOfferPassiveStep:
    """Tests for OfferPassiveStep."""

    def test_optional_passive_requires_input(self, game_state_with_hero):
        """Optional passive should request player input."""
        state = game_state_with_hero
        state.current_actor_id = HeroID("hero_arien")

        step = OfferPassiveStep(
            card_id="living_tsunami",
            trigger=PassiveTrigger.BEFORE_ATTACK.value,
            is_optional=True,
            prompt="Living Tsunami: Move 1 space before attacking?",
        )
        result = step.resolve(state, {})

        # requires_input is set, which pauses for player input
        assert result.requires_input
        assert result.input_request["type"] == "CONFIRM_PASSIVE"
        assert "YES" in result.input_request["options"]
        assert "NO" in result.input_request["options"]

    def test_accept_passive_spawns_move_steps(self, game_state_with_hero):
        """Accepting the passive should spawn movement steps."""
        state = game_state_with_hero
        state.current_actor_id = HeroID("hero_arien")

        step = OfferPassiveStep(
            card_id="living_tsunami",
            trigger=PassiveTrigger.BEFORE_ATTACK.value,
            is_optional=True,
            prompt="Living Tsunami: Move 1 space before attacking?",
        )
        step.pending_input = {"selection": "YES"}
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 2  # MoveSequenceStep + MarkPassiveUsedStep

        # First step should be MoveSequenceStep
        move_step = result.new_steps[0]
        assert isinstance(move_step, MoveSequenceStep)
        assert move_step.range_val == 1

        # Second step should be MarkPassiveUsedStep
        mark_step = result.new_steps[1]
        assert isinstance(mark_step, MarkPassiveUsedStep)
        assert mark_step.card_id == "living_tsunami"

    def test_decline_passive_no_steps(self, game_state_with_hero):
        """Declining the passive should spawn no steps."""
        state = game_state_with_hero
        state.current_actor_id = HeroID("hero_arien")

        step = OfferPassiveStep(
            card_id="living_tsunami",
            trigger=PassiveTrigger.BEFORE_ATTACK.value,
            is_optional=True,
            prompt="Living Tsunami: Move 1 space before attacking?",
        )
        step.pending_input = {"selection": "NO"}
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0


class TestMarkPassiveUsedStep:
    """Tests for MarkPassiveUsedStep."""

    def test_increments_usage_counter(self, game_state_with_hero):
        """MarkPassiveUsedStep should increment the usage counter."""
        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        assert hero.ultimate_card.passive_uses_this_turn == 0

        step = MarkPassiveUsedStep(card_id="living_tsunami")
        result = step.resolve(state, {})

        assert result.is_finished
        assert hero.ultimate_card.passive_uses_this_turn == 1

    def test_increments_multiple_times(self, game_state_with_hero):
        """Usage counter should increment each time step is called."""
        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        # Note: In practice, usage limit prevents this, but counter should still work
        hero.ultimate_card.passive_uses_this_turn = 5

        step = MarkPassiveUsedStep(card_id="living_tsunami")
        step.resolve(state, {})

        assert hero.ultimate_card.passive_uses_this_turn == 6


class TestLevelUpUltimateActivation:
    """Tests for level-up to level 8 triggering ultimate activation."""

    def test_ultimate_activates_at_level_8_after_level_up(self):
        """
        Integration test: hero levels up from 7 to 8, then ultimate passive
        should be detected by CheckPassiveAbilitiesStep.
        """
        from goa2.domain.board import Zone

        # Create hero at level 7 with enough gold to reach level 8
        ultimate = Card(
            id="living_tsunami",
            name="Living Tsunami",
            tier=CardTier.IV,
            color=CardColor.PURPLE,
            initiative=0,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={},
            effect_id="living_tsunami",
            effect_text="Once per turn, before performing an Attack action, you may move 1 space.",
        )
        ultimate.state = CardState.PASSIVE
        ultimate.is_facedown = False

        attack_card = Card(
            id="test_attack",
            name="Test Attack",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=5,
            primary_action=ActionType.ATTACK,
            primary_action_value=5,
            secondary_actions={},
            effect_id="",
            effect_text="Basic attack for testing.",
        )

        hero = Hero(
            id=HeroID("hero_arien"),
            name="Arien",
            level=7,  # Start at level 7
            gold=7,  # Cost to reach level 8 is 7 gold
            deck=[attack_card],
            hand=[attack_card],
            items={},
            ultimate_card=ultimate,
        )

        # Set up game state
        board = Board(
            zones={
                "center": Zone(
                    id="center",
                    name="Center",
                    hexes=[Hex(q=0, r=0, s=0)],
                    spawn_points=[],
                )
            }
        )
        state = GameState(board=board, teams={})
        team = Team(color=TeamColor.BLUE, heroes=[hero])
        hero.team = TeamColor.BLUE
        state.teams[TeamColor.BLUE] = team
        state.entity_locations[UnitID(hero.id)] = Hex(q=0, r=0, s=0)
        state.current_actor_id = HeroID("hero_arien")

        # BEFORE level up: passive should NOT be found
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})
        assert len(result.new_steps) == 0, "Ultimate should not be active at level 7"

        # Simulate level up (what EndPhaseCleanupStep._level_up does)
        hero.gold -= 7
        hero.level = 8

        # AFTER level up: passive SHOULD be found
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})
        assert len(result.new_steps) == 1, "Ultimate should be active at level 8"
        assert isinstance(result.new_steps[0], OfferPassiveStep)
        assert result.new_steps[0].card_id == "living_tsunami"

    def test_ultimate_not_active_at_level_7_even_with_gold(self):
        """
        Verify that having gold doesn't activate ultimate - only level matters.
        """
        from goa2.domain.board import Zone

        ultimate = Card(
            id="living_tsunami",
            name="Living Tsunami",
            tier=CardTier.IV,
            color=CardColor.PURPLE,
            initiative=0,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            secondary_actions={},
            effect_id="living_tsunami",
            effect_text="Once per turn, before performing an Attack action, you may move 1 space.",
        )
        ultimate.state = CardState.PASSIVE

        hero = Hero(
            id=HeroID("hero_arien"),
            name="Arien",
            level=7,  # Level 7
            gold=100,  # Lots of gold, but not spent yet
            deck=[],
            hand=[],
            items={},
            ultimate_card=ultimate,
        )

        board = Board(
            zones={
                "center": Zone(
                    id="center",
                    name="Center",
                    hexes=[Hex(q=0, r=0, s=0)],
                    spawn_points=[],
                )
            }
        )
        state = GameState(board=board, teams={})
        team = Team(color=TeamColor.BLUE, heroes=[hero])
        hero.team = TeamColor.BLUE
        state.teams[TeamColor.BLUE] = team
        state.entity_locations[UnitID(hero.id)] = Hex(q=0, r=0, s=0)
        state.current_actor_id = HeroID("hero_arien")

        # Ultimate should NOT be active (level check, not gold check)
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})
        assert len(result.new_steps) == 0


class TestPassiveUsageResetAcrossTurns:
    """Tests for passive usage counter resetting correctly."""

    def test_finalize_hero_turn_resets_ultimate_usage(self, game_state_with_hero):
        """FinalizeHeroTurnStep should reset ultimate card usage counter."""
        from goa2.engine.steps import FinalizeHeroTurnStep

        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        # Simulate that passive was used
        hero.ultimate_card.passive_uses_this_turn = 1

        # Give hero a current_turn_card so finalize works properly
        attack_card = hero.deck[0]
        attack_card.state = CardState.UNRESOLVED
        hero.current_turn_card = attack_card

        step = FinalizeHeroTurnStep(hero_id="hero_arien")
        step.resolve(state, {})

        assert hero.ultimate_card.passive_uses_this_turn == 0

    def test_usage_counter_allows_reuse_after_reset(self, game_state_with_hero):
        """After turn finalize, passive should be usable again."""
        from goa2.engine.steps import FinalizeHeroTurnStep

        state = game_state_with_hero
        hero = state.get_hero(HeroID("hero_arien"))
        state.current_actor_id = HeroID("hero_arien")

        # Use the passive
        hero.ultimate_card.passive_uses_this_turn = 1

        # Verify it's blocked
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})
        assert len(result.new_steps) == 0, "Should be blocked after use"

        # Finalize turn (which resets counter)
        attack_card = hero.deck[0]
        attack_card.state = CardState.UNRESOLVED
        hero.current_turn_card = attack_card
        finalize = FinalizeHeroTurnStep(hero_id="hero_arien")
        finalize.resolve(state, {})

        # Re-set actor (finalize clears it)
        state.current_actor_id = HeroID("hero_arien")

        # Now passive should be available again
        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ATTACK.value)
        result = step.resolve(state, {})
        assert len(result.new_steps) == 1, "Should be available after reset"
