import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, Card, CardTier, CardColor, ActionType, StatType, EffectType, EffectScope, Shape, AffectsFilter
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.stats import get_computed_stat
import goa2.scripts.rogue_effects # Register rogue effects

@pytest.fixture
def rogue_state():
    board = Board()
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1), Hex(q=2,r=0,s=-2), Hex(q=3,r=0,s=-3)}, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()
    
    # Rogue at 0,0,0
    hero = Hero(id="rogue", name="Rogue", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="venom_strike",
        name="Venom Strike",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=6,
        primary_action=ActionType.SKILL,
        primary_action_value=None, # Must be None for SKILL
        secondary_actions={ActionType.MOVEMENT: 2},
        effect_id="venom_strike",
        effect_text="Attack. This Round: Target has -1 Attack, -1 Defense, -1 Initiative.",
        is_facedown=False
    )
    hero.current_turn_card = card
    
    # Enemy Hero at 1,0,-1 (Range 1)
    victim = Hero(id="victim", name="Victim", team=TeamColor.BLUE, deck=[], level=1)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[victim], minions=[])
        },
        turn=1,
        round=1
    )
    # Use Unified Placement
    state.place_entity("rogue", Hex(q=0,r=0,s=0))
    state.place_entity("victim", Hex(q=1,r=0,s=-1))
    state.current_actor_id = "rogue"
    
    return state

def test_venom_strike_applies_debuffs(rogue_state):
    # 1. Start ResolveCardStep
    push_steps(rogue_state, [ResolveCardStep(hero_id="rogue")])
    
    # 2. CHOOSE_ACTION
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    # 3. Select SKILL (Venom Strike)
    rogue_state.execution_stack[-1].pending_input = {"choice_id": "SKILL"}
    
    # 4. ResolveCardStep -> ResolveCardTextStep -> AttackSequenceStep -> SelectStep
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "SELECT_UNIT"
    assert "victim" in req["valid_options"]
    
    # 5. Provide Input: Select victim
    rogue_state.execution_stack[-1].pending_input = {"selection": "victim"}
    
    # 6. SelectStep finishes -> spawns ReactionWindowStep
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    
    # 7. Provide Input: PASS reaction
    rogue_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}
    
    # 8. ReactionWindowStep finishes -> spawns ResolveCombatStep
    # ResolveCombatStep finishes -> victim defeated (DefeatUnitStep)
    # BUT wait, ResolveCombatStep deals damage. If victim is defeated, can they still have modifiers?
    # Actually, DefeatUnitStep removes from board. 
    # Let's make the victim a hero with high level so they don't necessarily get removed if they have life counters?
    # Actually, currently DefeatUnitStep always removes from board.
    
    # Let's check victim stats before combat finishes if possible, 
    # OR make sure they survive (but ResolveCombatStep currently is binary: blocked or defeated).
    
    # Let's look at ResolveCombatStep logic in src/goa2/engine/steps.py:
    # it spawns DefeatUnitStep if attack hits.
    
    # In Goa2, units are usually removed when defeated. 
    # If a hero is defeated, they are removed.
    
    # Let's see if we can apply modifiers even if they are removed? 
    # GameState.active_modifiers still has them.
    
    process_resolution_stack(rogue_state)
    
    # 9. Verify Modifiers on victim
    # Even if victim is removed from board, they are still in state.get_hero("victim")
    
    # Wait, AttackSequenceStep finishes ResolveCombatStep, 
    # then the VenomStrikeEffect continues with CreateModifierSteps.
    
    # Check stats
    # Base attack is usually 0 if not specified in Hero model? 
    # Let's check Hero model.
    
    # Actually, get_computed_stat uses base_value parameter.
    
    att = get_computed_stat(rogue_state, "victim", StatType.ATTACK, base_value=3)
    dfe = get_computed_stat(rogue_state, "victim", StatType.DEFENSE, base_value=3)
    ini = get_computed_stat(rogue_state, "victim", StatType.INITIATIVE, base_value=3)
    
    assert att == 2
    assert dfe == 2
    assert ini == 2

