import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, ActionType, Card, CardTier, CardColor
from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.engine.steps import (
    LanePushStep, ResolveDisplacementStep, ResolveCombatStep, 
    DefeatUnitStep, ResolveTieBreakerStep, ReactionWindowStep,
    CheckLanePushStep, MoveUnitStep, LogMessageStep,
    FinalizeHeroTurnStep, SelectStep, DrawCardStep, DamageStep,
    FastTravelStep, PlaceUnitStep, SwapUnitsStep, PushUnitStep
)

@pytest.fixture
def steps_state():
    board = Board()
    
    # Zones: RedBase <-> Mid <-> BlueBase
    red_base_hex = Hex(q=0, r=0, s=0)
    mid_hex = Hex(q=1, r=0, s=-1)
    blue_base_hex = Hex(q=2, r=0, s=-2)
    
    # Spawn points for Mid
    red_melee_spawn = SpawnPoint(location=mid_hex, team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE)
    # Blue spawn blocked by a hero in the new zone logic test
    blue_melee_spawn = SpawnPoint(location=Hex(q=1, r=-1, s=0), team=TeamColor.BLUE, type=SpawnType.MINION, minion_type=MinionType.MELEE)
    
    zones = {
        "RedBase": Zone(id="RedBase", hexes={red_base_hex}, neighbors=["Mid"]),
        "Mid": Zone(id="Mid", hexes={mid_hex, Hex(q=1, r=-1, s=0)}, spawn_points=[red_melee_spawn, blue_melee_spawn], neighbors=["RedBase", "BlueBase"]),
        "BlueBase": Zone(id="BlueBase", hexes={blue_base_hex}, neighbors=["Mid"])
    }
    board.zones = zones
    board.lane = ["RedBase", "Mid", "BlueBase"]
    board.populate_tiles_from_zones()
    
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    
    # Minion supply
    m1 = Minion(id="m_red_1", name="M1", type=MinionType.MELEE, team=TeamColor.RED)
    m2 = Minion(id="m_blue_1", name="M2", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[m2])
        },
        entity_locations={},
        active_zone_id="RedBase"
    )
    # Use Unified Placement
    state.place_entity("h1", red_base_hex)
    state.place_entity("h2", blue_base_hex)
    
    return state

def test_lane_push_spawning_and_displacement(steps_state):
    # Setup: Phase is at RedBase. Losing team is RED (pushes towards BLUE).
    steps_state.active_zone_id = "Mid"
    
    # Put a hero on the Blue Spawn point in Mid to block it
    blue_spawn_hex = Hex(q=1, r=-1, s=0)
    steps_state.place_entity("h2", blue_spawn_hex)
    
    # Execute LanePush for BLUE losing (pushes towards BLUE BASE)
    # Mid (idx 1) -> target idx 2 (BlueBase)
    push_step = LanePushStep(losing_team=TeamColor.BLUE)
    result = push_step.resolve(steps_state, {})
    
    assert steps_state.active_zone_id == "BlueBase"
    
def test_lane_push_mid_spawning(steps_state):
    # RedBase -> Mid. Blue loses at RedBase (idx 0 -> target idx 1: Mid)
    steps_state.active_zone_id = "RedBase"
    push_step = LanePushStep(losing_team=TeamColor.BLUE)
    
    # Block Blue spawn in Mid
    blue_spawn_hex = Hex(q=1, r=-1, s=0)
    steps_state.place_entity("h2", blue_spawn_hex)
    
    result = push_step.resolve(steps_state, {})
    
    assert steps_state.active_zone_id == "Mid"
    # Red minion should have spawned at (1,0,-1)
    assert steps_state.entity_locations["m_red_1"] == Hex(q=1, r=0, s=-1)
    # Blue minion spawn was blocked by h2, so it should be in new_steps as ResolveDisplacement
    assert len(result.new_steps) == 1
    assert isinstance(result.new_steps[0], ResolveDisplacementStep)
    assert result.new_steps[0].displacements == [("m_blue_1", blue_spawn_hex)]

def test_combat_error_paths(steps_state):
    # ResolveCombatStep with no target in context
    combat = ResolveCombatStep(damage=5)
    result = combat.resolve(steps_state, {})
    assert result.is_finished is True
    assert not result.new_steps

    # DefeatUnitStep with non-existent victim
    defeat = DefeatUnitStep(victim_id="non_existent")
    result = defeat.resolve(steps_state, {})
    assert result.is_finished is True
    
    # DefeatUnitStep with non-existent killer (should still work for rewards, just no killer gold)
    steps_state.place_entity("m_red_1", Hex(q=1,r=0,s=-1))
    defeat_minion = DefeatUnitStep(victim_id="m_red_1", killer_id="ghost")
    result = defeat_minion.resolve(steps_state, {})
    assert result.is_finished is True
    assert len(result.new_steps) == 2 # Remove + Check Lane Push

