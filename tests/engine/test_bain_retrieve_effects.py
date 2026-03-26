"""Tests for Bain's Drinking Buddies and Another One! card effects."""

import pytest
import goa2.scripts.bain_effects  # noqa: F401 — registers effects

from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    CardState,
)
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID
from goa2.engine.steps import ResolveCardStep, RetrieveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps


# ---------------------------------------------------------------------------
# Card factories
# ---------------------------------------------------------------------------


def _make_skill_card(card_id, name, effect_id, radius=3, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=10,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        radius_value=radius,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
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


def _build_state(board, bain_card, ally=None, enemy=None):
    """Build a GameState with Bain, optional ally, and optional enemy."""
    bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
    bain.current_turn_card = bain_card

    red_heroes = [bain]
    if ally:
        red_heroes.append(ally)

    blue_heroes = []
    if enemy:
        blue_heroes.append(enemy)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=red_heroes, minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=blue_heroes, minions=[]),
        },
    )
    state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
    if ally:
        state.place_entity(str(ally.id), Hex(q=1, r=0, s=-1))
    if enemy:
        state.place_entity(str(enemy.id), Hex(q=2, r=0, s=-2))
    state.current_actor_id = "hero_bain"
    return state


# ===========================================================================
# RetrieveCardStep.hero_key tests
# ===========================================================================


class TestRetrieveCardStepHeroKey:
    """RetrieveCardStep should retrieve for a non-actor hero when hero_key is set."""

    def test_retrieve_for_non_actor_hero(self, board):
        """When hero_key points to another hero, that hero retrieves the card."""
        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        discard_card = _make_filler_card("ally_discard")
        discard_card.state = CardState.DISCARD
        ally.discard_pile = [discard_card]

        card = _make_skill_card("db", "Test", "drinking_buddies")
        state = _build_state(board, card, ally=ally)

        # Set up context as if SelectStep already chose the card
        context = state.execution_context
        context["target_retrieve_card"] = "ally_discard"
        context["retrieve_target"] = "hero_ally"

        push_steps(state, [
            RetrieveCardStep(card_key="target_retrieve_card", hero_key="retrieve_target"),
        ])
        process_resolution_stack(state)

        # Ally should have the card back in hand
        ally_ref = state.get_hero(HeroID("hero_ally"))
        assert any(c.id == "ally_discard" for c in ally_ref.hand)
        assert len(ally_ref.discard_pile) == 0

    def test_retrieve_defaults_to_actor_when_no_hero_key(self, board):
        """Without hero_key, retrieves for current_actor_id (existing behavior)."""
        card = _make_skill_card("db", "Test", "drinking_buddies")
        bain = Hero(id=HeroID("hero_bain"), name="Bain", deck=[], hand=[])
        bain.current_turn_card = card
        discard_card = _make_filler_card("bain_discard")
        discard_card.state = CardState.DISCARD
        bain.discard_pile = [discard_card]

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
        state.current_actor_id = "hero_bain"
        state.execution_context["my_card"] = "bain_discard"

        push_steps(state, [RetrieveCardStep(card_key="my_card")])
        process_resolution_stack(state)

        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert any(c.id == "bain_discard" for c in bain_ref.hand)

    def test_retrieve_skips_when_hero_key_is_none_in_context(self, board):
        """If hero_key context value is None, step should be skipped gracefully."""
        card = _make_skill_card("db", "Test", "drinking_buddies")
        state = _build_state(board, card)
        state.execution_context["my_card"] = "some_card"
        state.execution_context["target_hero"] = None

        push_steps(state, [
            RetrieveCardStep(card_key="my_card", hero_key="target_hero"),
        ])
        result = process_resolution_stack(state)
        assert result is None  # Stack finished, no crash


# ===========================================================================
# Drinking Buddies effect tests
# ===========================================================================


