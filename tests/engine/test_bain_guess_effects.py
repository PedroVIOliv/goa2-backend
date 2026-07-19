"""Tests for Bain's guess-card-color effects:
A Game of Chance, Dead Man's Hand, We're Not Done Yet!"""

import pytest

import goa2.scripts.bain_effects  # noqa: F401 — registers effects
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import ResolveCardStep

# ---------------------------------------------------------------------------
# Card factories
# ---------------------------------------------------------------------------


def _make_skill_card(card_id, name, effect_id, radius=2, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=9,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        radius_value=radius,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_filler_card(card_id="filler", color=CardColor.RED):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.I,
        color=color,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


def _make_gold_card(card_id="gold"):
    return Card(
        id=card_id,
        name="Gold Filler",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board():
    b = Board()
    hexes = set()
    for q in range(-4, 5):
        for r in range(-4, 5):
            s = -q - r
            if abs(s) <= 4:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    b.zones = {"z1": z1}
    b.populate_tiles_from_zones()
    return b


def _build_state(board, bain_card, enemy_hand):
    """Build a GameState with Bain and an enemy hero with given hand."""
    bain = Hero(id=HeroID("hero_bain"), name="Bain", team=TeamColor.RED, deck=[], hand=[])
    bain.current_turn_card = bain_card

    enemy = Hero(
        id=HeroID("hero_enemy"), name="Enemy", team=TeamColor.BLUE, deck=[], hand=enemy_hand
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "hero_bain"
    return state


def _drive_to_skill(state):
    """Drive through ResolveCardStep until SKILL action is chosen."""
    push_steps(state, [ResolveCardStep(hero_id="hero_bain")])
    req = process_stack(state).input_request
    assert req["type"] == "CHOOSE_ACTION"
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}


# ===========================================================================
# CardsInContainerFilter tests
# ===========================================================================


class TestCardsInContainerFilter:
    """CardsInContainerFilter replaces HasCardsInDiscardFilter with generic
    container + min/max card count filtering."""

    def test_filters_by_min_cards_in_hand(self, board):
        """Enemy with 2 cards passes min_cards=2, enemy with 1 card does not."""
        from goa2.domain.models.enums import CardContainerType
        from goa2.engine.filters import CardsInContainerFilter

        enemy2 = Hero(
            id=HeroID("hero_enemy2"),
            name="Enemy2",
            deck=[],
            hand=[
                _make_filler_card("e2_c1"),
                _make_filler_card("e2_c2"),
            ],
        )
        enemy1 = Hero(
            id=HeroID("hero_enemy1"),
            name="Enemy1",
            deck=[],
            hand=[
                _make_filler_card("e1_c1"),
            ],
        )

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
        bain.current_turn_card = card

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy1, enemy2], minions=[]),
            },
        )
        state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
        state.place_entity("hero_enemy1", Hex(q=1, r=0, s=-1))
        state.place_entity("hero_enemy2", Hex(q=0, r=1, s=-1))

        f = CardsInContainerFilter(container=CardContainerType.HAND, min_cards=2)
        assert f.apply("hero_enemy2", state, {}) is True
        assert f.apply("hero_enemy1", state, {}) is False

    def test_filters_by_max_cards_in_hand(self, board):
        """max_cards=1 should only pass heroes with ≤1 card."""
        from goa2.domain.models.enums import CardContainerType
        from goa2.engine.filters import CardsInContainerFilter

        enemy = Hero(
            id=HeroID("hero_enemy"),
            name="Enemy",
            deck=[],
            hand=[
                _make_filler_card("c1"),
                _make_filler_card("c2"),
            ],
        )
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
        bain.current_turn_card = card

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
        state.place_entity("hero_enemy", Hex(q=1, r=0, s=-1))

        f = CardsInContainerFilter(container=CardContainerType.HAND, max_cards=1)
        assert f.apply("hero_enemy", state, {}) is False

        f2 = CardsInContainerFilter(container=CardContainerType.HAND, max_cards=3)
        assert f2.apply("hero_enemy", state, {}) is True

    def test_filters_discard_container(self, board):
        """Works with DISCARD container (replaces HasCardsInDiscardFilter)."""
        from goa2.domain.models import CardState
        from goa2.domain.models.enums import CardContainerType
        from goa2.engine.filters import CardsInContainerFilter

        enemy = Hero(id=HeroID("hero_enemy"), name="Enemy", deck=[], hand=[])
        discard = _make_filler_card("d1")
        discard.state = CardState.DISCARD
        enemy.discard_pile = [discard]

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
        bain.current_turn_card = card

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
            },
        )
        state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
        state.place_entity("hero_enemy", Hex(q=1, r=0, s=-1))

        f = CardsInContainerFilter(container=CardContainerType.DISCARD, min_cards=1)
        assert f.apply("hero_enemy", state, {}) is True

    def test_rejects_non_hero(self, board):
        """Non-hero candidates (minions, hexes) should be rejected."""
        from goa2.domain.models.enums import CardContainerType
        from goa2.engine.filters import CardsInContainerFilter

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
        bain.current_turn_card = card

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.place_entity("hero_bain", Hex(q=0, r=0, s=0))

        f = CardsInContainerFilter(container=CardContainerType.HAND, min_cards=1)
        assert f.apply(Hex(q=1, r=0, s=-1), state, {}) is False
        assert f.apply("nonexistent_hero", state, {}) is False