def test_tie_breaker_complex(steps_state):
    # 3 heroes tied
    steps_state.teams[TeamColor.RED].heroes.append(Hero(id="h3", name="H3", team=TeamColor.RED, deck=[]))
    
    tie = ResolveTieBreakerStep(tied_hero_ids=["h1", "h2", "h3"])
    # Initial tie breaker is RED. RED should choose between h1 and h3.
    result = tie.resolve(steps_state, {})
    
    assert result.requires_input is True
    assert result.input_request["team"] == TeamColor.RED
    assert set(result.input_request["player_ids"]) == {"h1", "h3"}

    # Simulate RED choice h3
    tie.pending_input = {"selected_hero_id": "h3"}
    result_choice = tie.resolve(steps_state, {})
    assert result_choice.is_finished is True
    # new_steps should be [ResolveCardStep(h3), FinalizeHeroTurnStep(h3)]
    assert len(result_choice.new_steps) == 2
    assert result_choice.new_steps[0].hero_id == "h3"
    assert isinstance(result_choice.new_steps[1], FinalizeHeroTurnStep)

def test_reaction_window_edge_cases(steps_state):
    rw = ReactionWindowStep(target_player_key="target_id")
    steps_state.place_entity("h2", Hex(q=2, r=0, s=-2))
    
    # Invalid card_id in input
    ctx = {"target_id": "h2"}
    rw.pending_input = {"selected_card_id": "junk_card"}
    result = rw.resolve(steps_state, ctx)
    assert result.is_finished is True
    # Implementation sets def_val = 5 (Mock default) if card not found
    assert ctx["defense_value"] == 5

def test_check_lane_push_step(steps_state):
    # No push
    check = CheckLanePushStep()
    steps_state.active_zone_id = "Mid"
    # Add minions to Mid
    steps_state.place_entity("m_red_1", Hex(q=1, r=0, s=-1))
    steps_state.place_entity("m_blue_1", Hex(q=1, r=-1, s=0))
    
    result = check.resolve(steps_state, {})
    assert result.is_finished is True
    assert not result.new_steps
    
    # Trigger push (Red has 0 minions in Mid)
    steps_state.remove_entity("m_red_1")
    result_push = check.resolve(steps_state, {})
    assert len(result_push.new_steps) == 1
    assert isinstance(result_push.new_steps[0], LanePushStep)

def test_select_step_variations(steps_state):
    # Mandatory failure (no candidates)
    select_none = SelectStep(target_type="UNIT", prompt="Fail", is_mandatory=True, filters=[])
    steps_state.entity_locations = {} # Wipe locations
    res = select_none.resolve(steps_state, {})
    assert res.is_finished is True
    assert res.abort_action is True

    # Optional skip
    select_opt = SelectStep(target_type="UNIT", prompt="Skip", is_mandatory=False)
    res_opt = select_opt.resolve(steps_state, {})
    assert res_opt.is_finished is True
    assert res_opt.abort_action is False

    # Auto select if one
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    select_auto = SelectStep(target_type="UNIT", prompt="Auto", auto_select_if_one=True)
    ctx = {}
    res_auto = select_auto.resolve(steps_state, ctx)
    assert res_auto.is_finished is True
    assert ctx["selection"] == "h1"

    # Pending input with Hex conversion
    select_hex = SelectStep(target_type="HEX", prompt="Hex")
    select_hex.pending_input = {"selection": {"q": 1, "r": 0, "s": -1}}
    ctx_hex = {}
    res_hex = select_hex.resolve(steps_state, ctx_hex)
    assert res_hex.is_finished is True
    assert isinstance(ctx_hex["selection"], Hex)
    assert ctx_hex["selection"] == Hex(q=1, r=0, s=-1)

def test_move_unit_step_errors(steps_state):
    # No actor
    move_no_actor = MoveUnitStep()
    steps_state.current_actor_id = None
    assert move_no_actor.resolve(steps_state, {}).is_finished is True

    # No destination
    move_no_dest = MoveUnitStep()
    steps_state.current_actor_id = "h1"
    assert move_no_dest.resolve(steps_state, {}).is_finished is True

    # Invalid path
    move_blocked = MoveUnitStep(range_val=1)
    # Target is too far
    ctx = {"target_hex": Hex(q=10, r=10, s=-20)}
    assert move_blocked.resolve(steps_state, ctx).is_finished is True

