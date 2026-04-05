from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, Hero, Token, TokenType, Card, CardTier, CardColor, CardState, ActionType
from goa2.domain.types import HeroID, BoardEntityID
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import MoveSequenceStep, MoveUnitStep, TriggerMineStep
from goa2.domain.events import GameEventType


def _make_state_with_mine():
    board = Board()
    for h in [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0), Hex(q=2, r=-2, s=0)]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    mine_owner = Hero(id=HeroID("hero_min"), name="Min", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[]),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mine_owner], minions=[]),
        },
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))

    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        owner_id=HeroID("hero_min"),
        is_passable=True,
        is_facedown=True,
    )
    state.token_pool[TokenType.MINE_BLAST] = [mine]
    state.misc_entities[BoardEntityID("mine_1")] = mine
    state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=-1, s=0))
    return state


def test_mine_triggered_and_removed_after_movement():
    """Moving through a mine triggers it and removes the token."""
    state = _make_state_with_mine()
    push_steps(state, [MoveSequenceStep(range_val=2)])

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -2, "s": 0}}
    process_resolution_stack(state)

    assert state.entity_locations[BoardEntityID("hero_a")] == Hex(q=2, r=-2, s=0)
    assert BoardEntityID("mine_1") not in state.entity_locations


def test_trigger_mine_step_directly():
    """TriggerMineStep removes mines from context and emits events."""
    state = _make_state_with_mine()
    state.execution_context["triggered_mine_ids"] = ["mine_1"]

    push_steps(state, [TriggerMineStep()])
    process_resolution_stack(state)

    assert BoardEntityID("mine_1") not in state.entity_locations


def test_trigger_mine_step_no_mines():
    """TriggerMineStep with empty mine list does nothing."""
    state = _make_state_with_mine()
    state.execution_context["triggered_mine_ids"] = []

    push_steps(state, [TriggerMineStep()])
    result = process_resolution_stack(state)

    assert result is None


def test_no_mine_triggered_when_no_passable_tokens():
    """Movement without passable tokens does not trigger anything."""
    board = Board()
    for h in [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0), Hex(q=2, r=-2, s=0)]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[])},
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))

    push_steps(state, [MoveSequenceStep(range_val=2)])

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -2, "s": 0}}
    process_resolution_stack(state)

    assert state.entity_locations[BoardEntityID("hero_a")] == Hex(q=2, r=-2, s=0)


def test_forced_movement_triggers_mine():
    """MoveUnitStep without MinePathChoiceStep still triggers mines (forced movement)."""
    state = _make_state_with_mine()
    state.execution_context["target_hex"] = {"q": 2, "r": -2, "s": 0}

    push_steps(state, [MoveUnitStep(unit_id="hero_a", destination_key="target_hex", range_val=2)])
    process_resolution_stack(state)

    assert state.entity_locations[BoardEntityID("hero_a")] == Hex(q=2, r=-2, s=0)
    assert BoardEntityID("mine_1") not in state.entity_locations


def test_blast_mine_forces_discard():
    """Walking through a blast mine forces the moved hero to discard a card."""
    state = _make_state_with_mine()
    hero = state.get_hero(HeroID("hero_a"))
    card = Card(
        id="card_1", name="Test Card", tier=CardTier.I, color=CardColor.RED,
        primary_action=ActionType.ATTACK, primary_action_value=2,
        secondary_actions={}, effect_id="e", effect_text="t",
        initiative=5, state=CardState.HAND, is_facedown=False,
    )
    hero.hand.append(card)

    push_steps(state, [MoveSequenceStep(range_val=2)])
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -2, "s": 0}}
    req = process_resolution_stack(state)

    # Blast mine triggered — hero must discard
    assert req is not None
    assert req["type"] == "SELECT_CARD"
    assert req["player_id"] == "hero_a"

    state.execution_stack[-1].pending_input = {"selection": "card_1"}
    process_resolution_stack(state)

    assert len(hero.hand) == 0
    assert any(c.id == "card_1" for c in hero.discard_pile)


def test_dud_mine_no_discard():
    """Walking through a dud mine does NOT force a discard."""
    board = Board()
    for h in [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0), Hex(q=2, r=-2, s=0)]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    mine_owner = Hero(id=HeroID("hero_min"), name="Min", team=TeamColor.RED, deck=[])
    card = Card(
        id="card_1", name="Test Card", tier=CardTier.I, color=CardColor.RED,
        primary_action=ActionType.ATTACK, primary_action_value=2,
        secondary_actions={}, effect_id="e", effect_text="t",
        initiative=5, state=CardState.HAND, is_facedown=False,
    )
    hero.hand.append(card)

    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[]),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mine_owner], minions=[]),
        },
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))

    mine = Token(
        id=BoardEntityID("mine_1"), name="Mine", token_type=TokenType.MINE_DUD,
        owner_id=HeroID("hero_min"), is_passable=True, is_facedown=True,
    )
    state.token_pool[TokenType.MINE_DUD] = [mine]
    state.misc_entities[BoardEntityID("mine_1")] = mine
    state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=-1, s=0))

    push_steps(state, [MoveSequenceStep(range_val=2)])
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -2, "s": 0}}
    req = process_resolution_stack(state)

    # Dud mine — no discard, movement completes
    assert req is None
    assert len(hero.hand) == 1
    assert BoardEntityID("mine_1") not in state.entity_locations
