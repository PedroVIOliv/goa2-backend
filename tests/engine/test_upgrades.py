import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import TeamColor, Team, Hero, Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.hex import Hex
from goa2.engine.mechanics import run_end_phase
from goa2.engine.actions import UpgradeCardCommand
from goa2.engine.phases import GamePhase
from goa2.domain.input import InputRequestType

@pytest.fixture
def upgrade_state():
    # Setup Board
    board = Board(
        zones={"z1": Zone(id="z1", hexes={Hex(q=0,r=0,s=0)})},
        lane=["z1"],
        tiles={}
    )
    board.populate_tiles_from_zones()
    
    # Setup Hero with Cards for Upgrade
    # Need Red I, Red II A, Red II B
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, level=1, gold=5, deck=[], hand=[]) # Enough for Lv 2 (cost 2)
    
    # Deck population
    c_red_1 = Card(id="r1", name="Red I", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="e1", effect_text="e1")
    c_red_2a = Card(id="r2a", name="Red II A", tier=CardTier.II, color=CardColor.RED, initiative=2, primary_action=ActionType.ATTACK, effect_id="e2", effect_text="e2")
    c_red_2b = Card(id="r2b", name="Red II B", tier=CardTier.II, color=CardColor.RED, initiative=3, primary_action=ActionType.ATTACK, effect_id="e3", effect_text="e3")
    
    h1.deck = [c_red_1, c_red_2a, c_red_2b]
    h1.hand = [c_red_1] # Start with lvl 1 in hand
    c_red_1.state = CardState.HAND
    
    # Setup Hero 2 for Simultaneous Test
    h2 = Hero(id="h2", name="Hero2", team=TeamColor.BLUE, level=1, gold=5, deck=[], hand=[])
    c_blue_1 = Card(id="b1", name="Blue I", tier=CardTier.I, color=CardColor.BLUE, initiative=1, primary_action=ActionType.SKILL, effect_id="e4", effect_text="e4")
    c_blue_2a = Card(id="b2a", name="Blue II A", tier=CardTier.II, color=CardColor.BLUE, initiative=2, primary_action=ActionType.SKILL, effect_id="e5", effect_text="e5")
    c_blue_2b = Card(id="b2b", name="Blue II B", tier=CardTier.II, color=CardColor.BLUE, initiative=3, primary_action=ActionType.SKILL, effect_id="e6", effect_text="e6")
    
    h2.deck = [c_blue_1, c_blue_2a, c_blue_2b]
    h2.hand = [c_blue_1]
    c_blue_1.state = CardState.HAND
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2])
        },
        active_zone_id="z1",
        phase=GamePhase.END_PHASE
    )
    return state

def test_level_up_trigger(upgrade_state):
    # Execute End Phase
    # Heroes have 5 gold. 
    # H1 Level 1 -> 2 (Cost 1). Remainder 4.
    # H1 Level 2 -> 3 (Cost 2). Remainder 2.
    # H1 Level 3 -> 4 (Cost 3). Remainder -1 (Not possible).
    # So H1 should reach Level 3.
    
    # H2 Level 1 -> 2 (Cost 1). Remainder 4.
    # ... Same logic.
    
    run_end_phase(upgrade_state)
    
    # Verify Level Up
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    h2 = upgrade_state.teams[TeamColor.BLUE].heroes[0]
    
    assert h1.level == 3
    assert h1.gold == 2 # 5 - 1 - 2 = 2
    
    # Verify Input Stack
    # H1 leveled 1->2 (Input) and 2->3 (Input). Total 2 requests.
    # H2 leveled 1->2 (Input) and 2->3 (Input). Total 2 requests.
    # Total stack size 4.
    assert len(upgrade_state.input_stack) == 4
    req_types = [r.request_type for r in upgrade_state.input_stack]
    assert all(r == InputRequestType.UPGRADE_CHOICE for r in req_types)

def test_pity_coin(upgrade_state):
    # Setup Hero with 0 Gold
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    h1.gold = 0
    
    run_end_phase(upgrade_state)
    
    assert h1.level == 1
    assert h1.gold == 1 # Pity Coin gained

def test_upgrade_execution(upgrade_state):
    # 1. Trigger Level Up
    run_end_phase(upgrade_state)
    
    # 2. Execute Command for H2 (Top of stack assumed, or we search)
    # Let's say we target H2's request specifically
    req = upgrade_state.input_stack[-1]
    actor_id = req.player_id
    
    # Identify which hero is 'actor_id'
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    h2 = upgrade_state.teams[TeamColor.BLUE].heroes[0]
    
    target_hero = h1 if actor_id == h1.id else h2
    chosen_card_id = "r2a" if target_hero == h1 else "b2a"
    
    cmd = UpgradeCardCommand(hero_id=target_hero.id, chosen_card_id=chosen_card_id)
    cmd.execute(upgrade_state)
    
    # 3. Verify Changes for Target Hero
    # Chosen Card -> Hand
    chosen = next(c for c in target_hero.deck if c.id == chosen_card_id)
    assert chosen.state == CardState.HAND
    assert chosen in target_hero.hand
    
    # Old Card -> RETIRED/Removed
    old_id = "r1" if target_hero == h1 else "b1"
    old = next(c for c in target_hero.deck if c.id == old_id)
    assert old.state == CardState.RETIRED
    assert old not in target_hero.hand
    
    # Other Option -> ITEM
    other_id = "r2b" if target_hero == h1 else "b2b"
    other = next(c for c in target_hero.deck if c.id == other_id)
    assert other.state == CardState.ITEM

