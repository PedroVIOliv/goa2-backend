import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
import goa2.scripts.arien_effects


@pytest.fixture
def rogue_wave_state():
    """
    Board setup:
    - (0,0,0): Arien (attacker)
    - (1,0,-1): Enemy minion (adjacent, push candidate)
    - (2,0,-2): Empty (push destination 1)
    - (3,0,-3): Empty (push destination 2)
    - (0,2,-2): Enemy hero (in range 2, attack target)
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),  # Arien
        Hex(q=1, r=0, s=-1),  # Enemy minion (adjacent)
        Hex(q=2, r=0, s=-2),  # Empty (push 1)
        Hex(q=3, r=0, s=-3),  # Empty (push 2)
        Hex(q=0, r=2, s=-2),  # Enemy hero (range 2)
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="rogue_wave",
        name="Rogue Wave",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        is_ranged=True,
        range_value=2,
        effect_id="rogue_wave",
        effect_text="Target a unit in range. After the attack: You may push an enemy unit adjacent to you up to 2 spaces.",
        is_facedown=False,
    )
    hero.current_turn_card = card

    enemy_hero = Hero(
        id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[], level=1
    )
    enemy_minion = Minion(
        id="enemy_minion", name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy_hero], minions=[enemy_minion]
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_minion", Hex(q=1, r=0, s=-1))  # Adjacent to Arien
    state.place_entity("enemy_hero", Hex(q=0, r=2, s=-2))  # Range 2 from Arien

    state.current_actor_id = "arien"

    return state


def test_rogue_wave_attack_and_push_2_spaces(rogue_wave_state):
    """Test full flow: attack in range, then push adjacent enemy 2 spaces."""
    step = ResolveCardStep(hero_id="arien")
    push_steps(rogue_wave_state, [step])

    # 1. Choose Action
    req = process_resolution_stack(rogue_wave_state)
    assert req["type"] == "CHOOSE_ACTION"
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Select Attack Target (in range 2)
    req = process_resolution_stack(rogue_wave_state)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy_hero" in req["valid_options"]
    assert "enemy_minion" in req["valid_options"]  # Also in range (adjacent = range 1)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

    # 3. Reaction Window (enemy_hero)
    req = process_resolution_stack(rogue_wave_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    rogue_wave_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}

    # 4. Combat resolves, then Select push target (optional)
    req = process_resolution_stack(rogue_wave_state)
    assert req["type"] == "SELECT_UNIT"
    assert req["can_skip"] == True  # Optional
    assert "enemy_minion" in req["valid_options"]  # Adjacent enemy
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "enemy_minion"}

    # 5. Select push distance (1 or 2)
    req = process_resolution_stack(rogue_wave_state)
    assert req["type"] == "SELECT_NUMBER"
    assert 1 in req["valid_options"]
    assert 2 in req["valid_options"]
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": 2}

    # 6. Push executes, action finishes
    res = process_resolution_stack(rogue_wave_state)
    assert res is None  # Finished

    # Verify: enemy_minion pushed 2 spaces from (1,0,-1) to (3,0,-3)
    assert rogue_wave_state.entity_locations["enemy_minion"] == Hex(q=3, r=0, s=-3)

    # Verify: enemy_hero was defeated (4 dmg vs 0 def)
    assert "enemy_hero" not in rogue_wave_state.entity_locations


def test_rogue_wave_push_1_space(rogue_wave_state):
    """Test pushing only 1 space when player chooses."""
    step = ResolveCardStep(hero_id="arien")
    push_steps(rogue_wave_state, [step])

    # 1. Action
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Target the enemy_hero (range 2), so minion survives for push
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

    # 3. Reaction
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}

    # 4. Push target - select the adjacent minion
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "enemy_minion"}

    # 5. Push distance = 1
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": 1}

    # 6. End
    process_resolution_stack(rogue_wave_state)

    # Verify: pushed only 1 space
    assert rogue_wave_state.entity_locations["enemy_minion"] == Hex(q=2, r=0, s=-2)


def test_rogue_wave_skip_push(rogue_wave_state):
    """Test skipping the optional push."""
    step = ResolveCardStep(hero_id="arien")
    push_steps(rogue_wave_state, [step])

    # 1. Action
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Target
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

    # 3. Reaction
    process_resolution_stack(rogue_wave_state)
    rogue_wave_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}

    # 4. Push target (skip)
    req = process_resolution_stack(rogue_wave_state)
    assert req["can_skip"] == True
    rogue_wave_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

    # 5. Should finish (no push distance selection since we skipped)
    res = process_resolution_stack(rogue_wave_state)
    assert res is None

    # Verify: minion not moved
    assert rogue_wave_state.entity_locations["enemy_minion"] == Hex(q=1, r=0, s=-1)