# ===========================================================================
# GuessCardColorStep tests
# ===========================================================================


class TestGuessCardColorStep:
    """GuessCardColorStep should present valid color options from victim's hand."""

    def test_offers_all_five_colors(self, board):
        """GuessCardColorStep always offers BLUE, GOLD, GREEN, RED, SILVER."""
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)

        push_steps(
            state,
            [
                GuessCardColorStep(output_key="guessed_color"),
            ],
        )

        req = process_stack(state).input_request
        assert req is not None
        assert req["type"] == "SELECT_OPTION"
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"BLUE", "GOLD", "GREEN", "RED", "SILVER"}

    def test_victim_restriction_offers_hand_colors(self, board):
        """With a victim and no hidden zones, options are the hand's colors."""
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED", "BLUE"}

    def test_victim_restriction_excludes_faceup_discard_color(self, board):
        """A color visible faceup outside the hand is publicly known absent."""
        from goa2.domain.models import CardState
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        enemy = state.get_hero(HeroID("hero_enemy"))
        faceup_green = _make_filler_card("e_green", color=CardColor.GREEN)
        faceup_green.state = CardState.DISCARD
        enemy.discard_pile = [faceup_green]
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED", "BLUE"}

    def test_victim_restriction_includes_facedown_discard_color(self, board):
        """A facedown card outside the hand (Takahide's Bushido) has a hidden
        identity, so its color could still be in hand — the option pool must
        include it rather than leak its absence."""
        from goa2.domain.models import CardState
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [_make_filler_card("e_red", color=CardColor.RED)]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        enemy = state.get_hero(HeroID("hero_enemy"))
        hidden_green = _make_filler_card("e_green", color=CardColor.GREEN)
        hidden_green.state = CardState.DISCARD
        hidden_green.is_facedown = True
        enemy.discard_pile = [hidden_green]
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED", "GREEN"}

    def test_victim_restriction_ignores_deck_zone_entirely(self, board):
        """The guess universe is hand + played + current turn + discard. Cards
        in the deck zone (upgrade stock OR Takahide's starts_in_deck cycle)
        are outside it and never widen the pool."""
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [_make_filler_card("e_red", color=CardColor.RED)]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        enemy = state.get_hero(HeroID("hero_enemy"))
        cycling_blue = _make_filler_card("e_blue", color=CardColor.BLUE)
        cycling_blue.starts_in_deck = True
        enemy.deck = [
            cycling_blue,
            _make_filler_card("e_green_stock_1", color=CardColor.GREEN),
            _make_filler_card("e_green_stock_2", color=CardColor.GREEN),
        ]
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED"}

    def test_victim_restriction_duplicate_colors_need_one_hidden_copy(self, board):
        """Takahide-style duplicate colors: with two golds faceup in discard
        and one still in hand, GOLD stays guessable — a copy remains hidden."""
        from goa2.domain.models import CardState
        from goa2.engine.steps import GuessCardColorStep

        gold_in_hand = _make_gold_card("e_gold_1")
        enemy_hand = [_make_filler_card("e_red", color=CardColor.RED), gold_in_hand]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        enemy = state.get_hero(HeroID("hero_enemy"))
        for cid in ("e_gold_2", "e_gold_3"):
            spent = _make_gold_card(cid)
            spent.state = CardState.DISCARD
            enemy.discard_pile.append(spent)
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED", "GOLD"}

    def test_victim_restriction_includes_facedown_played_card_color(self, board):
        """A facedown card in a played/resolved slot is identity-hidden and
        must widen the pool."""
        from goa2.engine.steps import GuessCardColorStep

        enemy_hand = [_make_filler_card("e_red", color=CardColor.RED)]
        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)
        enemy = state.get_hero(HeroID("hero_enemy"))
        hidden_blue = _make_filler_card("e_blue", color=CardColor.BLUE)
        hidden_blue.is_facedown = True
        enemy.played_cards = [hidden_blue, None]
        state.execution_context["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [GuessCardColorStep(output_key="guessed_color", victim_key="guess_victim")],
        )

        req = process_stack(state).input_request
        option_ids = {o["id"] for o in req["options"]}
        assert option_ids == {"RED", "BLUE"}

    def test_stores_selection_in_context(self, board):
        """Selected color is stored in context at output_key."""
        from goa2.engine.steps import GuessCardColorStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])

        push_steps(
            state,
            [
                GuessCardColorStep(output_key="guessed_color"),
            ],
        )

        req = process_stack(state).input_request
        assert req is not None
        state.execution_stack[-1].pending_input = {"selection": "RED"}
        _ = process_stack(state).input_request
        assert state.execution_context["guessed_color"] == "RED"


