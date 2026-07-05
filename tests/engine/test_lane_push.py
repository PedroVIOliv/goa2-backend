import pytest

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    GamePhase,
    Hero,
    Minion,
    MinionType,
    PassiveTrigger,
    Team,
    TeamColor,
)
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.domain.types import UnitID
from goa2.engine.handler import process_stack, push_steps, submit_input
from goa2.engine.map_logic import get_push_target_zone_id
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.steps import (
    CheckLanePushStep,
    DefeatUnitStep,
    EndPhaseStep,
    FinalizeHeroTurnStep,
    FindNextActorStep,
    MayRepeatNTimesStep,
    PlaceUnitStep,
    ReturnMinionToZoneStep,
)


def create_minion(id_str, team):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=MinionType.MELEE)


@pytest.fixture
def push_state():
    """5-zone lane: RedBase -> RedBeach -> Mid -> BlueBeach -> BlueBase"""
    from goa2.domain.tile import Tile

    board = Board()
    board.lane = ["z_red_base", "z_red_beach", "z_mid", "z_blue_beach", "z_blue_base"]

    mid_hexes = [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0)]
    red_beach_hexes = [Hex(q=-1, r=0, s=1), Hex(q=-1, r=1, s=0)]
    blue_beach_hexes = [Hex(q=2, r=-1, s=-1), Hex(q=2, r=0, s=-2)]

    board.zones["z_red_base"] = Zone(id="z_red_base", name="Red Base", hexes=set())
    board.zones["z_red_beach"] = Zone(
        id="z_red_beach", name="Red Beach", hexes=set(red_beach_hexes)
    )
    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    board.zones["z_blue_beach"] = Zone(
        id="z_blue_beach", name="Blue Beach", hexes=set(blue_beach_hexes)
    )
    board.zones["z_blue_base"] = Zone(id="z_blue_base", name="Blue Base", hexes=set())

    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    for h in red_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_red_beach")
    for h in blue_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_blue_beach")

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        active_zone_id="z_mid",
        wave_counter=5,
    )
    return state


def test_end_phase_push_trigger(push_state):
    """
    Minion Battle at Mid: Red 0 vs Blue 1.
    Red Loses. Push towards Red Beach.
    """
    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    _ = process_stack(push_state).input_request

    assert push_state.wave_counter == 4
    assert push_state.active_zone_id == "z_red_beach"
    assert m_blue.id not in push_state.unit_locations


def test_combat_defeat_waits_until_post_action_cleanup_to_push_lane(push_state):
    """
    Defeating the last enemy minion removes it immediately but does not push
    the lane until the action boundary cleanup runs.
    """
    m_red = create_minion("r1", TeamColor.RED)
    m_blue = create_minion("b1", TeamColor.BLUE)

    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)

    push_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))
    push_state.move_unit(m_blue.id, Hex(q=1, r=-1, s=0))

    step = DefeatUnitStep(victim_id=m_blue.id, killer_id=m_red.id)
    push_steps(push_state, [step])
    _ = process_stack(push_state).input_request

    assert m_blue.id not in push_state.unit_locations
    assert push_state.active_zone_id == "z_mid"
    assert push_state.wave_counter == 5


def test_finalize_queues_lane_push_check_after_return_minions(push_state):
    result = FinalizeHeroTurnStep(hero_id="missing_hero").resolve(
        push_state, push_state.execution_context
    )

    assert [type(step) for step in result.new_steps] == [
        ReturnMinionToZoneStep,
        CheckLanePushStep,
        FindNextActorStep,
    ]


def test_repeat_prompt_checks_lane_push_before_offering_repeat(push_state):
    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))

    push_state.current_actor_id = "hero_actor"
    repeat = MayRepeatNTimesStep(steps_template=[], max_repeats=1)
    push_steps(push_state, [repeat])

    result = process_stack(push_state)

    assert result.input_request is not None
    assert push_state.active_zone_id == "z_blue_beach"
    assert push_state.wave_counter == 4


def test_repeat_n_checks_lane_push_before_each_iteration(push_state):
    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))

    push_state.current_actor_id = "hero_actor"
    repeat = MayRepeatNTimesStep(
        steps_template=[PlaceUnitStep(unit_id=str(m_red.id), target_hex_arg=Hex(q=2, r=-1, s=-1))],
        max_repeats=2,
    )
    push_steps(push_state, [repeat])

    first_prompt = process_stack(push_state)
    assert first_prompt.input_request is not None
    assert push_state.active_zone_id == "z_blue_beach"

    submit_input(push_state, {"selection": "YES"})
    second_result = process_stack(push_state)

    assert second_result.input_request is None
    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.winner == TeamColor.RED


def _test_card(
    card_id: str,
    effect_id: str,
    *,
    primary_action: ActionType = ActionType.ATTACK,
    primary_action_value: int | None = 2,
    tier: CardTier = CardTier.I,
    color: CardColor = CardColor.RED,
) -> Card:
    return Card(
        id=card_id,
        name=card_id,
        tier=tier,
        color=color,
        primary_action=primary_action,
        primary_action_value=primary_action_value,
        secondary_actions={},
        effect_id=effect_id,
        effect_text="",
        initiative=10,
        is_facedown=False,
    )