def test_fast_travel_step_scenarios(steps_state):
    # Error: Not in zone
    ft = FastTravelStep(unit_id="h1")
    steps_state.place_entity("h1", Hex(q=100, r=100, s=-200)) # Out of bounds/No zone
    assert ft.resolve(steps_state, {}).is_finished is True

    # No safe zones (Enemy in RedBase)
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.place_entity("h2", Hex(q=0, r=0, s=0)) # Same hex = enemy in zone
    assert ft.resolve(steps_state, {}).is_finished is True
    
    # Success path: Clear enemies
    steps_state.remove_entity("h2")
    # h1 is at (0,0,0). 
    # NOTE: Since h2 was at (0,0,0), removing it cleared the tile. 
    # But h1 still thinks it is at (0,0,0). We must re-place h1 to ensure consistency for test.
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    
    # Ensure Mid has at least 2 empty spaces (done via setup or remove)
    
    # Previous tests might have left junk. But fixture returns clean state except h1/h2 placements.
    # Mid has (1,0,-1) and (1,-1,0). Both empty.

    res = ft.resolve(steps_state, {})
    # Should have multiple options (1,0,-1) and (1,-1,0) in Mid
    assert res.requires_input is True
    
    # Input selection
    ft.pending_input = {"selection": {"q": 1, "r": 0, "s": -1}}
    res_input = ft.resolve(steps_state, {})
    assert res_input.is_finished is True
    assert isinstance(res_input.new_steps[0], PlaceUnitStep)
    
    # Auto travel case (Only one empty hex in safe zones)
    # Block (1,-1,0)
    steps_state.place_entity("blocker", Hex(q=1, r=-1, s=0))
    ft.pending_input = None
    res_auto = ft.resolve(steps_state, {})
    assert res_auto.is_finished is True
    assert res_auto.new_steps[0].target_hex_arg == Hex(q=1, r=0, s=-1)
    
    # Invalid selection
    # To test invalid selection, we need multiple options again.
    steps_state.remove_entity("blocker")
    ft.pending_input = {"selection": {"q": 99, "r": 99, "s": -198}}
    res_invalid = ft.resolve(steps_state, {})
    assert res_invalid.requires_input is True

def test_misc_steps(steps_state):
    log = LogMessageStep(message="Hello {name}")
    assert log.resolve(steps_state, {"name": "World"}).is_finished is True

    draw = DrawCardStep(hero_id="h1")
    assert draw.resolve(steps_state, {}).is_finished is True

    dmg = DamageStep(target_key="missing", amount=1)
    assert dmg.resolve(steps_state, {}).is_finished is True

def test_reaction_window_full(steps_state):
    # Setup hero with defense card
    h2 = steps_state.get_hero("h2")
    def_card = Card(
        id="def1", name="Shield", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        primary_action=ActionType.DEFENSE, primary_action_value=3,
        effect_id="none", effect_text="", initiative=1
    )
    h2.hand = [def_card]
    
    rw = ReactionWindowStep(target_player_key="target_id")
    ctx = {"target_id": "h2"}
    
    # Not a hero skip
    ctx_minion = {"target_id": "m_blue_1"}
    assert rw.resolve(steps_state, ctx_minion).is_finished is True
    assert ctx_minion["defense_value"] == 0
    
    # Pass
    rw.pending_input = {"selected_card_id": "PASS"}
    res_pass = rw.resolve(steps_state, ctx)
    assert ctx["defense_value"] == 0
    
    # Use Primary Defense
    rw.pending_input = {"selected_card_id": "def1"}
    res_def = rw.resolve(steps_state, ctx)
    assert ctx["defense_value"] == 3
    
    # Secondary defense
    sec_card = Card(
        id="sec1", name="Blink", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        primary_action=ActionType.MOVEMENT, secondary_actions={ActionType.DEFENSE: 2},
        effect_id="none", effect_text="", initiative=1
    )
    h2.hand.append(sec_card)
    rw.pending_input = {"selected_card_id": "sec1"}
    rw.resolve(steps_state, ctx)
    assert ctx["defense_value"] == 2

def test_swap_and_place_errors(steps_state):
    # Swap error
    swap = SwapUnitsStep(unit_a_id="h1", unit_b_id="ghost")
    assert swap.resolve(steps_state, {}).is_finished is True
    
    # Place error (Occupied)
    place = PlaceUnitStep(unit_id="h2", target_hex_arg=Hex(q=0, r=0, s=0))
    # h1 is at (0,0,0) by default in fixture
    assert place.resolve(steps_state, {}).is_finished is True
    
    # Place missing actor
    place_no_actor = PlaceUnitStep(target_hex_arg=Hex(q=1, r=0, s=-1))
    steps_state.current_actor_id = None
    assert place_no_actor.resolve(steps_state, {}).is_finished is True

