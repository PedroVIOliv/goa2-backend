"""
Tests for Expert Duelist card effect (Arien Tier II Defense).

Card text: "Ignore all minion defense modifiers. This turn: You are immune to
attack actions of all enemy heroes, except this attacker."

Two effects:
1. Ignore minion defense modifiers (same as Aspiring Duelist)
2. ATTACK_IMMUNITY effect - immune to attacks from other enemy heroes
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, ActionType
from goa2.domain.models.effect import (
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
    DurationType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import SelectStep, CreateEffectStep, SetContextFlagStep
from goa2.engine.filters import TeamFilter, ImmunityFilter, RangeFilter
from goa2.engine.effect_manager import EffectManager

# Import to register effects
import goa2.scripts.arien_effects  # noqa: F401


@pytest.fixture
def duelist_state():
    """
    Creates a state with:
    - Arien (hero_arien) on RED team at (0,0,0)
    - Enemy Hero 1 (h_enemy1) on BLUE team at (1,0,-1) - the attacker
    - Enemy Hero 2 (h_enemy2) on BLUE team at (2,0,-2) - another enemy
    - Minion (m1) on BLUE team at (0,1,-1) - for minion modifier testing
    """
    board = Board()
    z1 = Zone(
        id="z1",
        name="Battle",
        hexes=[
            Hex(q=0, r=0, s=0),
            Hex(q=1, r=0, s=-1),
            Hex(q=2, r=0, s=-2),
            Hex(q=0, r=1, s=-1),
        ],
    )
    board.zones["z1"] = z1

    for h in z1.hexes:
        board.tiles[h] = Tile(hex=h)

    # Arien (defender)
    arien = Hero(id="hero_arien", name="Arien", team=TeamColor.RED, deck=[])

    # Enemy heroes
    h_enemy1 = Hero(id="h_enemy1", name="Enemy1", team=TeamColor.BLUE, deck=[])
    h_enemy2 = Hero(id="h_enemy2", name="Enemy2", team=TeamColor.BLUE, deck=[])

    # Minion for defense modifier testing
    m1 = Minion(id="m1", name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[h_enemy1, h_enemy2], minions=[m1]
            ),
        },
        entity_locations={},
        current_actor_id="h_enemy1",  # Enemy 1 is attacking
        active_zone_id="z1",
    )

    state.place_entity("hero_arien", Hex(q=0, r=0, s=0))
    state.place_entity("h_enemy1", Hex(q=1, r=0, s=-1))
    state.place_entity("h_enemy2", Hex(q=2, r=0, s=-2))
    state.place_entity("m1", Hex(q=0, r=1, s=-1))

    return state


class TestAttackImmunityEffect:
    """Tests for the ATTACK_IMMUNITY effect mechanics."""

    def test_attack_immunity_blocks_other_attackers(self, duelist_state):
        """
        When Arien has ATTACK_IMMUNITY with h_enemy1 exempted,
        h_enemy2 should NOT be able to target Arien.
        """
        # Create ATTACK_IMMUNITY effect on Arien, exempting h_enemy1
        EffectManager.create_effect(
            state=duelist_state,
            source_id="hero_arien",
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_TURN,
            except_attacker_ids=["h_enemy1"],
            is_active=True,
        )

        # Switch current actor to h_enemy2
        duelist_state.current_actor_id = "h_enemy2"

        # Test directly with ImmunityFilter
        immunity_filter = ImmunityFilter()
        context = {"current_action_type": ActionType.ATTACK}

        # Arien should be filtered out (immune to h_enemy2's attack)
        result = immunity_filter.apply("hero_arien", duelist_state, context)
        assert result is False, "Arien should be immune to attacks from h_enemy2"

        # h_enemy1 should still be targetable (not immune)
        result_h1 = immunity_filter.apply("h_enemy1", duelist_state, context)
        assert result_h1 is True, "h_enemy1 should be targetable"

    def test_attack_immunity_allows_exempted_attacker(self, duelist_state):
        """
        When Arien has ATTACK_IMMUNITY with h_enemy1 exempted,
        h_enemy1 SHOULD still be able to target Arien.
        """
        # Create ATTACK_IMMUNITY effect on Arien, exempting h_enemy1
        EffectManager.create_effect(
            state=duelist_state,
            source_id="hero_arien",
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_TURN,
            except_attacker_ids=["h_enemy1"],
            is_active=True,
        )

        # h_enemy1 is the current actor (and is exempted)
        duelist_state.current_actor_id = "h_enemy1"

        step = SelectStep(
            target_type="UNIT",
            prompt="Select Attack Target",
            filters=[
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=3),
                ImmunityFilter(),
            ],
        )

        context = {"current_action_type": ActionType.ATTACK}
        res = step.resolve(duelist_state, context)

        valid_options = res.input_request["valid_options"]

        # Arien SHOULD be targetable (h_enemy1 is exempted)
        assert "hero_arien" in valid_options

    def test_attack_immunity_does_not_affect_non_attack_actions(self, duelist_state):
        """
        ATTACK_IMMUNITY should only apply when current_action_type is ATTACK.
        For SKILL actions, the immunity should not apply.
        """
        # Create ATTACK_IMMUNITY effect on Arien
        EffectManager.create_effect(
            state=duelist_state,
            source_id="hero_arien",
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_TURN,
            except_attacker_ids=["h_enemy1"],
            is_active=True,
        )

        # h_enemy2 is acting
        duelist_state.current_actor_id = "h_enemy2"

        step = SelectStep(
            target_type="UNIT",
            prompt="Select Target",
            filters=[
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=3),
                ImmunityFilter(),
            ],
        )

        # Context indicates this is a SKILL action (not ATTACK)
        context = {"current_action_type": ActionType.SKILL}
        res = step.resolve(duelist_state, context)

        valid_options = res.input_request["valid_options"]

        # Arien SHOULD be targetable (immunity only applies to ATTACK)
        assert "hero_arien" in valid_options

    def test_attack_immunity_inactive_effect_ignored(self, duelist_state):
        """
        Inactive ATTACK_IMMUNITY effects should not block attacks.
        """
        # Create ATTACK_IMMUNITY effect but set is_active=False
        EffectManager.create_effect(
            state=duelist_state,
            source_id="hero_arien",
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_TURN,
            except_attacker_ids=["h_enemy1"],
            is_active=False,  # Inactive!
        )

        duelist_state.current_actor_id = "h_enemy2"

        step = SelectStep(
            target_type="UNIT",
            prompt="Select Attack Target",
            filters=[
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=3),
                ImmunityFilter(),
            ],
        )

        context = {"current_action_type": ActionType.ATTACK}
        res = step.resolve(duelist_state, context)

        valid_options = res.input_request["valid_options"]

        # Arien SHOULD be targetable (effect is inactive)
        assert "hero_arien" in valid_options


class TestCreateEffectStepWithExceptAttacker:
    """Tests for CreateEffectStep with except_attacker_key."""

    def test_create_effect_step_reads_attacker_from_context(self, duelist_state):
        """
        CreateEffectStep with except_attacker_key should read the attacker ID
        from context and store it in except_attacker_ids.
        """
        step = CreateEffectStep(
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_TURN,
            except_attacker_key="attacker_id",
            is_active=True,
            use_context_card=False,
        )

        # Simulate context from defense resolution
        context = {"attacker_id": "h_enemy1"}
        duelist_state.current_actor_id = "hero_arien"

        step.resolve(duelist_state, context)

        # Check that effect was created with correct except_attacker_ids
        assert len(duelist_state.active_effects) == 1
        effect = duelist_state.active_effects[0]
        assert effect.effect_type == EffectType.ATTACK_IMMUNITY
        assert "h_enemy1" in effect.except_attacker_ids


class TestExpertDuelistDefenseSteps:
    """Tests for the ExpertDuelistEffect.get_defense_steps()."""

    def test_expert_duelist_returns_both_effects(self, duelist_state):
        """
        ExpertDuelistEffect.get_defense_steps() should return:
        1. SetContextFlagStep for ignore_minion_defense
        2. CreateEffectStep for ATTACK_IMMUNITY
        """
        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get("expert_duelist")
        assert effect is not None

        arien = duelist_state.get_hero("hero_arien")

        # Mock card object (needs card stats attributes for compute_card_stats)
        class MockCard:
            id = "expert_duelist_card"
            primary_action = ActionType.DEFENSE
            primary_action_value = 6
            secondary_actions = {}
            range_value = None
            radius_value = None
            is_ranged = False

            @property
            def current_primary_action(self):
                return self.primary_action

            @property
            def current_primary_action_value(self):
                return self.primary_action_value

            @property
            def current_secondary_actions(self):
                return self.secondary_actions

            @property
            def current_effect_id(self):
                return None

        context = {"attacker_id": "h_enemy1"}
        steps = effect.get_defense_steps(duelist_state, arien, MockCard(), context)

        assert steps is not None
        assert len(steps) == 2

        # First step: SetContextFlagStep for ignore_minion_defense
        assert isinstance(steps[0], SetContextFlagStep)
        assert steps[0].key == "ignore_minion_defense"
        assert steps[0].value is True

        # Second step: CreateEffectStep for ATTACK_IMMUNITY
        assert isinstance(steps[1], CreateEffectStep)
        assert steps[1].effect_type == EffectType.ATTACK_IMMUNITY
        assert steps[1].except_attacker_key == "attacker_id"
        assert steps[1].duration == DurationType.THIS_TURN


class TestMasterDuelistDefenseSteps:
    """Tests for the MasterDuelistEffect.get_defense_steps()."""

    def test_master_duelist_returns_both_effects(self, duelist_state):
        """
        MasterDuelistEffect.get_defense_steps() should return:
        1. SetContextFlagStep for ignore_minion_defense
        2. CreateEffectStep for ATTACK_IMMUNITY with THIS_ROUND duration
        """
        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get("master_duelist")
        assert effect is not None

        arien = duelist_state.get_hero("hero_arien")

        # Mock card object (needs card stats attributes for compute_card_stats)
        class MockCard:
            id = "master_duelist_card"
            primary_action = ActionType.DEFENSE
            primary_action_value = 6
            secondary_actions = {}
            range_value = None
            radius_value = None
            is_ranged = False

            @property
            def current_primary_action(self):
                return self.primary_action

            @property
            def current_primary_action_value(self):
                return self.primary_action_value

            @property
            def current_secondary_actions(self):
                return self.secondary_actions

            @property
            def current_effect_id(self):
                return None

        context = {"attacker_id": "h_enemy1"}
        steps = effect.get_defense_steps(duelist_state, arien, MockCard(), context)

        assert steps is not None
        assert len(steps) == 2

        # First step: SetContextFlagStep for ignore_minion_defense
        assert isinstance(steps[0], SetContextFlagStep)
        assert steps[0].key == "ignore_minion_defense"
        assert steps[0].value is True

        # Second step: CreateEffectStep for ATTACK_IMMUNITY with THIS_ROUND
        assert isinstance(steps[1], CreateEffectStep)
        assert steps[1].effect_type == EffectType.ATTACK_IMMUNITY
        assert steps[1].except_attacker_key == "attacker_id"
        assert steps[1].duration == DurationType.THIS_ROUND  # Key difference!

    def test_master_duelist_immunity_persists_across_turns(self, duelist_state):
        """
        Master Duelist immunity should persist across turns within the same round,
        but expire when cards are retrieved at end of round.
        """
        from goa2.domain.models import (
            Card,
            CardTier,
            CardColor,
            ActionType as CardActionType,
            CardState,
        )

        # Setup: Give Arien a card that will be "played" and create the effect linked to it
        defense_card = Card(
            id="master_duelist_card",
            name="Master Duelist",
            tier=CardTier.III,
            color=CardColor.BLUE,
            initiative=10,
            primary_action=CardActionType.DEFENSE,
            primary_action_value=6,
            secondary_actions={},
            effect_id="master_duelist",
            effect_text="Ignore all minion defense modifiers. This round: You are immune to attack actions of all enemy heroes, except this attacker.",
        )
        arien = duelist_state.get_hero("hero_arien")
        arien.played_cards.append(defense_card)
        defense_card.state = CardState.RESOLVED

        # Create effect linked to the card
        EffectManager.create_effect(
            state=duelist_state,
            source_id="hero_arien",
            source_card_id="master_duelist_card",  # Link to card
            effect_type=EffectType.ATTACK_IMMUNITY,
            scope=EffectScope(
                shape=Shape.POINT, origin_id="hero_arien", affects=AffectsFilter.SELF
            ),
            duration=DurationType.THIS_ROUND,
            except_attacker_ids=["h_enemy1"],
            is_active=True,
        )

        # Simulate turn advancing within same round
        initial_turn = duelist_state.turn
        duelist_state.turn = initial_turn + 1  # Next turn, same round

        # h_enemy2 tries to attack
        duelist_state.current_actor_id = "h_enemy2"
        immunity_filter = ImmunityFilter()
        context = {"current_action_type": ActionType.ATTACK}

        # Arien should still be immune (effect lasts entire round)
        result = immunity_filter.apply("hero_arien", duelist_state, context)
        assert result is False, (
            "Arien should still be immune on next turn within same round"
        )

        # Now simulate end of round: deactivate effects and retrieve cards
        # This is what EndPhaseStep._retrieve_cards() does
        for card in arien.played_cards:
            EffectManager.deactivate_effects_by_card(duelist_state, card.id)
        arien.retrieve_cards()

        # Verify effect is now inactive
        effect = duelist_state.active_effects[0]
        assert effect.is_active is False, (
            "Effect should be deactivated after card retrieval"
        )

        # Arien should NO LONGER be immune
        result_after_retrieval = immunity_filter.apply(
            "hero_arien", duelist_state, context
        )
        assert result_after_retrieval is True, (
            "Arien should not be immune after cards are retrieved at end of round"
        )