def test_flurry_of_blows_repeat_starts_with_lane_push_check(push_state):
    from goa2.scripts.min_effects import FlurryOfBlowsEffect

    source_card = _test_card("crane", "crane_stance")
    hero = Hero(
        id="hero_min",
        name="Min",
        team=TeamColor.RED,
        deck=[],
        current_turn_card=source_card,
        level=8,
    )
    ultimate = _test_card(
        "flurry",
        "flurry_of_blows",
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        tier=CardTier.IV,
        color=CardColor.PURPLE,
    )

    steps = FlurryOfBlowsEffect().get_passive_steps(
        push_state,
        hero,
        ultimate,
        PassiveTrigger.AFTER_ATTACK,
        {
            "attack_effect_id": "crane_stance",
            "attack_card_id": source_card.id,
            "defender_id": "b1",
        },
    )

    assert isinstance(steps[0], CheckLanePushStep)


def test_cloak_and_daggers_repeat_starts_with_lane_push_check(push_state):
    from goa2.scripts.tigerclaw_effects import CloakAndDaggersEffect

    hero = Hero(id="hero_tigerclaw", name="Tigerclaw", team=TeamColor.RED, deck=[], level=8)
    ultimate = _test_card(
        "cloak",
        "cloak_and_daggers",
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        tier=CardTier.IV,
        color=CardColor.PURPLE,
    )

    steps = CloakAndDaggersEffect().get_passive_steps(
        push_state,
        hero,
        ultimate,
        PassiveTrigger.AFTER_BASIC_ACTION,
        {
            "basic_action_type": ActionType.ATTACK.value,
            "basic_action_value": 2,
            "last_combat_target": "b1",
        },
    )

    assert isinstance(steps[0], CheckLanePushStep)


def test_last_push_victory(push_state):
    """
    Wave Counter = 1. Push triggers LAST_PUSH game over.
    """
    push_state.wave_counter = 1

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    _ = process_stack(push_state).input_request

    assert push_state.wave_counter == 0
    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.victory_condition == "LAST_PUSH"


def test_lane_push_spawns_minions_in_new_zone():
    """
    After a lane push from Mid, minions should spawn at the new Beach zone's spawn points.
    """
    from goa2.domain.tile import Tile

    board = Board()
    board.lane = ["z_red_base", "z_red_beach", "z_mid", "z_blue_beach", "z_blue_base"]

    mid_hexes = [Hex(q=0, r=0, s=0)]
    red_beach_hex_1 = Hex(q=-2, r=1, s=1)
    red_beach_hex_2 = Hex(q=-3, r=1, s=2)
    red_beach_hexes = [red_beach_hex_1, red_beach_hex_2]

    red_spawn_1 = SpawnPoint(
        location=red_beach_hex_1,
        team=TeamColor.RED,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )
    red_spawn_2 = SpawnPoint(
        location=red_beach_hex_2,
        team=TeamColor.BLUE,
        type=SpawnType.MINION,
        minion_type=MinionType.MELEE,
    )

    board.zones["z_red_base"] = Zone(id="z_red_base", name="Red Base", hexes=set())
    board.zones["z_red_beach"] = Zone(
        id="z_red_beach",
        name="Red Beach",
        hexes=set(red_beach_hexes),
        spawn_points=[red_spawn_1, red_spawn_2],
    )
    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    board.zones["z_blue_beach"] = Zone(id="z_blue_beach", name="Blue Beach", hexes=set())
    board.zones["z_blue_base"] = Zone(id="z_blue_base", name="Blue Base", hexes=set())

    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    for h in red_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_red_beach")

    m_red = Minion(id=UnitID("r_melee"), name="r_melee", team=TeamColor.RED, type=MinionType.MELEE)
    m_blue_spawnable = Minion(
        id=UnitID("b_melee"), name="b_melee", team=TeamColor.BLUE, type=MinionType.MELEE
    )
    m_blue_in_mid = create_minion("b1", TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[m_red]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[], minions=[m_blue_in_mid, m_blue_spawnable]
            ),
        },
        active_zone_id="z_mid",
        wave_counter=5,
    )
    state.move_unit(m_blue_in_mid.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(state, [step])
    _ = process_stack(state).input_request

    assert state.active_zone_id == "z_red_beach"
    assert state.unit_locations.get(m_red.id) == red_beach_hex_1
    assert state.unit_locations.get(m_blue_in_mid.id) == red_beach_hex_2


def test_blocked_spawn_point_does_not_orphan_same_type_minion():
    """Regression: a blocked spawn point must not strand another same-type
    limbo minion.

    Repro (from replay 7ff359546787): a lane zone has two RED MELEE spawn
    points — one blocked by an enemy, one empty — and two RED MELEE minions in
    limbo after a push wipe. The blocked point queues a candidate for
    displacement but leaves it in limbo, so the empty point re-selects the SAME
    minion, double-booking it and orphaning the other in limbo forever.

    Every limbo minion must be assigned exactly once: one placed at the empty
    point, the other queued for displacement, and neither left off-board.
    """
    from goa2.domain.board import DEFAULT_LANE_ID
    from goa2.domain.tile import Tile
    from goa2.engine.steps.combat import _respawn_minions_at_spawn_points

    blocked_hex = Hex(q=-9, r=5, s=4)
    empty_hex = Hex(q=-6, r=-1, s=7)

    board = Board()
    # Spawn points ordered [blocked, empty] — the order that triggers the bug.
    board.zones["z"] = Zone(
        id="z",
        name="Z",
        hexes={blocked_hex, empty_hex},
        spawn_points=[
            SpawnPoint(
                location=blocked_hex,
                team=TeamColor.RED,
                type=SpawnType.MINION,
                minion_type=MinionType.MELEE,
            ),
            SpawnPoint(
                location=empty_hex,
                team=TeamColor.RED,
                type=SpawnType.MINION,
                minion_type=MinionType.MELEE,
            ),
        ],
    )
    board.tiles[blocked_hex] = Tile(hex=blocked_hex, zone_id="z")
    board.tiles[empty_hex] = Tile(hex=empty_hex, zone_id="z")

    m_a = Minion(id=UnitID("m_a"), name="m_a", team=TeamColor.RED, type=MinionType.MELEE)
    m_b = Minion(id=UnitID("m_b"), name="m_b", team=TeamColor.RED, type=MinionType.MELEE)
    blocker = Minion(
        id=UnitID("blocker"), name="blocker", team=TeamColor.BLUE, type=MinionType.MELEE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[m_a, m_b]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[blocker]),
        },
    )
    # An enemy sits on the blocked spawn point; m_a/m_b remain in limbo.
    state.move_unit(blocker.id, blocked_hex)

    pending = _respawn_minions_at_spawn_points(state, DEFAULT_LANE_ID, "z")

    placed = {str(m.id) for m in (m_a, m_b) if m.id in state.unit_locations}
    displaced = {uid for uid, _hex in pending}

    # Every limbo minion is assigned exactly once — none stranded in limbo.
    assert placed | displaced == {"m_a", "m_b"}
    assert placed.isdisjoint(displaced)
    assert len(placed) == 1 and len(displaced) == 1
    # The one placed went to the empty spawn point.
    assert state.unit_locations[next(iter(placed)) and UnitID(next(iter(placed)))] == empty_hex