def test_respawn_hero_variations(steps_state):
    from goa2.engine.steps import RespawnHeroStep
    # No hero
    assert RespawnHeroStep(hero_id="ghost").resolve(steps_state, {}).is_finished is True
    
    # Hero already on board
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    assert RespawnHeroStep(hero_id="h1").resolve(steps_state, {}).is_finished is True
    steps_state.remove_entity("h1")
    
    # No empty spawn points
    # Fixture has spawn points in Mid. RedBase has none.
    # Active zone doesn't matter for RespawnHeroStep as it checks ALL board tiles for spawn points.
    # Let's remove all spawn points from board.
    steps_state.board.spawn_points = []
    for tile in steps_state.board.tiles.values():
        tile.spawn_point = None
    assert RespawnHeroStep(hero_id="h1").resolve(steps_state, {}).is_finished is True

    # Pass respawn
    rh = RespawnHeroStep(hero_id="h1")
    # Add a spawn point back
    sp = SpawnPoint(location=Hex(q=0, r=0, s=0), team=TeamColor.RED, type=SpawnType.HERO)
    steps_state.board.tiles[Hex(q=0, r=0, s=0)].spawn_point = sp
    rh.pending_input = {"choice": "PASS"}
    ctx = {}
    assert rh.resolve(steps_state, ctx).is_finished is True
    assert ctx.get("skipped_respawn") is True

    # Success respawn
    rh.pending_input = {"spawn_hex": {"q": 0, "r": 0, "s": 0}}
    assert rh.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["h1"] == Hex(q=0, r=0, s=0)

def test_respawn_minion_errors(steps_state):
    from goa2.engine.steps import RespawnMinionStep
    # No active zone
    steps_state.active_zone_id = None
    rm = RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE)
    assert rm.resolve(steps_state, {}).is_finished is True
    
    # Zone not found
    steps_state.active_zone_id = "GhostZone"
    assert rm.resolve(steps_state, {}).is_finished is True

def test_respawn_minion_variations(steps_state):
    from goa2.engine.steps import RespawnMinionStep
    steps_state.active_zone_id = "Mid"
    rm = RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE)
    
    # Max count reached
    steps_state.place_entity("m_red_1", Hex(q=1, r=0, s=-1))
    # Ensure Mid only has 1 spawn point for RED MELEE
    # (Done in fixture)
    assert rm.resolve(steps_state, {}).is_finished is True
    
    # Increase spawn count to allow respawn
    steps_state.board.get_tile(Hex(q=1, r=-1, s=0)).spawn_point = SpawnPoint(location=Hex(q=1, r=-1, s=0), team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE)
    
    # No available minion in supply
    steps_state.remove_entity("m_red_1")
    old_minions = steps_state.teams[TeamColor.RED].minions
    steps_state.teams[TeamColor.RED].minions = [] # Empty supply
    assert rm.resolve(steps_state, {}).is_finished is True
    
    # Success respawn with input
    steps_state.teams[TeamColor.RED].minions = old_minions
    rm.pending_input = {"spawn_hex": {"q": 1, "r": 0, "s": -1}}
    assert rm.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["m_red_1"] == Hex(q=1, r=0, s=-1)
    
    # Error: Occupied
    rm.pending_input = {"spawn_hex": {"q": 1, "r": 0, "s": -1}}
    steps_state.place_entity("blocker", Hex(q=1, r=0, s=-1))
    # m_red_1 is not on board yet (remove it)
    steps_state.remove_entity("m_red_1")
    assert rm.resolve(steps_state, {}).is_finished is True
    assert "m_red_1" not in steps_state.entity_locations

def test_push_unit_variations(steps_state):
    # No target loc
    push_no_target = PushUnitStep(target_id="ghost")
    assert push_no_target.resolve(steps_state, {}).is_finished is True

    # No source hex (current_actor is None)
    steps_state.current_actor_id = None
    steps_state.place_entity("h2", Hex(q=2, r=0, s=-2))
    push_no_src = PushUnitStep(target_id="h2")
    assert push_no_src.resolve(steps_state, {}).is_finished is True

    # Same hex error
    steps_state.current_actor_id = "h1"
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    push_same = PushUnitStep(target_id="h1")
    assert push_same.resolve(steps_state, {}).is_finished is True

    # Not straight line error
    steps_state.place_entity("h2", Hex(q=1, r=1, s=-2)) # Not in straight line from (0,0,0)
    push_diag = PushUnitStep(target_id="h2")
    assert push_diag.resolve(steps_state, {}).is_finished is True

    # Hit board edge
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.place_entity("h2", Hex(q=2, r=0, s=-2)) # Far end
    push_edge = PushUnitStep(target_id="h2", distance=10)
    assert push_edge.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["h2"] == Hex(q=2, r=0, s=-2) # Didn't move

    # Hit obstacle
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.place_entity("h2", Hex(q=1, r=0, s=-1))
    steps_state.board.get_tile(Hex(q=2, r=0, s=-2)).is_terrain = True # Obstacle
    push_obs = PushUnitStep(target_id="h2", distance=2)
    assert push_obs.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["h2"] == Hex(q=1, r=0, s=-1) # Blocked