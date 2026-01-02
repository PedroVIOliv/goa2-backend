from goa2.engine.steps import FastTravelStep, PlaceUnitStep
from goa2.domain.models import Hero, TeamColor, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.domain.board import Board, Zone
from goa2.domain.types import HeroID, UnitID, BoardEntityID

class MockGameState:
    def __init__(self):
        self.board = Board()
        self.entity_locations = {}
        self.teams = {}
        self.current_actor_id = None
        self.misc_entities = {}
        
    @property
    def unit_locations(self):
         # Shim for legacy code if any left in steps (though we refactored steps.py)
         # Steps.py now uses entity_locations directly.
         return self.entity_locations

    def get_unit(self, uid):
        # Mock wrapper
        for t in self.teams.values():
             for h in t.heroes:
                 if str(h.id) == str(uid): return h
             for m in t.minions:
                 if str(m.id) == str(uid): return m
        return None
        
    def get_hero(self, uid):
        return self.get_unit(uid)
        
    def get_entity(self, uid):
        return self.get_unit(uid)

    def place_entity(self, uid, hex_loc):
        self.entity_locations[str(uid)] = hex_loc
        tile = self.board.get_tile(hex_loc)
        if tile:
            tile.occupant_id = BoardEntityID(str(uid))

def test_fast_travel_success_same_zone():
    state = MockGameState()
    
    # Zone 1: Safe
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1)}, neighbors=["z2"])
    state.board.zones["z1"] = z1
    state.board.populate_tiles_from_zones()
    
    # Hero in Z1
    hero = Hero(id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={})
    state.teams[TeamColor.RED] = type("Team", (), {"heroes": [hero], "minions": []})()
    state.current_actor_id = "hero1"
    
    # Use unified placement
    state.place_entity("hero1", Hex(q=0,r=0,s=0))
    
    # No enemies in Z1
    
    step = FastTravelStep(unit_id="hero1")
    result = step.resolve(state, {})
    
    # Should find Safe Zone (Z1) and valid hex (Hex(1,0,-1)) which is empty
    # Since Hero occupies 0,0,0, only 1,0,-1 is valid. Auto-select.
    
    assert result.is_finished is True
    assert len(result.new_steps) == 1
    assert isinstance(result.new_steps[0], PlaceUnitStep)
    assert result.new_steps[0].target_hex_arg == Hex(q=1,r=0,s=-1)

def test_fast_travel_success_adjacent_zone():
    state = MockGameState()
    
    # Z1 (Start) -> Z2 (Dest)
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0)}, neighbors=["z2"])
    z2 = Zone(id="z2", hexes={Hex(q=0,r=1,s=-1), Hex(q=0,r=2,s=-2)}, neighbors=["z1"])
    state.board.zones = {"z1": z1, "z2": z2}
    state.board.populate_tiles_from_zones()
    
    hero = Hero(id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={})
    state.teams[TeamColor.RED] = type("Team", (), {"heroes": [hero], "minions": []})()
    
    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0,r=0,s=0))
    
    step = FastTravelStep(unit_id="hero1")
    result = step.resolve(state, {})
    
    # Z1 occupied by Hero. Z2 empty.
    # Valid Hexes: Only Z2's 2 hexes.
    
    assert result.requires_input is True
    assert result.input_request["type"] == "SELECT_HEX"
    assert "z2" in str(result.input_request["prompt"])
    assert len(result.input_request["valid_hexes"]) == 2

def test_fast_travel_fail_enemy_in_start():
    state = MockGameState()
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1)}, neighbors=[])
    state.board.zones = {"z1": z1}
    state.board.populate_tiles_from_zones()
    
    hero = Hero(id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={})
    enemy = Minion(id=UnitID("e1"), name="Enemy", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state.teams[TeamColor.RED] = type("Team", (), {"heroes": [hero], "minions": []})()
    state.teams[TeamColor.BLUE] = type("Team", (), {"heroes": [], "minions": [enemy]})()
    
    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0,r=0,s=0))
    state.place_entity("e1", Hex(q=1,r=0,s=-1)) # Enemy in same zone
    
    step = FastTravelStep(unit_id="hero1")
    result = step.resolve(state, {})
    
    # Should fail because Start Zone is not safe
    assert result.is_finished is True
    assert not result.new_steps # No move steps generated

