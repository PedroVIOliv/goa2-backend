import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    ActionType,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    StatType,
    CardState,
)
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    ResolveCardStep,
    ResolveCardTextStep,
    ReactionWindowStep,
    AttackSequenceStep,
    MoveSequenceStep,
)
from goa2.engine.phases import resolve_next_action
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def stats_state():
    board = Board()
    for q in range(-3, 4):
        for r in range(-3, 4):
            h = Hex(q=q, r=r, s=-q - r)
            board.tiles[h] = Tile(hex=h)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_red",
    )

    hero = Hero(id="hero_red", name="Hero Red", team=TeamColor.RED, deck=[])
    state.teams[TeamColor.RED].heroes.append(hero)
    state.place_entity("hero_red", Hex(q=0, r=0, s=0))

    # Dummy enemy
    enemy = Hero(id="hero_blue", name="Hero Blue", team=TeamColor.BLUE, deck=[])
    state.teams[TeamColor.BLUE].heroes.append(enemy)
    state.place_entity("hero_blue", Hex(q=2, r=0, s=-2))

    return state


def test_resolve_card_step_attack_bonus(stats_state):
    # Setup: Hero has +1 Attack Modifier
    hero = stats_state.get_hero("hero_red")
    stats_state.active_modifiers.append(
        Modifier(
            id="mod1",
            source_id="self",
            target_id="hero_red",
            stat_type=StatType.ATTACK,
            value_mod=1,
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
        )
    )

    # Card: Attack 3
    card = Card(
        id="atk1",
        name="Strike",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        color=CardColor.RED,
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )
    hero.current_turn_card = card

    step = ResolveCardStep(hero_id="hero_red")
    push_steps(stats_state, [step])

    # Process
    req = process_resolution_stack(stats_state)

    assert req is not None
    assert req["type"] == "CHOOSE_ACTION"

    # Check Options UI Text: Should be 4 (3+1)
    opt = next(o for o in req["options"] if o["id"] == "ATTACK")
    assert opt["value"] == 4
    assert "(4)" in opt["text"]

    # Execute Choice (ResolveCardStep)
    stats_state.execution_stack[0].pending_input = {"choice_id": "ATTACK"}
    res = stats_state.execution_stack[0].resolve(stats_state, {})

    # Should spawn ResolveCardTextStep (Primary)
    text_step = next(s for s in res.new_steps if isinstance(s, ResolveCardTextStep))

    # Execute ResolveCardTextStep
    res_text = text_step.resolve(stats_state, {})

    # Should spawn AttackSequenceStep with damage=4
    atk_step = next(s for s in res_text.new_steps if isinstance(s, AttackSequenceStep))
    assert atk_step.damage == 4


def test_resolve_card_step_movement_bonus(stats_state):
    # Setup: Hero has +1 Move Item
    hero = stats_state.get_hero("hero_red")
    hero.items[StatType.MOVEMENT] = 1

    # Card: Move 2
    card = Card(
        id="mov1",
        name="Dash",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        color=CardColor.RED,
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )
    hero.current_turn_card = card

    step = ResolveCardStep(hero_id="hero_red")
    push_steps(stats_state, [step])

    req = process_resolution_stack(stats_state)

    # Check Options UI: Should be 3 (2+1)
    opt = next(o for o in req["options"] if o["id"] == "MOVEMENT")
    assert opt["value"] == 3

    # Execute Choice (ResolveCardStep)
    stats_state.execution_stack[0].pending_input = {"choice_id": "MOVEMENT"}
    res = stats_state.execution_stack[0].resolve(stats_state, {})

    # Should spawn ResolveCardTextStep (Primary)
    text_step = next(s for s in res.new_steps if isinstance(s, ResolveCardTextStep))

    # Execute ResolveCardTextStep
    res_text = text_step.resolve(stats_state, {})

    # Should spawn MoveSequenceStep with range_val=3
    move_step = next(s for s in res_text.new_steps if isinstance(s, MoveSequenceStep))
    assert move_step.range_val == 3


