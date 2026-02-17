import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    GamePhase,
    CardState,
    ActionType,
    Hero,
    Card,
    CardTier,
    CardColor,
)
from goa2.domain.types import HeroID
from goa2.domain.hex import Hex
from goa2.data.heroes.arien import create_arien
from goa2.data.heroes.rogue import create_rogue
from goa2.engine.phases import commit_card, start_revelation_phase
from goa2.engine.handler import process_resolution_stack
from goa2.engine.steps import FinalizeHeroTurnStep
import goa2.scripts.rogue_effects  # Register effects
import goa2.scripts.arien_effects  # Register effects


@pytest.fixture
def sabotage_state():
    # 1. Setup Board
    board = Board()
    z1 = Zone(
        id="z1",
        hexes={Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1), Hex(q=-1, r=0, s=1)},
        neighbors=[],
    )
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[], minions=[], life_counters=6
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[], minions=[], life_counters=6
            ),
        },
        phase=GamePhase.PLANNING,
        turn=2,  # Simulating Turn 2
    )

    # 2. Setup Heroes
    # Arien (Red)
    arien = create_arien()
    arien.id = HeroID("hero_arien")
    arien.team = TeamColor.RED

    # Rogue (Blue)
    rogue = create_rogue()
    rogue.id = HeroID("hero_rogue")
    rogue.team = TeamColor.BLUE

    # Hero3 (Red) - Just for Initiative Ordering
    hero3 = Hero(
        id=HeroID("hero_3"),
        name="Hero 3",
        team=TeamColor.RED,
        deck=[],
        hand=[],
        items={},
    )
    # Give Hero3 a card with Initiative 7 (using SKILL as primary, not DEFENSE)
    card_hero3 = Card(
        id="hero3_card",
        name="Average Speed",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=7,
        primary_action=ActionType.SKILL,  # Changed from DEFENSE - DEFENSE cannot be chosen as active action
        primary_action_value=None,
        effect_id="none",
        effect_text="None",
        secondary_actions={ActionType.DEFENSE: 1},
    )
    hero3.hand.append(card_hero3)

    state.register_entity(arien, "hero")
    state.register_entity(rogue, "hero")
    state.register_entity(hero3, "hero")

    state.place_entity(arien.id, Hex(q=0, r=0, s=0))
    state.place_entity(rogue.id, Hex(q=1, r=0, s=-1))
    state.place_entity(hero3.id, Hex(q=-1, r=0, s=1))  # Safe distance

    # 3. Initialize Hands (Standard)
    arien.initialize_state()
    rogue.initialize_state()
    # Hero3 already init manually

    return state


def test_rogue_initiates_sabotage_and_arien_defeats_rogue(sabotage_state):
    state = sabotage_state
    arien = state.get_hero(HeroID("hero_arien"))
    rogue = state.get_hero(HeroID("hero_rogue"))
    hero3 = state.get_hero(HeroID("hero_3"))

    # --- SETUP TURN 1 HISTORY ---
    turn1_card = next(c for c in arien.deck if c.id == "noble_blade")
    if turn1_card in arien.hand:
        arien.hand.remove(turn1_card)
    arien.played_cards.append(turn1_card)
    turn1_card.state = CardState.RESOLVED

    # --- PLANNING PHASE (Turn 2) ---
    state.phase = GamePhase.PLANNING

    # Arien commits "Liquid Leap" (Init 4)
    commit_card(state, arien.id, next(c for c in arien.hand if c.id == "liquid_leap"))

    # Rogue commits "Shadow Step" (Init 8)
    commit_card(state, rogue.id, next(c for c in rogue.hand if c.id == "rogue_gold"))

    # Hero3 commits "Average Speed" (Init 7)
    commit_card(state, hero3.id, hero3.hand[0])

    # --- REVELATION / RESOLUTION START ---
    # Init Order: Rogue (8) > Hero3 (7) > Arien (4)
    assert state.phase == GamePhase.RESOLUTION
    assert state.current_actor_id == rogue.id

    # --- EXECUTE ROGUE TURN (SABOTAGE) ---
    # 1. ResolveCardStep -> Choose Action -> SKILL
    req = process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    req = process_resolution_stack(state)

    # 2. Select Enemy Hero -> Arien
    state.execution_stack[-1].pending_input = {"selection": "hero_arien"}
    req = process_resolution_stack(state)

    # 3. Select Card -> Noble Blade
    state.execution_stack[-1].pending_input = {"selection": "noble_blade"}

    # 4. Finalize
    process_resolution_stack(state)
    process_resolution_stack(state)  # FinalizeHeroTurnStep

    # --- CHECK NEXT ACTOR ---
    # Current State:
    # Rogue: Done
    # Hero3: Init 7
    # Arien: Init 11 (Swapped from 4)
    # Order: Arien (11) > Hero3 (7)

    assert state.current_actor_id == arien.id
    assert arien.current_turn_card.id == "noble_blade"

    # --- EXECUTE ARIEN TURN (REVENGE) ---
    # 1. ResolveCardStep -> Choose Action
    req = process_resolution_stack(state)
    assert req["type"] == "CHOOSE_ACTION"
    assert "Noble Blade" in req["prompt"]

    # 2. Input: ATTACK
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}
    req = process_resolution_stack(state)

    # 3. Select Attack Target -> Rogue
    state.execution_stack[-1].pending_input = {"selection": "hero_rogue"}
    req = process_resolution_stack(state)

    # 4. Optional Nudge -> Skip
    # "Select adjacent unit to move 1 space (Optional)"
    # Note: In this scenario, there are no other units adjacent to Rogue (victim) except Arien (caster).
    # Arien is excluded by ExcludeIdentityFilter(exclude_self=True).
    # Rogue is excluded by ExcludeIdentityFilter(exclude_keys=["victim_id"]).
    # So there are NO candidates. The step is optional, so it AUTO-SKIPS.

    # We expected SELECT_UNIT here, but it skipped to AttackSequenceStep -> ReactionWindowStep.
    assert req["type"] == "SELECT_CARD_OR_PASS"
    assert req["player_id"] == rogue.id

    # 5. Rogue Reaction -> Pass
    state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}
    process_resolution_stack(state)

    # Finalize Arien
    process_resolution_stack(state)

    # --- CHECK NEXT ACTOR ---
    # Arien Done.
    # Next: Hero3 (7)

    assert state.current_actor_id == hero3.id

    # --- VERIFY DEFEAT ---
    assert state.entity_locations.get(rogue.id) is None
    assert state.teams[TeamColor.BLUE].life_counters == 5


