import pytest

import goa2.scripts.arien_effects

# Import to ensure effect classes are registered
import goa2.scripts.nebkher_effects
import goa2.scripts.tigerclaw_effects  # noqa: F401
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    GamePhase,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import (
    EffectType,
)
from goa2.domain.models.enums import StatType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import ResolveCardStep
from goa2.engine.steps.combat import AttackSequenceStep

from ..builders import hero_card


@pytest.fixture
def scenario_state():
    """
    Creates a game state with:
    - RED Team: Nebkher (hero_nebkher) and Tigerclaw (hero_tigerclaw)
    - BLUE Team: Arien (hero_arien) and Xargatha (hero_xargatha)

    Placements:
    - Tigerclaw: (0, 0, 0)
    - Arien: (1, 0, -1) (adjacent to Tigerclaw and Nebkher)
    - Nebkher: (0, 1, -1) (adjacent to Arien and Xargatha)
    - Xargatha: (0, 2, -2) (adjacent to Nebkher)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=0, r=2, s=-2),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
    }
    board.zones = {"z1": Zone(id="z1", hexes=hexes, neighbors=[])}
    board.populate_tiles_from_zones()

    # Load heroes from registry to ensure complete/real decks
    nebkher = HeroRegistry.get("NebKher")
    assert nebkher is not None
    nebkher.id = "hero_nebkher"
    nebkher.team = TeamColor.RED

    tigerclaw = HeroRegistry.get("Tigerclaw")
    assert tigerclaw is not None
    tigerclaw.id = "hero_tigerclaw"
    tigerclaw.team = TeamColor.RED

    arien = HeroRegistry.get("Arien")
    assert arien is not None
    arien.id = "hero_arien"
    arien.team = TeamColor.BLUE

    xargatha = HeroRegistry.get("Xargatha")
    assert xargatha is not None
    xargatha.id = "hero_xargatha"
    xargatha.team = TeamColor.BLUE

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[nebkher, tigerclaw], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[arien, xargatha], minions=[]),
        },
    )
    state.phase = GamePhase.RESOLUTION

    state.place_entity("hero_tigerclaw", Hex(q=0, r=0, s=0))
    state.place_entity("hero_arien", Hex(q=1, r=0, s=-1))
    state.place_entity("hero_nebkher", Hex(q=0, r=1, s=-1))
    state.place_entity("hero_xargatha", Hex(q=0, r=2, s=-2))

    return state


def test_arien_master_duelist_nebkher_mind_grip(scenario_state):
    # 1. Setup cards and turn counts
    arien = scenario_state.get_hero("hero_arien")
    nebkher = scenario_state.get_hero("hero_nebkher")

    # Give Arien master_duelist in her hand
    arien.hand = [hero_card("Arien", "master_duelist")]

    # Arien must have played a card on her first turn so that she has a card in
    # her previous slot. Let's make it violent_torrent (which has an Attack primary).
    vt_card = hero_card("Arien", "violent_torrent")
    arien.played_cards = [vt_card]
    arien.resolved_turn_count = 1

    # Nebkher has resolved 1 turn, so his prev slot index is 0.
    nebkher.resolved_turn_count = 1

    # 2. Tigerclaw attacks Arien.
    # We push an AttackSequenceStep where Tigerclaw is the attacker and Arien is the pre-selected target.
    scenario_state.current_actor_id = "hero_tigerclaw"
    scenario_state.execution_context["victim"] = "hero_arien"
    push_steps(
        scenario_state,
        [AttackSequenceStep(damage=4, range_val=1, target_id_key="victim")],
    )

    # Resolve until Arien reacts
    result = process_stack(scenario_state)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    assert result.input_request.player_id == "hero_arien"

    # Arien defends with master_duelist
    scenario_state.execution_stack[-1].pending_input = {"selection": "master_duelist"}
    result = process_stack(scenario_state)

    # Let the defense effect resolve and the attack finish.
    # Since we passed a defense card, standard resolution of the attack will continue and finish.
    assert result.input_request is None  # Attack sequence has completed

    # Verify that the ATTACK_IMMUNITY active effect is registered on Arien,
    # and that it excepts Tigerclaw.
    active_effects = scenario_state.active_effects
    duelist_effects = [e for e in active_effects if e.effect_type == EffectType.ATTACK_IMMUNITY]
    assert len(duelist_effects) == 1
    effect = duelist_effects[0]
    assert effect.source_id == "hero_arien"
    assert "hero_tigerclaw" in effect.except_attacker_ids
    assert "hero_nebkher" not in effect.except_attacker_ids

    # 3. Nebkher uses mind_grip
    scenario_state.current_actor_id = "hero_nebkher"
    # Give Nebkher mind_grip card
    mg_card = hero_card("NebKher", "mind_grip")
    nebkher.current_turn_card = mg_card

    # Resolve Nebkher's card
    push_steps(scenario_state, [ResolveCardStep(hero_id="hero_nebkher")])
    result = process_stack(scenario_state)

    # Prompt: Choose an action to perform on NebKher's card (primary or secondary)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "CHOOSE_ACTION"
    scenario_state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    result = process_stack(scenario_state)

    # Prompt: Mind Grip — choose one (1 or 2)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_NUMBER"
    scenario_state.execution_stack[-1].pending_input = {"selection": 1}
    result = process_stack(scenario_state)

    # Prompt: Select an enemy hero in range with a card in their previous slot.
    # Arien is adjacent to Nebkher, has a card in previous slot, and is an enemy.
    # Arien has ATTACK_IMMUNITY from other heroes, but this SelectStep is part of a SKILL action.
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_UNIT"
    valid_targets = [opt.id for opt in result.input_request.options]

    # VERIFY ARIEN IS SELECTABLE:
    assert (
        "hero_arien" in valid_targets
    ), "Arien should be selectable for Mind Grip targeting (SKILL action)"

    # Now let's select Arien and verify that if Nebkher tries to perform her previous card's ATTACK action,
    # she is NOT selectable for that attack targeting.
    scenario_state.execution_stack[-1].pending_input = {"selection": "hero_arien"}
    result = process_stack(scenario_state)

    # Prompt: Choose an action to perform on Arien's previous slot card (Violent Torrent)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "CHOOSE_ACTION"
    # Select the ATTACK action on Violent Torrent
    scenario_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}
    result = process_stack(scenario_state)

    # Prompt: Select Attack Target (from the copied attack action)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_UNIT"
    attack_targets = [opt.id for opt in result.input_request.options]

    # VERIFY ARIEN IS NOT SELECTABLE FOR THE ATTACK, BUT XARGATHA IS SELECTABLE:
    assert "hero_xargatha" in attack_targets, "Xargatha should be selectable for the attack"
    assert "hero_arien" not in attack_targets, "Arien should be immune to Nebkher's attack action"


def test_mind_grip_nested_action_type_restoration(scenario_state):
    arien = scenario_state.get_hero("hero_arien")
    nebkher = scenario_state.get_hero("hero_nebkher")
    xargatha = scenario_state.get_hero("hero_xargatha")

    # Give Xargatha a defense card in hand (master_duelist) and +2 Defense item so she survives
    xargatha.hand = [hero_card("Arien", "master_duelist")]
    xargatha.items[StatType.DEFENSE] = 2

    # Arien must have played a card on her first turn so that she has a card in her previous slot.
    vt_card = hero_card("Arien", "violent_torrent")
    arien.played_cards = [vt_card]
    arien.resolved_turn_count = 1
    nebkher.resolved_turn_count = 1

    # Nebkher uses mind_grip
    scenario_state.current_actor_id = "hero_nebkher"
    mg_card = hero_card("NebKher", "mind_grip")
    nebkher.current_turn_card = mg_card

    # Resolve Nebkher's card
    push_steps(scenario_state, [ResolveCardStep(hero_id="hero_nebkher")])
    result = process_stack(scenario_state)

    # 1. Action Choice: choose SKILL (Mind Grip)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "CHOOSE_ACTION"
    # Action type in context should be None initially
    assert scenario_state.execution_context.get("current_action_type") is None
    scenario_state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    result = process_stack(scenario_state)

    # 2. Mind Grip Choice: choose option 1 (Perform card action)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_NUMBER"
    assert scenario_state.execution_context.get("current_action_type") == ActionType.SKILL
    scenario_state.execution_stack[-1].pending_input = {"selection": 1}
    result = process_stack(scenario_state)

    # 3. Select Target Hero: Choose Arien
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_UNIT"
    assert scenario_state.execution_context.get("current_action_type") == ActionType.SKILL
    scenario_state.execution_stack[-1].pending_input = {"selection": "hero_arien"}
    result = process_stack(scenario_state)

    # 4. Choose Action on Arien's Card: Choose ATTACK
    assert result.input_request is not None
    assert result.input_request.request_type.value == "CHOOSE_ACTION"
    assert scenario_state.execution_context.get("current_action_type") == ActionType.SKILL
    scenario_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}
    result = process_stack(scenario_state)

    # 5. Select Attack Target (from copied Attack action): Choose Xargatha
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_UNIT"
    # Action type in context should now be ATTACK (set by PerformCardActionStep)
    assert scenario_state.execution_context.get("current_action_type") == ActionType.ATTACK
    scenario_state.execution_stack[-1].pending_input = {"selection": "hero_xargatha"}
    result = process_stack(scenario_state)

    # 6. Xargatha's Reaction Window: Choose master_duelist
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    assert scenario_state.execution_context.get("current_action_type") == ActionType.ATTACK
    scenario_state.execution_stack[-1].pending_input = {"selection": "master_duelist"}

    # Resolve the defense reaction
    result = process_stack(scenario_state)

    # 7. Repeat Prompt: choose NO
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_OPTION"
    # Action type should still be ATTACK during repeat check
    assert scenario_state.execution_context.get("current_action_type") == ActionType.ATTACK
    scenario_state.execution_stack[-1].pending_input = {"selection": "NO"}

    result = process_stack(scenario_state)
    assert result.input_request is None  # Sequence finished

    # Verify that the active effect created by Xargatha's defense has origin_action_type = ActionType.DEFENSE
    active_effects = scenario_state.active_effects
    duelist_effects = [
        e
        for e in active_effects
        if e.source_id == "hero_xargatha" and e.effect_type == EffectType.ATTACK_IMMUNITY
    ]
    assert len(duelist_effects) == 1
    effect = duelist_effects[0]
    assert effect.origin_action_type == ActionType.DEFENSE

    # Verify that the action type in context is correctly restored to SKILL at the end of the turn
    assert scenario_state.execution_context.get("current_action_type") == ActionType.SKILL