# ===========================================================================
# RevealAndResolveGuessStep tests
# ===========================================================================


class TestRevealAndResolveGuessStep:
    """RevealAndResolveGuessStep compares guessed color with card color."""

    def test_correct_guess_sets_flag(self, board):
        from goa2.engine.steps import RevealAndResolveGuessStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])
        ctx = state.execution_context
        ctx["chosen_card"] = "e_red"
        ctx["guessed_color"] = "RED"

        # Create a fake card with RED color for lookup
        enemy = state.get_hero(HeroID("hero_enemy"))
        red_card = _make_filler_card("e_red", color=CardColor.RED)
        enemy.hand = [red_card]

        push_steps(
            state,
            [
                RevealAndResolveGuessStep(
                    card_key="chosen_card",
                    guess_key="guessed_color",
                    victim_key="guess_victim",
                    correct_output_key="guess_correct",
                    wrong_output_key="guess_wrong",
                ),
            ],
        )
        ctx["guess_victim"] = "hero_enemy"

        _ = process_stack(state).input_request
        assert ctx.get("guess_correct") is True
        assert ctx.get("guess_wrong") is None

    def test_wrong_guess_sets_flag(self, board):
        from goa2.engine.steps import RevealAndResolveGuessStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])
        ctx = state.execution_context
        ctx["chosen_card"] = "e_red"
        ctx["guessed_color"] = "BLUE"
        ctx["guess_victim"] = "hero_enemy"

        enemy = state.get_hero(HeroID("hero_enemy"))
        red_card = _make_filler_card("e_red", color=CardColor.RED)
        enemy.hand = [red_card]

        push_steps(
            state,
            [
                RevealAndResolveGuessStep(
                    card_key="chosen_card",
                    guess_key="guessed_color",
                    victim_key="guess_victim",
                    correct_output_key="guess_correct",
                    wrong_output_key="guess_wrong",
                ),
            ],
        )

        _ = process_stack(state).input_request
        assert ctx.get("guess_correct") is None
        assert ctx.get("guess_wrong") is True

    def test_reveal_freezes_rollback_on_correct_guess(self, board):
        """Revealing the chosen card leaks hidden info, so the actor must not
        be able to rollback to the guess prompt afterwards."""
        from goa2.engine.steps import RevealAndResolveGuessStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])
        ctx = state.execution_context
        ctx["chosen_card"] = "e_red"
        ctx["guessed_color"] = "RED"
        ctx["guess_victim"] = "hero_enemy"

        enemy = state.get_hero(HeroID("hero_enemy"))
        enemy.hand = [_make_filler_card("e_red", color=CardColor.RED)]

        push_steps(
            state,
            [
                RevealAndResolveGuessStep(
                    card_key="chosen_card",
                    guess_key="guessed_color",
                    victim_key="guess_victim",
                    correct_output_key="guess_correct",
                    wrong_output_key="guess_wrong",
                ),
            ],
        )

        _ = process_stack(state).input_request
        assert ctx.get("rollback_frozen") is True

    def test_reveal_freezes_rollback_on_wrong_guess(self, board):
        from goa2.engine.steps import RevealAndResolveGuessStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])
        ctx = state.execution_context
        ctx["chosen_card"] = "e_red"
        ctx["guessed_color"] = "BLUE"
        ctx["guess_victim"] = "hero_enemy"

        enemy = state.get_hero(HeroID("hero_enemy"))
        enemy.hand = [_make_filler_card("e_red", color=CardColor.RED)]

        push_steps(
            state,
            [
                RevealAndResolveGuessStep(
                    card_key="chosen_card",
                    guess_key="guessed_color",
                    victim_key="guess_victim",
                    correct_output_key="guess_correct",
                    wrong_output_key="guess_wrong",
                ),
            ],
        )

        _ = process_stack(state).input_request
        assert ctx.get("rollback_frozen") is True

    def test_noop_reveal_does_not_freeze_rollback(self, board):
        """If nothing was revealed (no chosen card in context), rollback must
        stay available."""
        from goa2.engine.steps import RevealAndResolveGuessStep

        card = _make_skill_card("test", "Test", "a_game_of_chance")
        state = _build_state(board, card, [])
        ctx = state.execution_context
        ctx["guess_victim"] = "hero_enemy"

        push_steps(
            state,
            [
                RevealAndResolveGuessStep(
                    card_key="chosen_card",
                    guess_key="guessed_color",
                    victim_key="guess_victim",
                    correct_output_key="guess_correct",
                    wrong_output_key="guess_wrong",
                ),
            ],
        )

        _ = process_stack(state).input_request
        assert ctx.get("rollback_frozen") is not True


