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
    CardState,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
import goa2.scripts.arien_effects  # Register effects


@pytest.fixture
def dangerous_current_state():
    """
    Board setup:
    - (0,0,0): Arien (attacker)
    - (1,0,-1): Enemy minion (adjacent, attack target)
    - (2,0,-2): Enemy hero (1 space behind target, candidate for effect)
    - (3,0,-3): Empty (2 spaces behind target)
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Arien
    arien = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="dangerous_current",
        name="Dangerous Current",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=6,
        effect_id="dangerous_current",
        effect_text="Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 2 spaces in a straight line directly behind the target discards a card, or is defeated.",
        is_facedown=False,
    )
    arien.current_turn_card = card

    # Enemies
    enemy_target = Minion(
        id="enemy_minion", name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    enemy_victim = Hero(
        id="enemy_victim", name="Victim", team=TeamColor.BLUE, deck=[], level=1
    )
    # Give victim a card to discard
    discard_fodder = Card(
        id="fodder",
        name="Fodder",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        state=CardState.HAND,
        effect_id="",
        effect_text="",
    )
    enemy_victim.hand = [discard_fodder]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy_victim], minions=[enemy_target]
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_minion", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy_victim", Hex(q=2, r=0, s=-2))

    state.current_actor_id = "arien"
    return state


def test_dangerous_current_discard_flow(dangerous_current_state):
    """
    Scenario:
    1. Arien plays Dangerous Current.
    2. Selects 'enemy_minion' as attack target.
    3. Selects 'enemy_victim' as backstab target.
    4. 'enemy_victim' has a card, so must discard.
    5. 'enemy_victim' selects the card.
    6. Card is discarded.
    7. Attack proceeds on 'enemy_minion'.
    """
    step = ResolveCardStep(hero_id="arien")
    push_steps(dangerous_current_state, [step])

    # 1. Action Choice (Attack)
    process_resolution_stack(dangerous_current_state)
    dangerous_current_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Select Attack Target (Mandatory) -> enemy_minion
    req = process_resolution_stack(dangerous_current_state)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy_minion" in req["valid_options"]
    dangerous_current_state.execution_stack[-1].pending_input = {
        "selection": "enemy_minion"
    }

    # 3. Select Backstab Victim (Optional) -> enemy_victim
    # Note: Filter should allow enemy_victim at (2,0,-2) because it's behind (1,0,-1) from (0,0,0)
    req = process_resolution_stack(dangerous_current_state)
    assert req["type"] == "SELECT_UNIT"
    assert "enemy_victim" in req["valid_options"]
    dangerous_current_state.execution_stack[-1].pending_input = {
        "selection": "enemy_victim"
    }

    # 4. Force Discard -> Victim Selection
    # The system should now ask 'enemy_victim' to select a card.
    req = process_resolution_stack(dangerous_current_state)
    assert req["type"] == "SELECT_CARD"
    assert (
        req["player_id"] == "enemy_victim"
    )  # Crucial check: override_player_id_key working?
    assert "fodder" in req["valid_options"]

    dangerous_current_state.execution_stack[-1].pending_input = {"selection": "fodder"}

    # 5. Execute Discard and Attack
    process_resolution_stack(dangerous_current_state)

    # Verify Discard
    victim = dangerous_current_state.get_hero("enemy_victim")
    assert len(victim.hand) == 0
    assert len(victim.discard_pile) == 1
    assert victim.discard_pile[0].id == "fodder"

    # Attack sequence continues (Reaction Window for minion's owner - Blue Team)
    # Minion can't react, but owner might if we implemented that.
    # Current engine: Minions don't trigger reaction window unless specific logic?
    # AttackSequenceStep calls ReactionWindowStep.
    # ReactionWindowStep checks: "Optimization: Minions/Non-Heroes cannot react."
    # So it skips reaction.

    # Verify Combat Result (Minion Defeated)
    # Attack 6 vs Minion Defense (usually 0 unless modified)
    assert "enemy_minion" not in dangerous_current_state.entity_locations


def test_dangerous_current_defeat_flow(dangerous_current_state):
    """
    Scenario:
    1. Victim has NO cards.
    2. Effect triggers Defeat immediately.
    """
    # Empty the victim's hand
    victim = dangerous_current_state.get_hero("enemy_victim")
    victim.hand = []

    step = ResolveCardStep(hero_id="arien")
    push_steps(dangerous_current_state, [step])

    # 1. Action -> Attack
    process_resolution_stack(dangerous_current_state)
    dangerous_current_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Select Target -> Minion
    process_resolution_stack(dangerous_current_state)
    dangerous_current_state.execution_stack[-1].pending_input = {
        "selection": "enemy_minion"
    }

    # 3. Select Victim -> Victim
    process_resolution_stack(dangerous_current_state)
    dangerous_current_state.execution_stack[-1].pending_input = {
        "selection": "enemy_victim"
    }

    # 4. Logic detects empty hand -> DefeatUnitStep -> RemoveUnitStep
    process_resolution_stack(dangerous_current_state)

    # Verify Victim Defeated (removed from board)
    assert "enemy_victim" not in dangerous_current_state.entity_locations

    # Attack still proceeds on minion
    assert "enemy_minion" not in dangerous_current_state.entity_locations