def test_ultimate_unlock(upgrade_state):
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    h1.level = 7
    h1.gold = 10 # Plenty
    
    # Add Ultimate Card
    ult = Card(id="ult", name="Ultimate", tier=CardTier.IV, color=CardColor.PURPLE, initiative=0, primary_action=ActionType.SKILL, effect_id="u1", effect_text="u1")
    h1.deck.append(ult)
    
    # Run End Phase
    run_end_phase(upgrade_state)
    
    assert h1.level == 8
    
    # Verify Ultimate Unlocked auto
    assert ult.state == CardState.PASSIVE
    
    # Verify no input request for H1 (unless H2 leveled up too)
    # H2 is level 1, gold 5 -> Levels up to 2 -> Request.
    # Check inputs
    inputs_for_h1 = [r for r in upgrade_state.input_stack if r.player_id == h1.id]
    assert len(inputs_for_h1) == 0 # Auto unlock

def test_invalid_tier_upgrade(upgrade_state):
    # Setup H1 to level 2 -> Expect Tier II
    run_end_phase(upgrade_state)
    
    # H1 is now Level 2 (and 3 actually). Stack has Requests.
    # Find request for H1
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    
    # We want the request that asks for Level 2 Upgrade (Tier II)
    # Stack LIFO: [L2->3 Req, L1->2 Req] (if processed in order)
    # Actually mechanics implementation appends:
    # L1->2: Append Req 1
    # L2->3: Append Req 2
    # Stack: [Req 1, Req 2]
    # We can pop from Top or pick specific. Command validates inputs[-1].
    # Let's target the TOP request.
    
    top_req = upgrade_state.input_stack[-1]
    
    # Whatever the top request is, it expects a specific Tier.
    expected_tier = top_req.context["tier"]
    target_hero_id = top_req.player_id
    
    # Find the hero object
    target_hero = h1 if target_hero_id == h1.id else upgrade_state.teams[TeamColor.BLUE].heroes[0]
    
    # Let's try to choose a card of DIFFERENT Tier.
    c_red_3 = Card(id="r3", name="Red III", tier=CardTier.III, color=CardColor.RED, initiative=4, primary_action=ActionType.ATTACK, effect_id="e7", effect_text="e7")
    target_hero.deck.append(c_red_3)
    
    # Ensure current actor matches request
    if expected_tier == CardTier.II:
         cmd = UpgradeCardCommand(hero_id=target_hero_id, chosen_card_id="r3") # Tier III
         with pytest.raises(ValueError, match="Invalid Tier"):
             cmd.execute(upgrade_state)

def test_simultaneous_upgrade_out_of_order(upgrade_state):
    # Setup H1 and H2 levelling up
    run_end_phase(upgrade_state)
    
    # Validation: Stack has 2 requests. 
    # Usually: [ReqH1, ReqH2] (or vice versa depending on team iteration order)
    # mechanics.py iterates teams then heroes.
    # Teams: Red, Blue.
    # H1 (Red) pushed first. H2 (Blue) pushed second.
    # Stack: [ReqH1, ReqH2] (Top is H2)
    
    # Confirm Stack Order
    assert len(upgrade_state.input_stack) == 4 # Because of multi-level from 1->2 and 2->3
    
    # H1 Leveled 1->2 (Req1), 1->3 (Req2)
    # H2 Leveled 1->2 (Req3), 1->3 (Req4)
    # Order depends on loop.
    # Actually:
    # Loop Red Team -> Hero 1:
    #   While loop:
    #      Level 2 -> Push Req1
    #      Level 3 -> Push Req2
    # Loop Blue Team -> Hero 2:
    #   While loop:
    #      Level 2 -> Push Req3
    #      Level 3 -> Push Req4
    # Stack: [Req1, Req2, Req3, Req4 (Top)]
    
    req1 = upgrade_state.input_stack[0] # H1
    req4 = upgrade_state.input_stack[3] # H2
    
    assert req1.player_id == upgrade_state.teams[TeamColor.RED].heroes[0].id
    assert req4.player_id == upgrade_state.teams[TeamColor.BLUE].heroes[0].id
    
    # Test: Execute H1's upgrade (Req2 - Level 3) FIRST (Out of Order)
    # Wait, we can target Req1 (Level 2) or Req2 (Level 3)?
    # Since they are for the SAME hero, does order matter?
    # Logic: "Selects specific request that matches".
    # If we command "Upgrade to Tier II", we match the Req for Tier II.
    
    target_hero_id = req1.player_id
    
    # Try to resolve Tier II upgrade for H1. (This corresponds to Req1).
    # This is at index 0 (Bottom of stack).
    
    chosen_card_id = "r2a" # Tier II
    cmd = UpgradeCardCommand(hero_id=target_hero_id, chosen_card_id=chosen_card_id)
    cmd.execute(upgrade_state)
    
    # Verify:
    # 1. stack size reduced by 1
    assert len(upgrade_state.input_stack) == 3
    # 2. H1 still has 1 request pending (Req2)
    inputs_h1 = [r for r in upgrade_state.input_stack if r.player_id == target_hero_id]
    assert len(inputs_h1) == 1
    # 3. H1 has card
    h1 = upgrade_state.teams[TeamColor.RED].heroes[0]
    assert any(c.id == chosen_card_id for c in h1.hand)
    
    # Test: Execute H2's upgrade (Top of stack) - Should still work
    target_hero_2_id = req4.player_id
    chosen_card_2_id = "b2a"
    cmd2 = UpgradeCardCommand(hero_id=target_hero_2_id, chosen_card_id=chosen_card_2_id)
    cmd2.execute(upgrade_state)
    
    assert len(upgrade_state.input_stack) == 2

