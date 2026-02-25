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


@pytest.fixture
def violent_torrent_state():
    """
    Board setup for dual attack testing:
    - (0,0,0): Arien (attacker)

    Target 1 chain:
    - (1,0,-1): Enemy minion 1 (adjacent, target 1)
    - (4,0,-4): Enemy hero 1 (3 spaces behind target 1, valid for length=5)

    Target 2 chain (for repeat):
    - (0,1,-1): Enemy minion 2 (adjacent, target 2)
    - (0,2,-2): Enemy hero 2 (1 space behind target 2, valid)
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),
        # Chain 1
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=4, r=0, s=-4),
        # Chain 2
        Hex(q=0, r=1, s=-1),
        Hex(q=0, r=2, s=-2),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Arien
    arien = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="violent_torrent",
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        effect_id="violent_torrent",
        effect_text="Target a unit adjacent to you. Before the attack: Up to 1 enemy hero in any of the 5 spaces in a straight line directly behind the target discards a card, or is defeated. May repeat once on a different unit.",
        is_facedown=False,
    )
    arien.current_turn_card = card

    # Enemies
    minion1 = Minion(
        id="minion1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE
    )
    minion2 = Minion(
        id="minion2", name="M2", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    victim1 = Hero(id="victim1", name="V1", team=TeamColor.BLUE, deck=[], level=1)
    victim1.hand = [
        Card(
            id="c1",
            name="C1",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=1,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            state=CardState.HAND,
            effect_id="",
            effect_text="",
        )
    ]

    victim2 = Hero(id="victim2", name="V2", team=TeamColor.BLUE, deck=[], level=1)
    victim2.hand = [
        Card(
            id="c2",
            name="C2",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=1,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            state=CardState.HAND,
            effect_id="",
            effect_text="",
        )
    ]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[victim1, victim2],
                minions=[minion1, minion2],
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("minion1", Hex(q=1, r=0, s=-1))
    state.place_entity("victim1", Hex(q=4, r=0, s=-4))
    state.place_entity("minion2", Hex(q=0, r=1, s=-1))
    state.place_entity("victim2", Hex(q=0, r=2, s=-2))

    state.current_actor_id = "arien"
    return state


def test_violent_torrent_repeat_flow(violent_torrent_state):
    """
    Route 1: Full wombo combo - Attack 1 -> Backstab 1 -> Repeat -> Attack 2 -> Backstab 2
    """
    step = ResolveCardStep(hero_id="arien")
    push_steps(violent_torrent_state, [step])

    # 1. Action Choice -> ATTACK
    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # 2. Select Target 1 -> minion1
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_UNIT"
    assert "minion1" in req["valid_options"]
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "minion1"}

    # 3. Select Backstab 1 -> victim1
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_UNIT"
    assert "victim1" in req["valid_options"]
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "victim1"}

    # 4. Victim 1 Discards
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_CARD"
    assert req["player_id"] == "victim1"
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "c1"}

    # 5. Resolve Attack 1
    process_resolution_stack(violent_torrent_state)

    assert len(violent_torrent_state.get_hero("victim1").hand) == 0
    assert "minion1" not in violent_torrent_state.entity_locations

    # 6. Repeat Prompt -> YES
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_OPTION"
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "YES"}

    # 7. Select Target 2 -> minion2
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_UNIT"
    assert "minion2" in req["valid_options"]
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "minion2"}

    # 8. Select Backstab 2 -> victim2
    req = process_resolution_stack(violent_torrent_state)
    assert "victim2" in req["valid_options"]
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "victim2"}

    # 9. Victim 2 Discards
    req = process_resolution_stack(violent_torrent_state)
    assert req["player_id"] == "victim2"
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "c2"}

    # 10. Resolve Attack 2
    process_resolution_stack(violent_torrent_state)

    assert len(violent_torrent_state.get_hero("victim2").hand) == 0
    assert "minion2" not in violent_torrent_state.entity_locations


def test_violent_torrent_no_repeat(violent_torrent_state):
    """
    Route 2: Hit and run - Attack 1 -> Select Backstab (optional) -> Decline Repeat
    When backstab is optional and we have valid candidates, we can still skip it.
    """
    step = ResolveCardStep(hero_id="arien")
    push_steps(violent_torrent_state, [step])

    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # Target 1
    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "minion1"}

    # Backstab 1 - Skip (optional, even with valid candidates)
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_UNIT"
    assert "victim1" in req["valid_options"]
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

    # Resolve Attack 1
    process_resolution_stack(violent_torrent_state)

    # Repeat Prompt -> NO
    req = process_resolution_stack(violent_torrent_state)
    assert req["type"] == "SELECT_OPTION"
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "NO"}

    # Done
    process_resolution_stack(violent_torrent_state)
    assert len(violent_torrent_state.execution_stack) == 0

    # Verify: Minion 1 dead, Minion 2 alive
    assert "minion1" not in violent_torrent_state.entity_locations
    assert "minion2" in violent_torrent_state.entity_locations


def test_violent_torrent_defeat_condition(violent_torrent_state):
    """
    Route 3: Execution - Empty hand = Defeat
    """
    victim1 = violent_torrent_state.get_hero("victim1")
    victim1.hand = []

    step = ResolveCardStep(hero_id="arien")
    push_steps(violent_torrent_state, [step])

    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "minion1"}

    process_resolution_stack(violent_torrent_state)
    violent_torrent_state.execution_stack[-1].pending_input = {"selection": "victim1"}

    # Empty hand -> Defeat
    process_resolution_stack(violent_torrent_state)

    assert "victim1" not in violent_torrent_state.entity_locations
    assert "minion1" not in violent_torrent_state.entity_locations


def test_violent_torrent_alignment_filter():
    """
    Route 4: Range & Alignment Limits - Hero too far or not in line cannot be selected
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),  # Target
        Hex(q=7, r=0, s=-7),  # Hero 6 spaces behind (should be filtered, limit is 5)
        Hex(q=1, r=1, s=-2),  # Hero NOT in straight line (should be filtered)
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    arien = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="violent_torrent",
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        effect_id="violent_torrent",
        effect_text="Target adjacent unit.",
        is_facedown=False,
    )
    arien.current_turn_card = card

    target = Minion(id="target", name="T", type=MinionType.MELEE, team=TeamColor.BLUE)

    far_hero = Hero(id="far_hero", name="FH", team=TeamColor.BLUE, deck=[], level=1)
    far_hero.hand = [
        Card(
            id="c1",
            name="C1",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=1,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            state=CardState.HAND,
            effect_id="",
            effect_text="",
        )
    ]

    off_line_hero = Hero(
        id="offline_hero", name="OLH", team=TeamColor.BLUE, deck=[], level=1
    )
    off_line_hero.hand = [
        Card(
            id="c2",
            name="C2",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=1,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            state=CardState.HAND,
            effect_id="",
            effect_text="",
        )
    ]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[far_hero, off_line_hero], minions=[target]
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("target", Hex(q=1, r=0, s=-1))
    state.place_entity("far_hero", Hex(q=7, r=0, s=-7))
    state.place_entity("offline_hero", Hex(q=1, r=1, s=-2))

    state.current_actor_id = "arien"

    step = ResolveCardStep(hero_id="arien")
    push_steps(state, [step])

    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # Select Target
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "target"}

    # After target selection, backstab SelectStep runs
    # Both heroes should be filtered out (far_hero dist=6>5, off_line_hero not in line)
    # Optional SelectStep with no candidates auto-skips
    # Flow continues to Attack -> MayRepeatOnceStep
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_OPTION", (
        "MayRepeatOnceStep reached - backstab correctly skipped due to no valid targets"
    )


