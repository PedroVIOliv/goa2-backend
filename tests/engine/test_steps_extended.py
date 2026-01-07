import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    ActionType,
    Card,
    CardTier,
    CardColor,
)
from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.engine.steps import (
    LanePushStep,
    ResolveDisplacementStep,
    ResolveCombatStep,
    DefeatUnitStep,
    ResolveTieBreakerStep,
    ReactionWindowStep,
    CheckLanePushStep,
    MoveUnitStep,
    LogMessageStep,
    FinalizeHeroTurnStep,
    SelectStep,
    DrawCardStep,
    FastTravelSequenceStep,
    PlaceUnitStep,
    SwapUnitsStep,
    PushUnitStep,
    FastTravelStep,
)
from goa2.engine.handler import push_steps, process_resolution_stack


@pytest.fixture
def steps_state():
    board = Board()

    # Zones: RedBase <-> Mid <-> BlueBase
    red_base_hex = Hex(q=0, r=0, s=0)
    mid_hex = Hex(q=1, r=0, s=-1)
    blue_base_hex = Hex(q=2, r=0, s=-2)

    # Spawn points for Mid
    red_melee_spawn = SpawnPoint(
        location=mid_hex,
        team=TeamColor.RED,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )
    # Blue spawn blocked by a hero in the new zone logic test
    blue_melee_spawn = SpawnPoint(
        location=Hex(q=1, r=-1, s=0),
        team=TeamColor.BLUE,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )

    zones = {
        "RedBase": Zone(id="RedBase", hexes={red_base_hex}, neighbors=["Mid"]),
        "Mid": Zone(
            id="Mid",
            hexes={mid_hex, Hex(q=1, r=-1, s=0)},
            spawn_points=[red_melee_spawn, blue_melee_spawn],
            neighbors=["RedBase", "BlueBase"],
        ),
        "BlueBase": Zone(id="BlueBase", hexes={blue_base_hex}, neighbors=["Mid"]),
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
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[m2]),
        },
        entity_locations={},
        active_zone_id="RedBase",
    )
    # Use Unified Placement
    state.place_entity("h1", red_base_hex)
    state.place_entity("h2", blue_base_hex)

    return state


def test_fast_travel_step_scenarios(steps_state):
    # Setup: Clear enemies
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.remove_entity("h2")

    # Success path with Sequence
    ft_seq = FastTravelSequenceStep(unit_id="h1")
    push_steps(steps_state, [ft_seq])

    # Expand
    res = process_resolution_stack(steps_state)
    assert res is not None
    assert res["type"] == "SELECT_HEX"
    # Should have multiple options (1,0,-1) and (1,-1,0) in Mid
    assert len(res["valid_options"]) == 2

    # Auto travel case (Only one empty hex in safe zones)
    steps_state.execution_stack.clear()
    steps_state.place_entity("blocker", Hex(q=1, r=-1, s=0))
    push_steps(steps_state, [ft_seq])
    res_auto = process_resolution_stack(steps_state)
    # SelectStep with auto_select_if_one=False (default) still requests input if multiple hexes are candidate
    # But wait, FastTravelDestinationFilter should only allow (1,0,-1) now.
    assert res_auto is not None
    assert len(res_auto["valid_options"]) == 1
    assert res_auto["valid_options"][0] == Hex(q=1, r=0, s=-1)


def test_misc_steps(steps_state):
    log = LogMessageStep(message="Hello {name}")
    assert log.resolve(steps_state, {"name": "World"}).is_finished is True

    draw = DrawCardStep(hero_id="h1")
    assert draw.resolve(steps_state, {}).is_finished is True


def test_reaction_window_full(steps_state):
    # Setup hero with defense card
    h2 = steps_state.get_hero("h2")
    def_card = Card(
        id="def1",
        name="Shield",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        primary_action=ActionType.DEFENSE,
        primary_action_value=3,
        effect_id="none",
        effect_text="",
        initiative=1,
        is_facedown=False,
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
        id="sec1",
        name="Blink",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        secondary_actions={ActionType.DEFENSE: 2},
        effect_id="none",
        effect_text="",
        initiative=1,
        is_facedown=False,
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
    sp = SpawnPoint(
        location=Hex(q=0, r=0, s=0), team=TeamColor.RED, type=SpawnType.HERO
    )
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
    steps_state.board.get_tile(Hex(q=1, r=-1, s=0)).spawn_point = SpawnPoint(
        location=Hex(q=1, r=-1, s=0),
        team=TeamColor.RED,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )

    # No available minion in supply
    steps_state.remove_entity("m_red_1")
    old_minions = steps_state.teams[TeamColor.RED].minions
    steps_state.teams[TeamColor.RED].minions = []  # Empty supply
    assert rm.resolve(steps_state, {}).is_finished is True

    # Success respawn with input
    steps_state.teams[TeamColor.RED].minions = old_minions
    rm.pending_input = {"spawn_hex": {"q": 1, "r": 0, "s": -1}}
    assert rm.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["m_red_1"] == Hex(q=1, r=0, s=-1)

    # Error: Occupied
    rm.pending_input = {"spawn_hex": {"q": 1, "r": 0, "s": -1}}
    # m_red_1 is not on board yet (remove it)
    steps_state.remove_entity("m_red_1")
    steps_state.place_entity("blocker", Hex(q=1, r=0, s=-1))
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
    steps_state.place_entity(
        "h2", Hex(q=1, r=1, s=-2)
    )  # Not in straight line from (0,0,0)
    push_diag = PushUnitStep(target_id="h2")
    assert push_diag.resolve(steps_state, {}).is_finished is True

    # Hit board edge
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.place_entity("h2", Hex(q=2, r=0, s=-2))  # Far end
    push_edge = PushUnitStep(target_id="h2", distance=10)
    assert push_edge.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["h2"] == Hex(q=2, r=0, s=-2)  # Didn't move

    # Hit obstacle
    steps_state.place_entity("h1", Hex(q=0, r=0, s=0))
    steps_state.place_entity("h2", Hex(q=1, r=0, s=-1))
    steps_state.board.get_tile(Hex(q=2, r=0, s=-2)).is_terrain = True  # Obstacle
    push_obs = PushUnitStep(target_id="h2", distance=2)
    assert push_obs.resolve(steps_state, {}).is_finished is True
    assert steps_state.entity_locations["h2"] == Hex(q=1, r=0, s=-1)  # Blocked