class TestDrinkingBuddies:
    """Drinking Buddies: You may have a hero in radius retrieve a discarded card.
    If they do, you may also retrieve a discarded card."""

    def test_target_hero_retrieves_then_actor_retrieves(self, board):
        """Happy path: pick ally, ally picks card, then Bain picks card."""
        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        ally_discard = _make_filler_card("ally_discard_1")
        ally_discard.state = CardState.DISCARD
        ally.discard_pile = [ally_discard]

        card = _make_skill_card("drinking_buddies", "Drinking Buddies", "drinking_buddies")
        state = _build_state(board, card, ally=ally)

        bain = state.get_hero(HeroID("hero_bain"))
        bain_discard = _make_filler_card("bain_discard_1")
        bain_discard.state = CardState.DISCARD
        bain.discard_pile = [bain_discard]

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # 1. Choose action (SKILL)
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "CHOOSE_ACTION"
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # 2. Select target hero (ally) — optional
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_ally"}

        # 3. Ally selects card from their discard
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "ally_discard_1"}

        # 4. Bain selects card from own discard (optional)
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "bain_discard_1"}

        # 5. Process remaining steps (retrieve + finalize)
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        ally_ref = state.get_hero(HeroID("hero_ally"))
        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert any(c.id == "ally_discard_1" for c in ally_ref.hand)
        assert any(c.id == "bain_discard_1" for c in bain_ref.hand)

    def test_skip_target_selection_skips_everything(self, board):
        """If Bain skips target selection, no retrieval happens at all."""
        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        ally_discard = _make_filler_card("ally_discard_1")
        ally_discard.state = CardState.DISCARD
        ally.discard_pile = [ally_discard]

        card = _make_skill_card("drinking_buddies", "Drinking Buddies", "drinking_buddies")
        state = _build_state(board, card, ally=ally)

        bain = state.get_hero(HeroID("hero_bain"))
        bain_discard = _make_filler_card("bain_discard_1")
        bain_discard.state = CardState.DISCARD
        bain.discard_pile = [bain_discard]

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # Skip target selection
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        # Should finish without more prompts
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        # Nobody retrieved anything
        ally_ref = state.get_hero(HeroID("hero_ally"))
        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert len(ally_ref.discard_pile) == 1
        assert len(bain_ref.discard_pile) == 1

    def test_actor_can_skip_own_retrieve(self, board):
        """Ally retrieves but Bain skips his own retrieve."""
        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        ally_discard = _make_filler_card("ally_discard_1")
        ally_discard.state = CardState.DISCARD
        ally.discard_pile = [ally_discard]

        card = _make_skill_card("drinking_buddies", "Drinking Buddies", "drinking_buddies")
        state = _build_state(board, card, ally=ally)

        bain = state.get_hero(HeroID("hero_bain"))
        bain_discard = _make_filler_card("bain_discard_1")
        bain_discard.state = CardState.DISCARD
        bain.discard_pile = [bain_discard]

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # Select ally
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "hero_ally"}

        # Ally picks card
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ally_discard_1"}

        # Bain skips his own retrieve
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        ally_ref = state.get_hero(HeroID("hero_ally"))
        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert any(c.id == "ally_discard_1" for c in ally_ref.hand)
        assert len(bain_ref.discard_pile) == 1  # Bain still has his card in discard

    def test_enemy_hero_can_be_target(self, board):
        """Any hero in radius can be targeted, including enemies."""
        enemy = Hero(id=HeroID("hero_enemy"), name="Enemy", deck=[], hand=[])
        enemy_discard = _make_filler_card("enemy_discard_1")
        enemy_discard.state = CardState.DISCARD
        enemy.discard_pile = [enemy_discard]

        card = _make_skill_card("drinking_buddies", "Drinking Buddies", "drinking_buddies")
        state = _build_state(board, card, enemy=enemy)

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # Select enemy hero
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        # Enemy picks card from discard
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "enemy_discard_1"}

        # Bain's retrieve (skip — no cards in discard)
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        enemy_ref = state.get_hero(HeroID("hero_enemy"))
        assert any(c.id == "enemy_discard_1" for c in enemy_ref.hand)

    def test_heroes_without_discards_not_offered(self, board):
        """Heroes with empty discard pile should not appear as targets."""
        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        # ally has no discarded cards

        card = _make_skill_card("drinking_buddies", "Drinking Buddies", "drinking_buddies")
        state = _build_state(board, card, ally=ally)

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # No valid targets (ally has no discard) — step should be skipped or
        # offer no candidates. Since it's optional, it auto-skips.
        req = process_resolution_stack(state)
        while req is not None:
            # Should not prompt for unit selection since no valid targets
            assert req["type"] != "SELECT_UNIT" or len(req.get("options", [])) > 0
            req = process_resolution_stack(state)