# --- Game-over boundary tests ---


def test_push_from_blue_beach_triggers_game_over(push_state):
    """
    Blue loses at BlueBeach → push reaches BlueBase → game over.
    """
    push_state.active_zone_id = "z_blue_beach"

    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=2, r=-1, s=-1))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    _ = process_stack(push_state).input_request

    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.winner == TeamColor.RED
    assert push_state.victory_condition == "LANE_PUSH"


def test_push_from_red_beach_triggers_game_over(push_state):
    """
    Red loses at RedBeach → push reaches RedBase → game over.
    """
    push_state.active_zone_id = "z_red_beach"

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=-1, r=0, s=1))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    _ = process_stack(push_state).input_request

    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.winner == TeamColor.BLUE
    assert push_state.victory_condition == "LANE_PUSH"


def test_push_from_mid_not_game_over(push_state):
    """
    Push from Mid goes to a Beach zone, NOT game over.
    """
    # Red loses at Mid → pushes toward RedBeach
    target, is_over = get_push_target_zone_id(push_state, TeamColor.RED)
    assert target == "z_red_beach"
    assert is_over is False

    # Blue loses at Mid → pushes toward BlueBeach
    target, is_over = get_push_target_zone_id(push_state, TeamColor.BLUE)
    assert target == "z_blue_beach"
    assert is_over is False


def test_get_push_target_zone_id_beach_to_base_is_game_over(push_state):
    """
    Direct unit test: pushing from Beach toward Base returns game over.
    """
    # Red loses at RedBeach (idx 1) → new_idx=0 (RedBase) → game over
    push_state.active_zone_id = "z_red_beach"
    target, is_over = get_push_target_zone_id(push_state, TeamColor.RED)
    assert target is None
    assert is_over is True

    # Blue loses at BlueBeach (idx 3) → new_idx=4 (BlueBase) → game over
    push_state.active_zone_id = "z_blue_beach"
    target, is_over = get_push_target_zone_id(push_state, TeamColor.BLUE)
    assert target is None
    assert is_over is True


# --- SessionResult.winner tests ---


def test_session_winner_set_for_lane_push(push_state):
    """GameSession.advance() returns winner for lane push game over."""
    push_state.active_zone_id = "z_blue_beach"

    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=2, r=-1, s=-1))

    session = GameSession(push_state)
    push_steps(push_state, [EndPhaseStep()])
    result = session.advance()

    assert result.result_type == SessionResultType.GAME_OVER
    assert result.winner == "RED"


def test_session_winner_set_for_last_push(push_state):
    """GameSession.advance() returns winner for last push game over."""
    push_state.wave_counter = 1

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    session = GameSession(push_state)
    push_steps(push_state, [EndPhaseStep()])
    result = session.advance()

    assert result.result_type == SessionResultType.GAME_OVER
    assert result.winner is not None
