import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, GamePhase
from goa2.domain.types import HeroID
from goa2.engine.steps import (
    AttackSequenceStep,
    MoveUnitStep,
    DefeatUnitStep,
    RemoveUnitStep,
    TriggerGameOverStep,
)


@pytest.fixture
def game_state():
    # Setup board
    board = Board()
    h1 = Hex(q=0, r=0, s=0)
    h2 = Hex(q=1, r=-1, s=0)
    board.tiles[h1] = Tile(hex=h1, zone_id="test_zone")
    board.tiles[h2] = Tile(hex=h2, zone_id="test_zone")

    # Add one dummy minion for RED to allow attack (if needed by filters, though SelectStep uses state.get_unit)
    # Actually, heroes are units too.

    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[], minions=[], life_counters=5
            ),
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[], minions=[], life_counters=1
            ),  # Last life counter
        },
        active_zone_id="test_zone",
    )

    # Hero A (Blue) - The Attacker
    hero_a = Hero(id=HeroID("hero_blue"), name="Attacker", deck=[], team=TeamColor.BLUE)
    state.register_entity(hero_a, "hero")
    state.place_entity(hero_a.id, h1)

    # Mock a card for Hero Blue so AttackSequenceStep doesn't fail on card lookups if any
    from goa2.domain.models import Card, ActionType, CardTier, CardColor

    mock_card = Card(
        id="mock_attack",
        name="Attack and Move",
        primary_action=ActionType.ATTACK,
        primary_action_value=10,
        initiative=10,
        tier=CardTier.I,
        color=CardColor.BLUE,
        effect_id="NONE",
        effect_text="None",
        is_facedown=False,
    )
    hero_a.current_turn_card = mock_card

    # Hero B (Red) - The Victim
    hero_b = Hero(id=HeroID("hero_red"), name="Victim", deck=[], team=TeamColor.RED)
    state.register_entity(hero_b, "hero")
    state.place_entity(hero_b.id, h2)

    state.current_actor_id = HeroID("hero_blue")

    return state


def test_game_over_purges_remaining_action_steps(game_state):
    """
    Scenario:
    1. Hero Blue performs an action: "Attack, then Move 2".
    2. The Attack kills Hero Red.
    3. Red team loses their last Life Counter -> Game Over.
    4. Verify that the "Move 2" step is NEVER executed because the stack was purged.
    """
    from goa2.engine.steps import (
        SelectStep,
        ReactionWindowStep,
        ResolveCombatStep,
        ResolveDefenseTextStep,
        ResolveOnBlockEffectStep,
        RestoreActionTypeStep,
    )

    # 1. INITIAL STATE
    move_step = MoveUnitStep(unit_id="hero_blue", range_val=2)
    attack_step = AttackSequenceStep(damage=10, range_val=1)

    game_state.execution_stack.append(move_step)
    game_state.execution_stack.append(attack_step)

    assert len(game_state.execution_stack) == 2
    assert isinstance(game_state.execution_stack[0], MoveUnitStep)
    assert isinstance(game_state.execution_stack[1], AttackSequenceStep)

    # 2. EXPAND ATTACK
    # We pop and resolve manually to see the expansion
    step = game_state.execution_stack.pop()
    result = step.resolve(game_state, game_state.execution_context)
    game_state.execution_stack.extend(reversed(result.new_steps))

    # Stack should now have: [Move, Restore, OnBlock, Combat, DefenseText, Reaction, Select]
    assert len(game_state.execution_stack) == 7
    assert isinstance(game_state.execution_stack[6], SelectStep)
    assert isinstance(game_state.execution_stack[5], ReactionWindowStep)
    assert isinstance(game_state.execution_stack[4], ResolveDefenseTextStep)
    assert isinstance(game_state.execution_stack[3], ResolveCombatStep)
    assert isinstance(game_state.execution_stack[2], ResolveOnBlockEffectStep)
    assert isinstance(game_state.execution_stack[1], RestoreActionTypeStep)
    assert isinstance(game_state.execution_stack[0], MoveUnitStep)

    # 3. RESOLVE SELECTION
    step = game_state.execution_stack.pop()
    step.pending_input = {"selection": "hero_red"}
    result = step.resolve(game_state, game_state.execution_context)
    # SelectStep returns is_finished=True and no new steps
    assert result.is_finished is True

    assert len(game_state.execution_stack) == 6
    assert isinstance(game_state.execution_stack[5], ReactionWindowStep)

    # 4. RESOLVE REACTION
    step = game_state.execution_stack.pop()
    step.pending_input = {"selected_card_id": "PASS"}
    result = step.resolve(game_state, game_state.execution_context)
    assert result.is_finished is True

    # 5. RESOLVE DEFENSE TEXT (no primary defense selected, so just passes through)
    assert len(game_state.execution_stack) == 5
    step = game_state.execution_stack.pop()
    assert isinstance(step, ResolveDefenseTextStep)
    result = step.resolve(game_state, game_state.execution_context)
    assert result.is_finished is True

    assert len(game_state.execution_stack) == 4
    assert isinstance(game_state.execution_stack[3], ResolveCombatStep)

    # 6. RESOLVE COMBAT -> SPAWNS DEFEAT
    step = game_state.execution_stack.pop()
    result = step.resolve(game_state, game_state.execution_context)
    game_state.execution_stack.extend(reversed(result.new_steps))

    # Stack now has: [Move, Restore, OnBlock, Defeat]
    assert len(game_state.execution_stack) == 4
    assert isinstance(game_state.execution_stack[3], DefeatUnitStep)
    assert isinstance(game_state.execution_stack[2], ResolveOnBlockEffectStep)
    assert isinstance(game_state.execution_stack[1], RestoreActionTypeStep)
    assert isinstance(game_state.execution_stack[0], MoveUnitStep)

    # 7. RESOLVE DEFEAT -> SPAWNS REMOVE & TRIGGER
    step = game_state.execution_stack.pop()
    result = step.resolve(game_state, game_state.execution_context)
    game_state.execution_stack.extend(reversed(result.new_steps))

    # Order: [Move, Restore, OnBlock, Trigger, Remove]
    assert len(game_state.execution_stack) == 5
    assert isinstance(game_state.execution_stack[4], RemoveUnitStep)
    assert isinstance(game_state.execution_stack[3], TriggerGameOverStep)
    assert isinstance(game_state.execution_stack[2], ResolveOnBlockEffectStep)
    assert isinstance(game_state.execution_stack[1], RestoreActionTypeStep)
    assert isinstance(game_state.execution_stack[0], MoveUnitStep)

    # 8. RESOLVE REMOVE
    step = game_state.execution_stack.pop()
    result = step.resolve(game_state, game_state.execution_context)
    assert "hero_red" not in game_state.entity_locations

    assert len(game_state.execution_stack) == 4
    assert isinstance(game_state.execution_stack[3], TriggerGameOverStep)

    # 9. RESOLVE TRIGGER (THE PURGE)
    step = game_state.execution_stack.pop()
    result = step.resolve(game_state, game_state.execution_context)

    # Game Over logic happens here
    assert game_state.phase == GamePhase.GAME_OVER

    # --- FINAL ASSERTION ---
    # The stack should now be EMPTY because TriggerGameOverStep calls stack.clear()
    assert len(game_state.execution_stack) == 0

    print("\n   [SUCCESS] Stack trace verified. Purge confirmed at step 9.")
