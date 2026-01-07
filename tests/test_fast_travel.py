from goa2.engine.steps import FastTravelSequenceStep, PlaceUnitStep, SelectStep
from goa2.domain.models import Hero, TeamColor, Minion, MinionType, Team, ActionType
from goa2.domain.hex import Hex
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.types import HeroID, UnitID, BoardEntityID
from goa2.domain.state import GameState
from goa2.engine.handler import process_resolution_stack, push_steps


def setup_base_state():
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id=None,
    )
    return state


def test_fast_travel_success_same_zone():
    state = setup_base_state()

    # Zone 1: Safe
    z1 = Zone(
        id="z1", hexes={Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}, neighbors=["z2"]
    )
    state.board.zones["z1"] = z1
    state.board.populate_tiles_from_zones()

    # Hero in Z1
    hero = Hero(
        id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={}
    )
    state.teams[TeamColor.RED].heroes.append(hero)
    state.current_actor_id = "hero1"

    state.place_entity("hero1", Hex(q=0, r=0, s=0))

    step = FastTravelSequenceStep(unit_id="hero1")
    push_steps(state, [step])

    # First process expands FastTravelSequenceStep into SelectStep
    req = process_resolution_stack(state)

    # Should find Safe Zone (Z1) and valid hex (Hex(1,0,-1)) which is empty
    # SelectStep returns input request
    assert req is not None
    assert req["type"] == "SELECT_HEX"
    assert Hex(q=1, r=0, s=-1) in req["valid_options"]


def test_fast_travel_success_adjacent_zone():
    state = setup_base_state()

    # Z1 (Start) -> Z2 (Dest)
    z1 = Zone(id="z1", hexes={Hex(q=0, r=0, s=0)}, neighbors=["z2"])
    z2 = Zone(
        id="z2", hexes={Hex(q=0, r=1, s=-1), Hex(q=0, r=2, s=-2)}, neighbors=["z1"]
    )
    state.board.zones = {"z1": z1, "z2": z2}
    state.board.populate_tiles_from_zones()

    hero = Hero(
        id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={}
    )
    state.teams[TeamColor.RED].heroes.append(hero)

    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0, r=0, s=0))

    step = FastTravelSequenceStep(unit_id="hero1")
    push_steps(state, [step])

    req = process_resolution_stack(state)

    assert req is not None
    assert req["type"] == "SELECT_HEX"
    assert len(req["valid_options"]) == 2  # Z2's hexes


def test_fast_travel_fail_enemy_in_start():
    state = setup_base_state()
    z1 = Zone(id="z1", hexes={Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}, neighbors=[])
    state.board.zones = {"z1": z1}
    state.board.populate_tiles_from_zones()

    hero = Hero(
        id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={}
    )
    enemy = Minion(
        id=UnitID("e1"), name="Enemy", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state.teams[TeamColor.RED].heroes.append(hero)
    state.teams[TeamColor.BLUE].minions.append(enemy)

    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0, r=0, s=0))
    state.place_entity("e1", Hex(q=1, r=0, s=-1))  # Enemy in same zone

    step = FastTravelSequenceStep(unit_id="hero1")
    push_steps(state, [step])

    # Should expand and then SelectStep should finish with "No candidates" because start zone is unsafe
    # Wait, SelectStep returns finished=True if no candidates and mandatory=False
    req = process_resolution_stack(state)

    assert req is None  # No input requested because no valid options
    assert state.entity_locations["hero1"] == Hex(q=0, r=0, s=0)


def test_fast_travel_exclude_unsafe_dest():
    state = setup_base_state()
    z1 = Zone(id="z1", hexes={Hex(q=0, r=0, s=0)}, neighbors=["z2", "z3"])
    z2 = Zone(id="z2", hexes={Hex(q=10, r=0, s=-10)}, neighbors=["z1"])  # Safe
    z3 = Zone(
        id="z3", hexes={Hex(q=20, r=0, s=-20)}, neighbors=["z1"]
    )  # Unsafe (Enemy)

    state.board.zones = {"z1": z1, "z2": z2, "z3": z3}
    state.board.populate_tiles_from_zones()

    hero = Hero(
        id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={}
    )
    enemy = Minion(
        id=UnitID("e1"), name="Enemy", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state.teams[TeamColor.RED].heroes.append(hero)
    state.teams[TeamColor.BLUE].minions.append(enemy)

    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0, r=0, s=0))
    state.place_entity("e1", Hex(q=20, r=0, s=-20))  # Enemy in Z3

    step = FastTravelSequenceStep(unit_id="hero1")
    push_steps(state, [step])

    req = process_resolution_stack(state)

    # Only Z2 should be in valid options
    assert req is not None
    assert len(req["valid_options"]) == 1
    assert req["valid_options"][0] == Hex(q=10, r=0, s=-10)


def test_fast_travel_option_filtering():
    from goa2.engine.steps import ResolveCardStep
    from goa2.domain.models import Card, CardTier, CardColor

    state = setup_base_state()

    z1 = Zone(id="z1", hexes={Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}, neighbors=[])
    state.board.zones = {"z1": z1}
    state.board.populate_tiles_from_zones()

    hero = Hero(
        id=HeroID("hero1"), name="H1", team=TeamColor.RED, deck=[], hand=[], items={}
    )

    card = Card(
        id="c1",
        name="Teleport",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        secondary_actions={ActionType.FAST_TRAVEL: 0},
        color=CardColor.RED,
        effect_id="test_effect",
        effect_text="Teleport to safe zone.",
        is_facedown=False,
    )
    hero.current_turn_card = card
    state.teams[TeamColor.RED].heroes.append(hero)

    state.current_actor_id = "hero1"
    state.place_entity("hero1", Hex(q=0, r=0, s=0))

    # Enemy makes zone unsafe
    enemy = Minion(
        id=UnitID("e1"), name="E1", type=MinionType.MELEE, team=TeamColor.BLUE
    )
    state.teams[TeamColor.BLUE].minions.append(enemy)
    state.place_entity("e1", Hex(q=1, r=0, s=-1))

    # Run Step
    step = ResolveCardStep(hero_id="hero1")
    push_steps(state, [step])
    result = process_resolution_stack(state)

    # Options should contain MOVEMENT and HOLD, but NOT FAST_TRAVEL
    assert result is not None
    opts = result.get("options", [])
    opt_ids = [o["id"] for o in opts]

    assert "MOVEMENT" in opt_ids
    assert "FAST_TRAVEL" not in opt_ids