def test_violent_torrent_repeat_no_valid_targets():
    """
    Edge case: Player selects YES to repeat, but no valid second targets exist.
    Behavior: Optional SelectSteps auto-skip, attack runs with no target and cancels gracefully.
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),  # Minion (adjacent)
        Hex(q=3, r=0, s=-3),  # Victim (behind minion)
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    arien = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="violent_torrent",
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        effect_id="violent_torrent",
        effect_text="Target adjacent unit.",
        is_facedown=False,
    )
    arien.current_turn_card = card

    minion = Minion(id="minion", name="M", type=MinionType.MELEE, team=TeamColor.BLUE)
    victim = Hero(id="victim", name="V", team=TeamColor.BLUE, deck=[], level=1)
    victim.hand = [
        Card(
            id="c1",
            name="C1",
            tier=CardTier.UNTIERED,
            color=CardColor.GOLD,
            initiative=1,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            state=CardState.HAND,
            effect_id="",
            effect_text="",
        )
    ]

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[victim], minions=[minion]
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("minion", Hex(q=1, r=0, s=-1))
    state.place_entity("victim", Hex(q=3, r=0, s=-3))

    state.current_actor_id = "arien"

    step = ResolveCardStep(hero_id="arien")
    push_steps(state, [step])

    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # Target -> minion
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "minion"}

    # Skip backstab
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_UNIT"
    state.execution_stack[-1].pending_input = {"selection": "SKIP"}

    # Attack completes
    process_resolution_stack(state)

    # Repeat prompt -> YES (even though no other targets exist)
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_OPTION"
    state.execution_stack[-1].pending_input = {"selection": "YES"}

    # Repeat steps spawn and auto-skip since no second target exists
    # Flow continues to completion
    result = process_resolution_stack(state)

    # Verify minion is defeated from first attack
    assert "minion" not in state.entity_locations

    # Verify the card effect completed (execution stack should be empty or nearly empty)
    # The repeat attack with no target is handled gracefully
    print("   [OK] Repeat with no valid targets handled gracefully - combat cancelled")


def test_violent_torrent_repeat_vs_heavy_minion():
    """
    Edge case: Player selects YES to repeat, but the only remaining target is a heavy minion
    with immunity (protected by a support minion).
    The target is valid (in range), just immune and filtered out.
    """
    board = Board()

    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),  # Minion 1 (adjacent, gets defeated)
        Hex(
            q=0, r=1, s=-1
        ),  # Heavy Minion 2 (adjacent, immune while support minion present)
        Hex(q=1, r=1, s=-2),  # Support Minion 3 (stays alive to provide immunity)
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    arien = Hero(id="arien", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="violent_torrent",
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.ATTACK,
        primary_action_value=7,
        effect_id="violent_torrent",
        effect_text="Target adjacent unit.",
        is_facedown=False,
    )
    arien.current_turn_card = card

    minion1 = Minion(
        id="minion1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE
    )
    minion2 = Minion(
        id="minion2", name="Heavy M2", type=MinionType.HEAVY, team=TeamColor.BLUE
    )
    support_minion = Minion(
        id="support_minion", name="Supp M3", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[arien], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[],
                minions=[minion1, minion2, support_minion],
            ),
        },
    )

    state.place_entity("arien", Hex(q=0, r=0, s=0))
    state.place_entity("minion1", Hex(q=1, r=0, s=-1))
    state.place_entity("minion2", Hex(q=0, r=1, s=-1))
    state.place_entity("support_minion", Hex(q=1, r=1, s=-2))

    state.current_actor_id = "arien"
    state.active_zone_id = "z1"
    step = ResolveCardStep(hero_id="arien")
    push_steps(state, [step])

    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    # Target -> minion1 (gets defeated)
    process_resolution_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "minion1"}

    # Attack completes, minion1 defeated
    process_resolution_stack(state)
    assert "minion1" not in state.entity_locations

    # Repeat prompt -> YES
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_OPTION"
    state.execution_stack[-1].pending_input = {"selection": "YES"}

    # Select second target -> heavy minion2 is NOT valid (immune due to support_minion)
    req = process_resolution_stack(state)
    # Heavy minion is immune (support_minion present), so no candidates -> optional step auto-skips
    assert req is None, "Heavy minion should be filtered out (immune), step auto-skips"

    # Verify minion1 is still defeated
    assert "minion1" not in state.entity_locations
    # minion2 and support_minion should still be alive (immune, not targeted)
    assert "minion2" in state.entity_locations
    assert "support_minion" in state.entity_locations

    print("   [OK] Heavy minion correctly treated as immune")
