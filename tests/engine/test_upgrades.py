import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, CardState, StatType, GamePhase
from goa2.engine.steps import EndPhaseCleanupStep, ResolveUpgradesStep, apply_hero_upgrade
from goa2.engine.handler import process_resolution_stack, push_steps

@pytest.fixture
def upgrade_state():
    board = Board()
    
    # Hero 1: 3 Gold, Level 1.
    # Costs: Level 2 (1), Level 3 (2). Total 3.
    # Should reach Level 3.
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, level=1, gold=3, deck=[])
    
    # Card Pool for H1
    r1 = Card(id="r1", name="Red I", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, primary_action_value=2, effect_id="e1", effect_text="e1")
    r2a = Card(id="r2a", name="Red II A", tier=CardTier.II, color=CardColor.RED, initiative=2, primary_action=ActionType.ATTACK, primary_action_value=3, effect_id="e2", effect_text="e2", item=StatType.ATTACK)
    r2b = Card(id="r2b", name="Red II B", tier=CardTier.II, color=CardColor.RED, initiative=3, primary_action=ActionType.ATTACK, primary_action_value=3, effect_id="e3", effect_text="e3", item=StatType.DEFENSE)
    
    b1 = Card(id="b1", name="Blue I", tier=CardTier.I, color=CardColor.BLUE, initiative=1, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e4", effect_text="e4")
    b2a = Card(id="b2a", name="Blue II A", tier=CardTier.II, color=CardColor.BLUE, initiative=2, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e5", effect_text="e5", item=StatType.RANGE)
    b2b = Card(id="b2b", name="Blue II B", tier=CardTier.II, color=CardColor.BLUE, initiative=3, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e6", effect_text="e6", item=StatType.MOVEMENT)

    g1 = Card(id="g1", name="Green I", tier=CardTier.I, color=CardColor.GREEN, initiative=1, primary_action=ActionType.MOVEMENT, primary_action_value=3, effect_id="e7", effect_text="e7")

    h1.deck = [r1, r2a, r2b, b1, b2a, b2b, g1]
    h1.hand = [r1, b1, g1]
    for c in h1.hand: c.state = CardState.HAND
    for c in h1.deck: 
        if c not in h1.hand: c.state = CardState.DECK

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        }
    )
    return state

def test_end_phase_level_up_calculation(upgrade_state):
    step = EndPhaseCleanupStep()
    push_steps(upgrade_state, [step])
    
    process_resolution_stack(upgrade_state)
    
    h1 = upgrade_state.get_hero("h1")
    assert h1.level == 3
    assert h1.gold == 0
    assert upgrade_state.pending_upgrades["h1"] == 2
    assert upgrade_state.phase == GamePhase.LEVEL_UP
    
    # Should have spawned ResolveUpgradesStep
    assert isinstance(upgrade_state.execution_stack[-1], ResolveUpgradesStep)

def test_resolve_upgrades_options(upgrade_state):
    # Setup pending state manually
    upgrade_state.pending_upgrades["h1"] = 2
    
    step = ResolveUpgradesStep()
    push_steps(upgrade_state, [step])
    
    req = process_resolution_stack(upgrade_state)
    assert req["type"] == "UPGRADE_PHASE"
    
    h1_data = req["players"]["h1"]
    assert h1_data["remaining"] == 2
    
    # Options should include Red II and Blue II (Lowest tier is I)
    options = h1_data["options"]
    colors = [o["color"] for o in options]
    assert CardColor.RED in colors
    assert CardColor.BLUE in colors
    assert CardColor.GREEN not in colors # No Green II in deck

def test_apply_upgrade_hand_and_items(upgrade_state):
    # 1. Apply Red Upgrade (r2a)
    apply_hero_upgrade(upgrade_state, "h1", "r2a")
    
    h1 = upgrade_state.get_hero("h1")
    
    # Hand Check
    hand_ids = [c.id for c in h1.hand]
    assert "r2a" in hand_ids
    assert "r1" not in hand_ids # Removed
    
    # Item Check (r2b was the pair)
    # r2b item is DEFENSE
    assert h1.items[StatType.DEFENSE] == 1
    
    # Pending count check
    # fixture didn't set it, so apply_hero_upgrade might have failed to decrement if missing
    # But wait, I didn't set it in this test. 
    # Let's set it.
    upgrade_state.pending_upgrades["h1"] = 2
    apply_hero_upgrade(upgrade_state, "h1", "b2a") # Second upgrade
    
    assert upgrade_state.pending_upgrades["h1"] == 1
    assert h1.items[StatType.MOVEMENT] == 1 # b2b tucked

def test_upgrade_loop_to_completion(upgrade_state):
    # Fully automated flow test
    step = EndPhaseCleanupStep()
    push_steps(upgrade_state, [step])
    
    # 1. End Phase -> Spawns ResolveUpgrades
    process_resolution_stack(upgrade_state)
    
    # 2. ResolveUpgrades -> Returns Request
    req = process_resolution_stack(upgrade_state)
    assert req["type"] == "UPGRADE_PHASE"
    
    # 3. Simulate Choice 1: Red
    apply_hero_upgrade(upgrade_state, "h1", "r2a")
    
    # 4. ResolveUpgrades again (since it's still on stack)
    req2 = process_resolution_stack(upgrade_state)
    assert req2 is not None
    assert req2["players"]["h1"]["remaining"] == 1
    
    # 5. Simulate Choice 2: Blue
    apply_hero_upgrade(upgrade_state, "h1", "b2a")
    
    # 6. ResolveUpgrades again -> All done -> Spawns RoundReset
    process_resolution_stack(upgrade_state)
    
    # 7. RoundReset runs
    process_resolution_stack(upgrade_state)
    
    assert upgrade_state.round == 2
    assert upgrade_state.phase == GamePhase.PLANNING
    assert not upgrade_state.pending_upgrades

def test_pity_coin_gain(upgrade_state):
    # Setup H1 with 0 Gold
    h1 = upgrade_state.get_hero("h1")
    h1.gold = 0
    h1.level = 1
    
    step = EndPhaseCleanupStep()
    push_steps(upgrade_state, [step])
    
    process_resolution_stack(upgrade_state)
    
    assert h1.level == 1
    assert h1.gold == 1
    assert upgrade_state.phase == GamePhase.PLANNING # No level up, resets round

def test_simultaneous_multi_player_upgrades(upgrade_state):
    # Setup H2 (Blue) with 1 gold (1 level up)
    # H1 already has 3 gold (2 level ups) from fixture
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, level=1, gold=1, deck=[])
    
    # H2 Deck
    b1 = Card(id="h2_b1", name="Blue I", tier=CardTier.I, color=CardColor.BLUE, initiative=1, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e4", effect_text="e4")
    b2a = Card(id="h2_b2a", name="Blue II A", tier=CardTier.II, color=CardColor.BLUE, initiative=2, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e5", effect_text="e5", item=StatType.RANGE)
    b2b = Card(id="h2_b2b", name="Blue II B", tier=CardTier.II, color=CardColor.BLUE, initiative=3, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e6", effect_text="e6", item=StatType.MOVEMENT)
    r1 = Card(id="h2_r1", name="Red I", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, primary_action_value=2, effect_id="e1", effect_text="e1")
    g1 = Card(id="h2_g1", name="Green I", tier=CardTier.I, color=CardColor.GREEN, initiative=1, primary_action=ActionType.MOVEMENT, primary_action_value=3, effect_id="e7", effect_text="e7")

    h2.deck = [b1, b2a, b2b, r1, g1]
    h2.hand = [b1, r1, g1]
    for c in h2.hand: c.state = CardState.HAND
    for c in h2.deck: 
        if c not in h2.hand: c.state = CardState.DECK
        
    upgrade_state.teams[TeamColor.BLUE].heroes.append(h2)

    # 1. Start End Phase
    push_steps(upgrade_state, [EndPhaseCleanupStep()])
    process_resolution_stack(upgrade_state)
    
    # Verify Pending Counts
    assert upgrade_state.pending_upgrades["h1"] == 2
    assert upgrade_state.pending_upgrades["h2"] == 1
    
    # 2. Get first broadcast request
    req = process_resolution_stack(upgrade_state)
    assert req["type"] == "UPGRADE_PHASE"
    assert "h1" in req["players"]
    assert "h2" in req["players"]
    
    # 3. Simulate H2 (1 level) picking their card
    apply_hero_upgrade(upgrade_state, "h2", "h2_b2a")
    
    # 4. Resolve again - H2 should be GONE from the broadcast, H1 still there with 2
    req2 = process_resolution_stack(upgrade_state)
    assert "h2" not in req2["players"]
    assert req2["players"]["h1"]["remaining"] == 2
    
    # 5. Simulate H1 first pick
    apply_hero_upgrade(upgrade_state, "h1", "r2a")
    
    # 6. Resolve again - H1 still there with 1
    req3 = process_resolution_stack(upgrade_state)
    assert req3["players"]["h1"]["remaining"] == 1
    
    # 7. Simulate H1 final pick
    apply_hero_upgrade(upgrade_state, "h1", "b2a")
    
    # 8. Resolve again - All done, should reset round
    process_resolution_stack(upgrade_state) # ResolveUpgrades finishes
    process_resolution_stack(upgrade_state) # RoundReset runs
    
    assert upgrade_state.round == 2
    assert upgrade_state.phase == GamePhase.PLANNING
    assert not upgrade_state.pending_upgrades