# ===========================================================================
# A Game of Chance effect tests
# ===========================================================================


class TestAGameOfChance:
    """A Game of Chance: Enemy picks card, guess color.
    Correct → discard. Wrong → gain 1 coin."""

    def test_correct_guess_discards_card(self, board):
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card("a_game_of_chance", "A Game of Chance", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        # 1. Select enemy hero (auto or manual)
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        # 2. Enemy chooses card from hand
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        # 3. Bain guesses color
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_OPTION"
        # Guess RED (correct — card IS red)
        state.execution_stack[-1].pending_input = {"selection": "RED"}

        # 4. Resolve — process remaining steps
        req = process_stack(state).input_request
        while req is not None:
            req = process_stack(state).input_request

        enemy = state.get_hero(HeroID("hero_enemy"))
        # e_red should be discarded
        assert not any(c.id == "e_red" for c in enemy.hand)
        assert any(c.id == "e_red" for c in enemy.discard_pile)
        # Bain should NOT gain coins
        bain = state.get_hero(HeroID("hero_bain"))
        assert bain.gold == 0

    def test_wrong_guess_gains_1_coin(self, board):
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card("a_game_of_chance", "A Game of Chance", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        # Select enemy
        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        # Enemy chooses red card
        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        # Bain guesses BLUE (wrong)
        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "BLUE"}

        req = process_stack(state).input_request
        while req is not None:
            req = process_stack(state).input_request

        enemy = state.get_hero(HeroID("hero_enemy"))
        # Card should NOT be discarded
        assert any(c.id == "e_red" for c in enemy.hand)
        # Bain gains 1 coin
        bain = state.get_hero(HeroID("hero_bain"))
        assert bain.gold == 1

    def test_no_valid_target_skips(self, board):
        """If no enemy hero has 2+ cards in hand, effect does nothing."""
        enemy_hand = [_make_filler_card("e_one")]  # Only 1 card
        card = _make_skill_card("a_game_of_chance", "A Game of Chance", "a_game_of_chance")
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        # Should skip (no valid targets) and finish
        req = process_stack(state).input_request
        while req is not None:
            # Should not get a SELECT_UNIT for enemy hero
            req = process_stack(state).input_request


# ===========================================================================
# Dead Man's Hand effect tests
# ===========================================================================


class TestDeadMansHand:
    """Dead Man's Hand: Same as A Game of Chance but wrong guess = 2 coins."""

    def test_wrong_guess_gains_2_coins(self, board):
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card(
            "dead_mans_hand",
            "Dead Man's Hand",
            "dead_mans_hand",
            tier=CardTier.II,
            radius=3,
        )
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "BLUE"}

        req = process_stack(state).input_request
        while req is not None:
            req = process_stack(state).input_request

        bain = state.get_hero(HeroID("hero_bain"))
        assert bain.gold == 2


