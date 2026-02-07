import pytest
from goa2.domain.state import GameState
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, GamePhase
from goa2.domain.types import HeroID
from goa2.data.heroes.arien import create_arien
from goa2.data.heroes.rogue import create_rogue
from goa2.engine.handler import process_resolution_stack
from goa2.engine.phases import commit_card
from goa2.engine.map_loader import load_map


@pytest.fixture
def state():
    # Load map directly
    board = load_map("data/maps/test_map.json")

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
        phase=GamePhase.SETUP,
        wave_counter=5,
    )
    state.active_zone_id = board.lane[len(board.lane) // 2]

    # Create Heroes
    arien = create_arien()
    arien.id = HeroID("hero_arien")
    arien.team = TeamColor.RED

    rogue = create_rogue()
    rogue.id = HeroID("hero_rogue")
    rogue.team = TeamColor.BLUE

    # Register Heroes
    state.register_entity(arien, "hero")
    state.register_entity(rogue, "hero")

    # Initialize hands
    arien.initialize_state()
    rogue.initialize_state()

    # Place heroes on board
    state.move_unit(arien.id, Hex(q=0, r=0, s=0))
    state.move_unit(rogue.id, Hex(q=1, r=0, s=-1))

    return state


def test_swap_after_revelation_prompts_correct_card(state):
    arien = state.get_hero(HeroID("hero_arien"))
    rogue = state.get_hero(HeroID("hero_rogue"))

    # -------------------------------------------------------------------------
    # TURN 1: Both play a card
    # -------------------------------------------------------------------------
    state.phase = GamePhase.PLANNING

    # Arien plays card index 0
    card1_arien = arien.hand[0]
    commit_card(state, arien.id, card1_arien)

    # Rogue plays card index 0
    card1_rogue = rogue.hand[0]
    commit_card(state, rogue.id, card1_rogue)

    # Simulate resolution of Turn 1 (Transition to Resolution, resolve all)
    # We can shortcut this by manually moving cards to 'played_cards' and resetting
    # effectively simulating the end of Turn 1.

    # Clear pending inputs (they were moved to current_turn_card by start_revelation in normal flow)
    state.pending_inputs = {}

    # Force Arien's Card 1 to be RESOLVED
    arien.current_turn_card = card1_arien
    arien.resolve_current_card()  # Moves to played_cards, sets state=RESOLVED

    # Force Rogue's Card 1 to be RESOLVED
    rogue.current_turn_card = card1_rogue
    rogue.resolve_current_card()

    # Advance Game Counters
    state.turn = 2
    state.phase = GamePhase.PLANNING
    state.unresolved_hero_ids = []

    # -------------------------------------------------------------------------
    # TURN 2: Commit Cards
    # -------------------------------------------------------------------------
    # Arien commits card index 0 (which is now a different card since first was played)
    card2_arien = arien.hand[0]
    commit_card(state, arien.id, card2_arien)

    # Rogue commits card index 0
    card2_rogue = rogue.hand[0]
    commit_card(state, rogue.id, card2_rogue)

    # Current State: Cards committed but not revealed
    # commit_card triggers phase transition if all act.
    assert state.phase == GamePhase.RESOLUTION

    # We need to verify Arien is acting or force it.

    # Check if arien is current actor. If not, swap current actor to arien
    # and update stack to process him first.
    if state.current_actor_id != arien.id:
        print(f"Forcing actor to Arien (was {state.current_actor_id})")
        state.current_actor_id = arien.id
        # Clear stack and push ResolveCardStep for Arien
        state.execution_stack = []
        from goa2.engine.steps import ResolveCardStep, FinalizeHeroTurnStep

        # Remember LIFO: Finalize (bottom) -> Resolve (top)
        state.execution_stack.append(FinalizeHeroTurnStep(hero_id=arien.id))
        state.execution_stack.append(ResolveCardStep(hero_id=arien.id))

    # -------------------------------------------------------------------------
    # THE SWAP
    # -------------------------------------------------------------------------
    # Now, before Arien executes his ResolveCardStep, we swap his cards.
    # We swap 'card2_arien' (Current Unresolved) with 'card1_arien' (Resolved/Played).

    # Sanity check before swap
    assert arien.current_turn_card == card2_arien
    assert card1_arien in arien.played_cards

    print(f"Swapping {card2_arien.id} (Current) with {card1_arien.id} (Played)")

    arien.swap_cards(card2_arien, card1_arien)

    # Verify Swap happened in memory
    assert arien.current_turn_card == card1_arien
    assert card2_arien in arien.played_cards

    # -------------------------------------------------------------------------
    # EXECUTE RESOLUTION
    # -------------------------------------------------------------------------
    # Process the step
    input_request = process_resolution_stack(state)

    # -------------------------------------------------------------------------
    # ASSERTIONS
    # -------------------------------------------------------------------------
    assert input_request is not None
    assert input_request["type"] == "CHOOSE_ACTION"
    assert input_request["player_id"] == arien.id

    # The prompt should reference the SWAPPED card (Card 1)
    print(f"Prompt is for: {input_request['prompt']}")
    assert card1_arien.name in input_request["prompt"]
