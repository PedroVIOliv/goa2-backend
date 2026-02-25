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


@pytest.fixture
def tidal_blast_state():
    """
    Board setup:
    - (0,0,0): Arien (attacker)
    - (1,0,-1): Enemy minion (adjacent, push candidate)
    - (2,0,-2): Empty
    - (3,0,-3): Empty
    - (4,0,-4): Empty (push destination 3)
    - (0,2,-2): Enemy hero (range 2, attack target)
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),  # Arien
        Hex(q=1, r=0, s=-1),  # Enemy minion (adjacent)
        Hex(q=2, r=0, s=-2),  # Empty
        Hex(q=3, r=0, s=-3),  # Empty
        Hex(q=4, r=0, s=-4),  # Empty (max push)
        Hex(q=0, r=2, s=-2),  # Enemy hero (range 2)
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="tidal_blast",
        name="Tidal Blast",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        is_ranged=True,
        range_value=2,
        effect_id="tidal_blast",
        effect_text="Target a unit in range. After the attack: You may push an enemy unit adjacent to you up to 3 spaces.",
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
    state.place_entity("enemy_minion", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy_hero", Hex(q=0, r=2, s=-2))

    state.current_actor_id = "arien"
    return state


def test_tidal_blast_push_3_spaces(tidal_blast_state):
    """Test full flow: push 3 spaces."""
    step = ResolveCardStep(hero_id="arien")
    push_steps(tidal_blast_state, [step])

    # 1. Action
    process_resolution_stack(tidal_blast_state)
    tidal_blast_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Target Enemy Hero
    process_resolution_stack(tidal_blast_state)
    tidal_blast_state.execution_stack[-1].pending_input = {"selection": "enemy_hero"}

    # 3. Reaction
    process_resolution_stack(tidal_blast_state)
    tidal_blast_state.execution_stack[-1].pending_input = {"selection": "PASS"}

    # 4. Select Push Target (Minion)
    process_resolution_stack(tidal_blast_state)
    tidal_blast_state.execution_stack[-1].pending_input = {"selection": "enemy_minion"}

    # 5. Select Distance (3)
    req = process_resolution_stack(tidal_blast_state)
    assert req["type"] == "SELECT_NUMBER"
    assert 3 in req["valid_options"]
    tidal_blast_state.execution_stack[-1].pending_input = {"selection": 3}

    # 6. Execute
    process_resolution_stack(tidal_blast_state)

    # Verify push result: from (1,0,-1) -> (4,0,-4)
    assert tidal_blast_state.entity_locations["enemy_minion"] == Hex(q=4, r=0, s=-4)