def test_rogue_bypasses_sabotage_by_choosing_movement(sabotage_state):
    state = sabotage_state
    arien = state.get_hero(HeroID("hero_arien"))
    rogue = state.get_hero(HeroID("hero_rogue"))
    hero3 = state.get_hero(HeroID("hero_3"))

    # --- SETUP HISTORY ---
    turn1_card = next(c for c in arien.deck if c.id == "noble_blade")
    if turn1_card in arien.hand:
        arien.hand.remove(turn1_card)
    arien.played_cards.append(turn1_card)
    turn1_card.state = CardState.RESOLVED

    # --- PLANNING ---
    state.phase = GamePhase.PLANNING

    # Arien: Liquid Leap (4)
    commit_card(state, arien.id, next(c for c in arien.hand if c.id == "liquid_leap"))

    # Rogue: Shadow Step (8)
    commit_card(state, rogue.id, next(c for c in rogue.hand if c.id == "rogue_gold"))

    # Hero3: Average Speed (7)
    commit_card(state, hero3.id, hero3.hand[0])

    # --- RESOLUTION ---
    # Order: Rogue (8) > Hero3 (7) > Arien (4)

    assert state.current_actor_id == rogue.id

    # 1. Rogue Choose Action -> MOVEMENT
    req = process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "MOVEMENT"}
    req = process_resolution_stack(state)

    # 2. Select Destination (if needed) or just resolve
    if req and req["type"] == "SELECT_HEX":
        target = next(opt for opt in req["valid_options"] if opt != Hex(q=0, r=0, s=0))
        state.execution_stack[-1].pending_input = {"selection": target}
        process_resolution_stack(state)

    # Finish Rogue Turn
    process_resolution_stack(state)

    # --- CHECK NEXT ACTOR ---
    # Rogue Done.
    # Remaining: Hero3 (7), Arien (4)
    # Next: Hero3

    assert state.current_actor_id == hero3.id

    # Execute Hero3 Turn (Simple Resolve)
    # Hero 3 card is "Average Speed" - SKILL card with DEFENSE secondary.
    # Since primary is SKILL, it will prompt for CHOOSE_ACTION.

    # 1. Choose Action - SKILL (primary)
    req = process_resolution_stack(state)  # Choose Action for Hero 3
    if req and req["type"] == "CHOOSE_ACTION":
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}
        process_resolution_stack(state)

    # SKILL with no effect just logs and finishes.
    # Process until Hero3 done
    # Loop until actor changes
    while state.current_actor_id == hero3.id:
        req = process_resolution_stack(state)
        if not req:
            break
        # If input needed, provide default or skip
        if req["type"] == "CHOOSE_ACTION":
            state.execution_stack[-1].pending_input = {"selection": "SKILL"}
        else:
            # Try to provide dummy input to break loop if stuck?
            # For SELECT_HEX, pick something valid
            if "valid_options" in req:
                state.execution_stack[-1].pending_input = {
                    "selection": req["valid_options"][0]
                }

    # --- CHECK NEXT ACTOR ---
    # Hero3 Done.
    # Next: Arien (4)

    assert state.current_actor_id == arien.id

    # Verify Arien's Card
    assert arien.current_turn_card.id == "liquid_leap"