def test_resolve_card_step_range_bonus(stats_state):
    # Setup: Hero has +1 Range Modifier
    hero = stats_state.get_hero("hero_red")
    stats_state.active_modifiers.append(
        Modifier(
            id="mod2",
            source_id="self",
            target_id="hero_red",
            stat_type=StatType.RANGE,
            value_mod=1,
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
        )
    )

    # Card: Attack 3 (Range 1)
    card = Card(
        id="atk_rng",
        name="Reach",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        range_value=1,
        color=CardColor.RED,
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )
    hero.current_turn_card = card

    step = ResolveCardStep(hero_id="hero_red")
    push_steps(stats_state, [step])

    # Select Attack
    process_resolution_stack(stats_state)  # UI
    stats_state.execution_stack[0].pending_input = {"choice_id": "ATTACK"}
    res = stats_state.execution_stack[0].resolve(stats_state, {})

    # Should spawn ResolveCardTextStep (Primary)
    text_step = next(s for s in res.new_steps if isinstance(s, ResolveCardTextStep))

    # Execute ResolveCardTextStep
    res_text = text_step.resolve(stats_state, {})

    # Should spawn AttackSequenceStep with range_val=2 (1+1)
    atk_step = next(s for s in res_text.new_steps if isinstance(s, AttackSequenceStep))
    assert atk_step.range_val == 2


def test_resolve_card_text_step_fallback_bonus(stats_state):
    # Setup: Hero has +1 Move Item
    hero = stats_state.get_hero("hero_red")
    hero.items[StatType.MOVEMENT] = 1

    # Card: Move 2 (Primary)
    card = Card(
        id="mov_primary",
        name="Dash",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        color=CardColor.RED,
        effect_id="missing_effect",
        effect_text="",
        is_facedown=False,
    )
    hero.current_turn_card = card

    # ResolveCardTextStep (triggered via Primary selection or direct)
    step = ResolveCardTextStep(card_id=card.id, hero_id="hero_red")
    res = step.resolve(stats_state, {})

    # Should use fallback logic and compute stats
    move_step = next(s for s in res.new_steps if isinstance(s, MoveSequenceStep))
    assert move_step.range_val == 3


def test_reaction_window_defense_bonus(stats_state):
    # Setup: Defender (Blue) has +1 Defense Item
    defender = stats_state.get_hero("hero_blue")
    defender.items[StatType.DEFENSE] = 1

    # Defense Card: Value 3
    # FIX: Use UNTIERED for GOLD color
    def_card = Card(
        id="def1",
        name="Shield",
        tier=CardTier.UNTIERED,
        initiative=1,
        primary_action=ActionType.DEFENSE,
        primary_action_value=3,
        color=CardColor.GOLD,
        effect_id="none",
        effect_text="",
        is_facedown=False,
    )
    defender.hand.append(def_card)

    step = ReactionWindowStep(target_player_key="target_id")
    ctx = {"target_id": "hero_blue"}

    # Choose Card
    step.pending_input = {"selected_card_id": "def1"}
    res = step.resolve(stats_state, ctx)

    # Context should have computed defense: 4 (3+1)
    assert ctx["defense_value"] == 4


def test_initiative_bonus(stats_state):
    # Setup: Hero Red has +5 Initiative Bonus
    stats_state.active_modifiers.append(
        Modifier(
            id="mod3",
            source_id="self",
            target_id="hero_red",
            stat_type=StatType.INITIATIVE,
            value_mod=5,
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
        )
    )

    # Hero Red plays Init 10 -> Total 15
    # Hero Blue plays Init 12 -> Total 12
    h1 = stats_state.get_hero("hero_red")
    h1.current_turn_card = Card(
        id="c1",
        name="Slow",
        tier=CardTier.I,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        color=CardColor.RED,
        effect_id="none",
        effect_text="",
        state=CardState.UNRESOLVED,
        is_facedown=False,
    )

    h2 = stats_state.get_hero("hero_blue")
    h2.current_turn_card = Card(
        id="c2",
        name="Fast",
        tier=CardTier.I,
        initiative=12,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        color=CardColor.RED,
        effect_id="none",
        effect_text="",
        state=CardState.UNRESOLVED,
        is_facedown=False,
    )

    stats_state.unresolved_hero_ids = ["hero_red", "hero_blue"]

    # Run phases logic
    resolve_next_action(stats_state)

    # Red should act first (15 vs 12)
    assert stats_state.current_actor_id == "hero_red"