def test_fast_travel_exclude_unsafe_dest():
    state = MockGameState()
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0)}, neighbors=["z2", "z3"])
    z2 = Zone(id="z2", hexes={Hex(q=10,r=0,s=-10)}, neighbors=["z1"]) # Safe
    z3 = Zone(id="z3", hexes={Hex(q=20,r=0,s=-20)}, neighbors=["z1"]) # Unsafe (Enemy)
    
    state.board.zones = {"z1": z1, "z2": z2, "z3": z3}
    state.board.populate_tiles_from_zones()
    
    hero = Hero(id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={})
    enemy = Minion(id=UnitID("e1"), name="Enemy", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state.teams[TeamColor.RED] = type("Team", (), {"heroes": [hero], "minions": []})()
    state.teams[TeamColor.BLUE] = type("Team", (), {"heroes": [], "minions": [enemy]})()
    
    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0,r=0,s=0))
    state.place_entity("e1", Hex(q=20,r=0,s=-20)) # Enemy in Z3
    
    step = FastTravelStep(unit_id="hero1")
    result = step.resolve(state, {})
    
    # Z1 is safe (no enemies). Occupied by self.
    # Z2 is safe. Empty.
    # Z3 is UNSAFE.
    
    # Only Z2 should be in valid options (Z1 has no empty hexes)
    
    assert result.is_finished is True # Auto-select Z2
    assert result.new_steps[0].target_hex_arg == Hex(q=10,r=0,s=-10)

def test_fast_travel_option_filtering():
    # Verify ResolveCardStep filters out Fast Travel if unsafe
    from goa2.engine.steps import ResolveCardStep
    from goa2.domain.models import ActionType, Card, CardTier, CardColor
    state = MockGameState()
    
    # 1. Setup Unsafe Zone (Enemy present)
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1)}, neighbors=[])
    state.board.zones = {"z1": z1}
    state.board.populate_tiles_from_zones()
    
    hero = Hero(id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={})
    
    # Card with FAST_TRAVEL
    card = Card(
        id="c1", name="Teleport", tier=CardTier.I, initiative=10,
        primary_action=ActionType.MOVEMENT, primary_action_value=3,
        secondary_actions={},
        color=CardColor.RED,
        effect_id="test_effect",
        effect_text="Teleport to safe zone.",
        is_facedown=False
    )
    hero.current_turn_card = card
    
    state.teams[TeamColor.RED] = type("Team", (), {"heroes": [hero], "minions": []})()
    
    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0,r=0,s=0))
    
    # Enemy makes zone unsafe
    enemy = Minion(id=UnitID("e1"), name="E1", type=MinionType.MELEE, team=TeamColor.BLUE)
    state.teams[TeamColor.BLUE] = type("Team", (), {"heroes": [], "minions": [enemy]})()
    state.place_entity("e1", Hex(q=1,r=0,s=-1))
    
    # Run Step
    step = ResolveCardStep(hero_id="hero1")
    result = step.resolve(state, {})
    
    # Verify that Fast Travel is indeed a secondary action on the card (added by validator)
    assert ActionType.FAST_TRAVEL in card.secondary_actions
    
    # Options should contain MOVEMENT and HOLD, but NOT FAST_TRAVEL
    assert result.requires_input
    opts = result.input_request.get("options", [])
    opt_ids = [o["id"] for o in opts]
    
    assert "MOVEMENT" in opt_ids
    assert "HOLD" in opt_ids
    assert "FAST_TRAVEL" not in opt_ids
    assert len(opt_ids) == 2

