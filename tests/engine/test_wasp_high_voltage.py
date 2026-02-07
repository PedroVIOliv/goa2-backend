"""
Tests for High Voltage passive ability.

High Voltage (Wasp's Ultimate):
"Each time after you perform a basic skill, you may defeat an enemy minion
in radius; an enemy hero who was adjacent to that minion discards a card, if able."

Key behaviors:
1. Passive triggers AFTER_BASIC_SKILL (Gold/Silver skill cards only)
2. Only active when hero level >= 8
3. Unlimited uses per turn ("each time")
4. Optional - player can decline
5. Defeats enemy minion in radius
6. Forces adjacent enemy hero to discard
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    CardState,
    TeamColor,
    Team,
    Minion,
    MinionType,
    PassiveTrigger,
)
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID, UnitID
from goa2.engine.steps import (
    CheckPassiveAbilitiesStep,
    OfferPassiveStep,
    SelectStep,
    DefeatUnitStep,
    ForceDiscardStep,
)
from goa2.engine.handler import process_resolution_stack

# Import to register the effect
import goa2.scripts.wasp_effects  # noqa: F401


@pytest.fixture
def level_8_wasp():
    """Creates a Wasp hero at level 8 with the ultimate card active."""
    # Create the ultimate card
    ultimate = Card(
        id="high_voltage",
        name="High Voltage",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="high_voltage",
        effect_text="Each time after you perform a basic skill, you may defeat an enemy minion in radius; an enemy hero who was adjacent to that minion discards a card, if able.",
        radius_value=3,
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    # Create a basic skill card (Gold) for testing
    gold_skill_card = Card(
        id="telekinesis",
        name="Telekinesis",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="telekinesis",
        effect_text="Move an enemy unit in range 1 space.",
    )

    hero = Hero(
        id=HeroID("hero_wasp"),
        name="Wasp",
        level=8,  # Level 8 - ultimate is active
        deck=[gold_skill_card],
        hand=[gold_skill_card],
        items={},
        ultimate_card=ultimate,
    )
    return hero


@pytest.fixture
def level_7_wasp():
    """Creates a Wasp hero at level 7 (ultimate NOT active)."""
    ultimate = Card(
        id="high_voltage",
        name="High Voltage",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={},
        effect_id="high_voltage",
        effect_text="Each time after you perform a basic skill...",
        radius_value=3,
    )
    ultimate.state = CardState.PASSIVE
    ultimate.is_facedown = False

    gold_skill_card = Card(
        id="telekinesis",
        name="Telekinesis",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="telekinesis",
        effect_text="Move an enemy unit in range 1 space.",
    )

    hero = Hero(
        id=HeroID("hero_wasp"),
        name="Wasp",
        level=7,  # Level 7 - ultimate NOT active
        deck=[gold_skill_card],
        hand=[gold_skill_card],
        items={},
        ultimate_card=ultimate,
    )
    return hero


@pytest.fixture
def enemy_hero():
    """Creates an enemy hero with cards in hand."""
    discard_card = Card(
        id="enemy_card",
        name="Enemy Card",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        effect_id="",
        effect_text="Test card.",
    )

    hero = Hero(
        id=HeroID("hero_enemy"),
        name="Enemy",
        level=1,
        deck=[discard_card],
        hand=[discard_card],
        items={},
    )
    return hero


@pytest.fixture
def enemy_minion():
    """Creates an enemy minion."""
    return Minion(
        id=UnitID("minion_enemy_1"),
        name="Enemy Melee Minion",
        type=MinionType.MELEE,
        team=TeamColor.RED,
    )


@pytest.fixture
def game_state_with_wasp(level_8_wasp, enemy_hero, enemy_minion):
    """Creates a game state with Wasp, enemy hero, and enemy minion."""
    # Create board with multiple hexes
    board = Board(
        zones={
            "center": Zone(
                id="center",
                name="Center",
                hexes=[
                    Hex(q=0, r=0, s=0),  # Wasp position
                    Hex(q=1, r=-1, s=0),  # Minion position (adjacent to enemy hero)
                    Hex(q=2, r=-2, s=0),  # Enemy hero position
                    Hex(q=-1, r=1, s=0),
                    Hex(q=0, r=-1, s=1),
                ],
                spawn_points=[],
            )
        }
    )

    state = GameState(board=board, teams={})

    # Set up teams
    blue_team = Team(color=TeamColor.BLUE, heroes=[level_8_wasp])
    level_8_wasp.team = TeamColor.BLUE
    state.teams[TeamColor.BLUE] = blue_team

    red_team = Team(color=TeamColor.RED, heroes=[enemy_hero], minions=[enemy_minion])
    enemy_hero.team = TeamColor.RED
    enemy_minion.team = TeamColor.RED
    state.teams[TeamColor.RED] = red_team

    # Place units on board
    state.entity_locations[UnitID(level_8_wasp.id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(enemy_minion.id)] = Hex(q=1, r=-1, s=0)
    state.entity_locations[UnitID(enemy_hero.id)] = Hex(q=2, r=-2, s=0)

    return state


class TestHighVoltagePassiveConfig:
    """Tests for HighVoltageEffect.get_passive_config()."""

    def test_passive_config_trigger(self):
        """Passive should trigger on AFTER_BASIC_SKILL."""
        from goa2.scripts.wasp_effects import HighVoltageEffect

        effect = HighVoltageEffect()
        config = effect.get_passive_config()

        assert config is not None
        assert config.trigger == PassiveTrigger.AFTER_BASIC_SKILL

    def test_passive_config_unlimited_uses(self):
        """Passive should have unlimited uses per turn."""
        from goa2.scripts.wasp_effects import HighVoltageEffect

        effect = HighVoltageEffect()
        config = effect.get_passive_config()

        assert config.uses_per_turn == 0  # 0 = unlimited

    def test_passive_config_optional(self):
        """Passive should be optional."""
        from goa2.scripts.wasp_effects import HighVoltageEffect

        effect = HighVoltageEffect()
        config = effect.get_passive_config()

        assert config.is_optional is True


class TestCheckPassiveAbilitiesStep:
    """Tests for CheckPassiveAbilitiesStep with AFTER_BASIC_SKILL."""

    def test_finds_ultimate_passive_at_level_8(self, game_state_with_wasp):
        """Ultimate passive should be found when hero is level 8+."""
        state = game_state_with_wasp
        state.current_actor_id = HeroID("hero_wasp")

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_BASIC_SKILL.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 1
        assert isinstance(result.new_steps[0], OfferPassiveStep)
        assert result.new_steps[0].card_id == "high_voltage"

    def test_no_passive_at_level_7(self, level_7_wasp):
        """Ultimate passive should NOT be found when hero is level 7."""
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

        team = Team(color=TeamColor.BLUE, heroes=[level_7_wasp])
        level_7_wasp.team = TeamColor.BLUE
        state.teams[TeamColor.BLUE] = team
        state.entity_locations[UnitID(level_7_wasp.id)] = Hex(q=0, r=0, s=0)
        state.current_actor_id = HeroID("hero_wasp")

        step = CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_BASIC_SKILL.value)
        result = step.resolve(state, {})

        assert result.is_finished
        assert len(result.new_steps) == 0  # No passive found


class TestHighVoltagePassiveSteps:
    """Tests for HighVoltageEffect.get_passive_steps()."""

    def test_passive_steps_structure(self, game_state_with_wasp):
        """Passive should generate correct step structure."""
        from goa2.scripts.wasp_effects import HighVoltageEffect

        state = game_state_with_wasp
        hero = state.get_hero(HeroID("hero_wasp"))
        card = hero.ultimate_card

        effect = HighVoltageEffect()
        steps = effect.get_passive_steps(
            state, hero, card, PassiveTrigger.AFTER_BASIC_SKILL, {}
        )

        assert len(steps) == 4

        # Step 1: Select enemy minion
        assert isinstance(steps[0], SelectStep)
        assert steps[0].output_key == "hv_minion"
        assert steps[0].is_mandatory is False

        # Step 2: Select adjacent enemy hero
        assert isinstance(steps[1], SelectStep)
        assert steps[1].output_key == "hv_hero"
        assert steps[1].active_if_key == "hv_minion"

        # Step 3: Defeat minion
        assert isinstance(steps[2], DefeatUnitStep)
        assert steps[2].victim_key == "hv_minion"
        assert steps[2].active_if_key == "hv_minion"

        # Step 4: Force discard
        assert isinstance(steps[3], ForceDiscardStep)
        assert steps[3].victim_key == "hv_hero"

    def test_passive_ignores_wrong_trigger(self, game_state_with_wasp):
        """Passive should return empty list for wrong trigger."""
        from goa2.scripts.wasp_effects import HighVoltageEffect

        state = game_state_with_wasp
        hero = state.get_hero(HeroID("hero_wasp"))
        card = hero.ultimate_card

        effect = HighVoltageEffect()
        steps = effect.get_passive_steps(
            state, hero, card, PassiveTrigger.BEFORE_ATTACK, {}
        )

        assert len(steps) == 0


class TestDefeatUnitStepWithVictimKey:
    """Tests for DefeatUnitStep with victim_key parameter."""

    def test_defeat_unit_with_victim_key(self, game_state_with_wasp, enemy_minion):
        """DefeatUnitStep should read victim_id from context when using victim_key."""
        state = game_state_with_wasp
        context = {"hv_minion": enemy_minion.id}

        step = DefeatUnitStep(victim_key="hv_minion")
        result = step.resolve(state, context)

        assert result.is_finished
        # Should spawn RemoveUnitStep and CheckLanePushStep
        assert len(result.new_steps) == 2

    def test_defeat_unit_skips_when_key_missing(self, game_state_with_wasp):
        """DefeatUnitStep should skip when victim_key is not in context."""
        state = game_state_with_wasp
        context = {}  # No hv_minion key

        step = DefeatUnitStep(victim_key="hv_minion")
        result = step.resolve(state, context)

        assert result.is_finished
        assert result.new_steps is None or len(result.new_steps) == 0

    def test_defeat_unit_respects_active_if_key(self, game_state_with_wasp):
        """DefeatUnitStep should skip when active_if_key condition not met."""
        state = game_state_with_wasp
        context = {}  # No hv_minion key

        step = DefeatUnitStep(victim_key="hv_minion", active_if_key="hv_minion")
        result = step.resolve(state, context)

        assert result.is_finished
        assert result.new_steps is None or len(result.new_steps) == 0
