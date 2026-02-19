import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    EffectType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep, PlaceUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effect_manager import EffectManager
import goa2.scripts.wasp_effects  # noqa: F401 - Register wasp effects


@pytest.fixture
def wasp_magnetic_state():
    """
    Board setup:
    - (0,0,0): Wasp (attacker)
    - (1,0,-1): Adjacent Enemy 1 (attack target)
    - (3,0,-3): Enemy Hero 2 (in radius 3, should be blocked)
    - (4,0,-4): Enemy Hero 3 (outside radius 3, should be allowed)
    - (2,0,-2): Empty space (for testing placement)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=4, r=0, s=-4),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="magnetic_dagger",
        name="Magnetic Dagger",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=12,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        radius_value=3,
        effect_id="magnetic_dagger",
        effect_text="Target a unit adjacent to you. After the attack: This turn: Enemy units in radius cannot be swapped or placed by themselves or by enemy heroes.",
        is_facedown=False,
    )
    wasp.current_turn_card = card

    enemy1 = Hero(id="e1", name="E1", team=TeamColor.BLUE, deck=[], level=1)
    enemy2 = Hero(id="e2", name="E2", team=TeamColor.BLUE, deck=[], level=1)
    enemy3 = Hero(id="e3", name="E3", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy1, enemy2, enemy3], minions=[]
            ),
        },
    )

    state.place_entity("wasp", Hex(q=0, r=0, s=0))
    state.place_entity("e1", Hex(q=1, r=0, s=-1))
    state.place_entity("e2", Hex(q=3, r=0, s=-3))
    state.place_entity("e3", Hex(q=4, r=0, s=-4))

    state.current_actor_id = "wasp"
    return state


def test_magnetic_dagger_flow(wasp_magnetic_state):
    """
    Scenario:
    1. Wasp plays Magnetic Dagger.
    2. Selects e1 as attack target.
    3. Attack resolves.
    4. Effect is created blocking enemy heroes in radius 3.
    """
    step = ResolveCardStep(hero_id="wasp")
    push_steps(wasp_magnetic_state, [step])

    # 1. Action Choice (Attack)
    req = process_resolution_stack(wasp_magnetic_state)
    assert req["type"] == "CHOOSE_ACTION"
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Select Attack Target (Mandatory) -> e1
    req = process_resolution_stack(wasp_magnetic_state)
    assert req["type"] == "SELECT_UNIT"
    assert "e1" in req["valid_options"]
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "e1"}

    # 3. Reaction Window
    req = process_resolution_stack(wasp_magnetic_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "PASS"}

    # 4. Finish resolution
    process_resolution_stack(wasp_magnetic_state)

    # Verify effect created
    assert len(wasp_magnetic_state.active_effects) == 1
    effect = wasp_magnetic_state.active_effects[0]
    assert effect.effect_type == EffectType.PLACEMENT_PREVENTION

    # Finalize the hero's turn to move card to RESOLVED state
    hero = wasp_magnetic_state.get_hero("wasp")
    card_id = hero.current_turn_card.id
    hero.resolve_current_card()
    EffectManager.activate_effects_by_card(wasp_magnetic_state, card_id)


def test_magnetic_dagger_blocks_placement_in_radius(wasp_magnetic_state):
    """
    Test that enemy heroes within radius 3 cannot be placed.
    """
    step = ResolveCardStep(hero_id="wasp")
    push_steps(wasp_magnetic_state, [step])

    # Attack e1
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "e1"}
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "PASS"}
    process_resolution_stack(wasp_magnetic_state)

    # Finalize card to activate effects
    hero = wasp_magnetic_state.get_hero("wasp")
    card_id = hero.current_turn_card.id
    hero.resolve_current_card()
    EffectManager.activate_effects_by_card(wasp_magnetic_state, card_id)

    # Re-place e1 (was defeated during attack)
    wasp_magnetic_state.place_entity("e1", Hex(q=1, r=0, s=-1))

    # Try to place e2 (in radius 3) by enemy e2 - should be blocked
    wasp_magnetic_state.current_actor_id = "e2"
    place_step_blocked = PlaceUnitStep(
        unit_id="e2", target_hex_arg=Hex(q=2, r=0, s=-2), is_mandatory=True
    )
    res_blocked = place_step_blocked.resolve(wasp_magnetic_state, {})
    assert res_blocked.abort_action is True, (
        "Placement of enemy hero in radius should be blocked"
    )

    # Try to place e3 (outside radius 3) by enemy e3 - should be allowed
    wasp_magnetic_state.current_actor_id = "e3"
    place_step_allowed = PlaceUnitStep(
        unit_id="e3", target_hex_arg=Hex(q=2, r=0, s=-2), is_mandatory=True
    )
    res_allowed = place_step_allowed.resolve(wasp_magnetic_state, {})
    assert res_allowed.abort_action is False, (
        "Placement of enemy hero outside radius should be allowed"
    )


def test_magnetic_dagger_blocks_self_placement(wasp_magnetic_state):
    """
    Test that enemy heroes cannot place themselves (via skills) while in radius 3.
    """
    step = ResolveCardStep(hero_id="wasp")
    push_steps(wasp_magnetic_state, [step])

    # Attack e1
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "e1"}
    process_resolution_stack(wasp_magnetic_state)
    wasp_magnetic_state.execution_stack[-1].pending_input = {"selection": "PASS"}
    process_resolution_stack(wasp_magnetic_state)

    # Finalize card to activate effects
    hero = wasp_magnetic_state.get_hero("wasp")
    card_id = hero.current_turn_card.id
    hero.resolve_current_card()
    EffectManager.activate_effects_by_card(wasp_magnetic_state, card_id)

    # Re-place e1 (was defeated during attack)
    wasp_magnetic_state.place_entity("e1", Hex(q=1, r=0, s=-1))

    # Try to place e2 (in radius 3) by e2's own action - should be blocked
    wasp_magnetic_state.current_actor_id = "e2"
    place_step = PlaceUnitStep(
        unit_id="e2", target_hex_arg=Hex(q=2, r=0, s=-2), is_mandatory=True
    )
    res = place_step.resolve(wasp_magnetic_state, {})
    assert res.abort_action is True, "Self-placement in radius should be blocked"