# ===========================================================================
# Another One! effect tests
# ===========================================================================


class TestAnotherOne:
    """Another One!: Same as Drinking Buddies + end-of-turn delayed trigger
    that repeats the retrieve sequence."""

    def test_creates_delayed_trigger_effect(self, board):
        """After resolving, a THIS_TURN DELAYED_TRIGGER effect should exist."""
        from goa2.domain.models.effect import EffectType, DurationType

        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        ally_discard = _make_filler_card("ally_discard_1")
        ally_discard.state = CardState.DISCARD
        ally.discard_pile = [ally_discard]

        card = _make_skill_card(
            "another_one", "Another One!", "another_one",
            tier=CardTier.III, radius=3,
        )
        state = _build_state(board, card, ally=ally)

        bain = state.get_hero(HeroID("hero_bain"))
        bain_discard = _make_filler_card("bain_discard_1")
        bain_discard.state = CardState.DISCARD
        bain.discard_pile = [bain_discard]

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # Skip target selection (to get through quickly)
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        # Process until done
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        # A delayed trigger effect should have been created
        delayed = [
            e for e in state.active_effects
            if e.effect_type == EffectType.DELAYED_TRIGGER
            and e.duration == DurationType.THIS_TURN
        ]
        assert len(delayed) == 1
        assert len(delayed[0].finishing_steps) > 0

    def test_delayed_trigger_fires_at_end_of_turn(self, board):
        """When end_turn() is called, the finishing steps should execute."""
        from goa2.domain.models.effect import EffectType, DurationType
        from goa2.engine.phases import end_turn

        ally = Hero(id=HeroID("hero_ally"), name="Ally", deck=[], hand=[])
        ally_d1 = _make_filler_card("ally_d1")
        ally_d1.state = CardState.DISCARD
        ally_d2 = _make_filler_card("ally_d2")
        ally_d2.state = CardState.DISCARD
        ally.discard_pile = [ally_d1, ally_d2]

        card = _make_skill_card(
            "another_one", "Another One!", "another_one",
            tier=CardTier.III, radius=3,
        )
        state = _build_state(board, card, ally=ally)

        bain = state.get_hero(HeroID("hero_bain"))
        bain_d1 = _make_filler_card("bain_d1")
        bain_d1.state = CardState.DISCARD
        bain_d2 = _make_filler_card("bain_d2")
        bain_d2.state = CardState.DISCARD
        bain.discard_pile = [bain_d1, bain_d2]

        push_steps(state, [ResolveCardStep(hero_id="hero_bain")])

        # Choose action
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "SKILL"}

        # Select ally for first retrieve
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "hero_ally"}

        # Ally picks card
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ally_d1"}

        # Bain picks card
        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "bain_d1"}

        # Finish card resolution
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        # Verify first retrieval worked
        ally_ref = state.get_hero(HeroID("hero_ally"))
        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert any(c.id == "ally_d1" for c in ally_ref.hand)
        assert any(c.id == "bain_d1" for c in bain_ref.hand)

        # Now trigger end of turn — this should fire the delayed trigger
        end_turn(state)

        # The finishing steps are now on the stack — drive them
        # SetActorStep sets Bain as actor, then the retrieve sequence runs

        # Select ally for second retrieve
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_ally"}

        # Ally picks second card
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "ally_d2"}

        # Bain picks second card
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "bain_d2"}

        # Finish
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        # Both should have retrieved second cards too
        ally_ref = state.get_hero(HeroID("hero_ally"))
        bain_ref = state.get_hero(HeroID("hero_bain"))
        assert any(c.id == "ally_d2" for c in ally_ref.hand)
        assert any(c.id == "bain_d2" for c in bain_ref.hand)