# ===========================================================================
# We're Not Done Yet! effect tests
# ===========================================================================


class TestWereNotDoneYet:
    """We're Not Done Yet!: Guess mechanic + on wrong guess,
    choose to repeat once or gain 2 coins."""

    def test_correct_guess_discards_no_repeat(self, board):
        """Correct guess → discard, no repeat offered."""
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card(
            "were_not_done_yet",
            "We're Not Done Yet!",
            "were_not_done_yet",
            tier=CardTier.III,
            radius=3,
        )
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "RED"}

        req = process_stack(state).input_request
        while req is not None:
            # Should not be asked to repeat or gain coins
            assert req.get("type") != "SELECT_NUMBER"
            req = process_stack(state).input_request

        enemy = state.get_hero(HeroID("hero_enemy"))
        assert any(c.id == "e_red" for c in enemy.discard_pile)

    def test_wrong_guess_choose_coins(self, board):
        """Wrong guess → choose coins → gain 2 coins."""
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
        ]
        card = _make_skill_card(
            "were_not_done_yet",
            "We're Not Done Yet!",
            "were_not_done_yet",
            tier=CardTier.III,
            radius=3,
        )
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "BLUE"}

        # Choose: 1=repeat, 2=gain coins
        req = process_stack(state).input_request
        assert req is not None
        assert req["type"] == "SELECT_NUMBER"
        state.execution_stack[-1].pending_input = {"selection": 2}

        req = process_stack(state).input_request
        while req is not None:
            req = process_stack(state).input_request

        bain = state.get_hero(HeroID("hero_bain"))
        assert bain.gold == 2

    def test_wrong_guess_choose_repeat_then_correct(self, board):
        """Wrong guess → choose repeat → correct second time → discard."""
        enemy_hand = [
            _make_filler_card("e_red", color=CardColor.RED),
            _make_filler_card("e_blue", color=CardColor.BLUE),
            _make_filler_card("e_green", color=CardColor.GREEN),
        ]
        card = _make_skill_card(
            "were_not_done_yet",
            "We're Not Done Yet!",
            "were_not_done_yet",
            tier=CardTier.III,
            radius=3,
        )
        state = _build_state(board, card, enemy_hand)

        _drive_to_skill(state)

        # First guess sequence
        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "e_red"}

        req = process_stack(state).input_request
        state.execution_stack[-1].pending_input = {"selection": "BLUE"}  # Wrong

        # Choose repeat
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_NUMBER"
        state.execution_stack[-1].pending_input = {"selection": 1}

        # Second guess sequence — select enemy again
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        # Enemy chooses card
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "e_blue"}

        # Guess correctly this time
        req = process_stack(state).input_request
        assert req["type"] == "SELECT_OPTION"
        state.execution_stack[-1].pending_input = {"selection": "BLUE"}

        req = process_stack(state).input_request
        while req is not None:
            req = process_stack(state).input_request

        enemy = state.get_hero(HeroID("hero_enemy"))
        assert any(c.id == "e_blue" for c in enemy.discard_pile)
        bain = state.get_hero(HeroID("hero_bain"))
        assert bain.gold == 0  # No coins on correct repeat