def test_slippery_ground_limits_movement(rogue_state):
    # Setup card for Slippery Ground
    card = Card(
        id="slippery_ground",
        name="Slippery Ground",
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="slippery_ground",
        effect_text="This Turn: Adjacent enemies can only move up to 1 space.",
        is_facedown=False
    )
    rogue_state.get_hero("rogue").current_turn_card = card
    
    # Victim is already at (1, 0, -1), which is adjacent to Rogue at (0, 0, 0)
    
    # 1. Start ResolveCardStep
    push_steps(rogue_state, [ResolveCardStep(hero_id="rogue")])
    
    # 2. CHOOSE_ACTION
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    # 3. Select SKILL (Slippery Ground)
    rogue_state.execution_stack[-1].pending_input = {"choice_id": "SKILL"}
    
    # 4. Resolve steps
    process_resolution_stack(rogue_state)
    
    # 5. Verify effect is active in state
    assert len(rogue_state.active_effects) == 1
    assert rogue_state.active_effects[0].effect_type == EffectType.MOVEMENT_ZONE
    
    # 6. Check victim movement validation
    # Victim tries to move 2 spaces. Current loc (1, 0, -1). Target (3, -1, -2).
    # validation = rogue_state.validator.can_move(rogue_state, "victim", 2)
    # assert validation.allowed is False
    # assert "Movement limited to 1" in validation.reason
    
    # Use MoveUnitStep to verify it blocks
    from goa2.engine.steps import MoveUnitStep
    rogue_state.current_actor_id = "victim"
    move_step = MoveUnitStep(unit_id="victim", destination_key="target", range_val=2, is_mandatory=True)
    context = {"target": Hex(q=3, r=-1, s=-2)}
    
    res = move_step.resolve(rogue_state, context)
    assert res.abort_action is True
    
    # Target 1 space away should be allowed
    move_step_1 = MoveUnitStep(unit_id="victim", destination_key="target", range_val=1, is_mandatory=True)
    context_1 = {"target": Hex(q=2, r=0, s=-2)}
    res_1 = move_step_1.resolve(rogue_state, context_1)
    assert res_1.abort_action is False

def test_magnetic_dagger_prevents_placement(rogue_state):
    # Setup card for Magnetic Dagger
    card = Card(
        id="magnetic_dagger",
        name="Magnetic Dagger",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="magnetic_dagger",
        effect_text="Attack. This Turn: Enemy heroes in Radius 3 cannot be placed or swapped by enemy actions.",
        is_facedown=False
    )
    rogue_state.get_hero("rogue").current_turn_card = card
    
    # 1. Start ResolveCardStep
    push_steps(rogue_state, [ResolveCardStep(hero_id="rogue")])
    
    # 2. CHOOSE_ACTION
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    # 3. Select SKILL (Magnetic Dagger)
    rogue_state.execution_stack[-1].pending_input = {"choice_id": "SKILL"}
    
    # 4. Resolve steps until SELECT_UNIT (Attack Target)
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "SELECT_UNIT"
    rogue_state.execution_stack[-1].pending_input = {"selection": "victim"}
    
    # 5. Resolve steps until SELECT_CARD_OR_PASS (Reaction)
    req = process_resolution_stack(rogue_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    rogue_state.execution_stack[-1].pending_input = {"selected_card_id": "PASS"}
    
    # 6. Finish resolution
    process_resolution_stack(rogue_state)
    
    # 7. Verify effect is active
    assert any(e.effect_type == EffectType.PLACEMENT_PREVENTION for e in rogue_state.active_effects)
    
    # IMPORTANT: Victim was defeated and removed from board in step 6.
    # For spatial effects to work, the target hex of the unit must be within radius.
    # We re-place victim to test displacement prevention.
    rogue_state.place_entity("victim", Hex(q=1, r=0, s=-1))
    
    # 8. Try to place victim by Rogue (Caster)
    # This should be ALLOWED (Rogue is not blocked by their own effect)
    rogue_state.current_actor_id = "rogue"
    from goa2.engine.steps import PlaceUnitStep
    place_step = PlaceUnitStep(unit_id="victim", target_hex_arg=Hex(q=3, r=0, s=-3), is_mandatory=True)
    
    res = place_step.resolve(rogue_state, {})
    assert res.abort_action is False
    
    # 9. Try to place victim by Victim (Enemy of Caster)
    # This should be BLOCKED (Enemy actions are blocked)
    # Note: Victim is now at (3, 0, -3) from previous step. We try to move them elsewhere.
    rogue_state.current_actor_id = "victim"
    place_step_blue = PlaceUnitStep(unit_id="victim", target_hex_arg=Hex(q=2, r=0, s=-2), is_mandatory=True)
    
    res_blue = place_step_blue.resolve(rogue_state, {})
    assert res_blue.abort_action is True
