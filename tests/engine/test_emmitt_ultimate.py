"""
Emmitt — Alternative Timelines (ultimate) tests.

"You may play two cards each turn; if you do, after the cards are revealed,
retrieve one of your unresolved cards."

TDD paths: docs/superpowers/plans/2026-07-05-emmitt-tdd-paths.md §13.
Locked rulings: two-card commit is optional (commit one + explicit DONE, or a
second commit, closes Emmitt's planning); both cards are publicly revealed;
the retrieve-one choice is mandatory and happens after reveal, before any
hero resolves.
"""

import pytest

import goa2.scripts.emmitt_effects  # noqa: F401  (registers alternative_timelines)
from goa2.domain.models import CardState, GamePhase, TeamColor
from goa2.domain.types import HeroID
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.setup import GameSetup

MAP = "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def session():
    """Emmitt (RED, level 8 → ultimate active) vs Wasp (BLUE), in PLANNING."""
    state = GameSetup.create_game(map_path=MAP, red_heroes=["Emmitt"], blue_heroes=["Wasp"])
    emmitt = state.teams[TeamColor.RED].heroes[0]
    emmitt.level = 8
    return GameSession(state)


def _heroes(session):
    emmitt = session.state.teams[TeamColor.RED].heroes[0]
    wasp = session.state.teams[TeamColor.BLUE].heroes[0]
    return emmitt, wasp


def _card(hero, card_id):
    return next(c for c in hero.hand if c.id == card_id)


class TestTwoCardCommit:
    def test_second_commit_rejected_without_ultimate(self, session):
        """U1: below level 8 the second commit raises (normal single-commit rule)."""
        emmitt, _ = _heroes(session)
        emmitt.level = 7
        session.commit_card(HeroID(emmitt.id), emmitt.hand[0])
        with pytest.raises(ValueError, match="already committed"):
            session.commit_card(HeroID(emmitt.id), emmitt.hand[0])

    def test_second_commit_accepted_with_ultimate(self, session):
        """H1: with the ultimate active a second commit is legal; both leave hand."""
        emmitt, _ = _heroes(session)
        hand_before = len(emmitt.hand)
        card_a, card_b = emmitt.hand[0], emmitt.hand[1]
        session.commit_card(HeroID(emmitt.id), card_a)
        session.commit_card(HeroID(emmitt.id), card_b)
        assert len(emmitt.hand) == hand_before - 2
        assert card_a not in emmitt.hand and card_b not in emmitt.hand
        assert session.current_phase == GamePhase.PLANNING  # Wasp hasn't committed

    def test_third_commit_rejected(self, session):
        """U4: a third commit always raises."""
        emmitt, _ = _heroes(session)
        session.commit_card(HeroID(emmitt.id), emmitt.hand[0])
        session.commit_card(HeroID(emmitt.id), emmitt.hand[0])
        with pytest.raises(ValueError, match="two cards"):
            session.commit_card(HeroID(emmitt.id), emmitt.hand[0])

    def test_planning_waits_for_emmitt_after_first_commit(self, session):
        """H4 setup: after Emmitt's first commit, planning stays open for him
        even when everyone else has committed."""
        emmitt, wasp = _heroes(session)
        session.commit_card(HeroID(emmitt.id), emmitt.hand[0])
        session.commit_card(HeroID(wasp.id), wasp.hand[0])
        assert session.current_phase == GamePhase.PLANNING

    def test_finish_planning_closes_without_second_card(self, session):
        """H4: first commit + explicit DONE → planning closes, no retrieve
        prompt, the committed card resolves normally."""
        emmitt, wasp = _heroes(session)
        card = emmitt.hand[0]
        session.commit_card(HeroID(emmitt.id), card)
        session.commit_card(HeroID(wasp.id), wasp.hand[0])
        result = session.finish_planning(HeroID(emmitt.id))
        assert session.current_phase != GamePhase.PLANNING
        assert emmitt.current_turn_card is card
        assert emmitt.extra_turn_card is None
        # No retrieve prompt: the first input (if any) is not a card choice for Emmitt
        if result.result_type == SessionResultType.INPUT_NEEDED:
            assert "retrieve" not in (result.input_request.prompt or "").lower()

    def test_single_card_hand_auto_completes(self, session):
        """H5: with one card in hand, the single commit auto-closes Emmitt's
        planning (no second card is possible, no DONE needed)."""
        emmitt, wasp = _heroes(session)
        emmitt.hand = emmitt.hand[:1]
        session.commit_card(HeroID(emmitt.id), emmitt.hand[0])
        session.commit_card(HeroID(wasp.id), wasp.hand[0])
        assert session.current_phase != GamePhase.PLANNING


class TestPostRevealRetrieve:
    def _commit_two_and_close(self, session, id_a="reverse_time", id_b="unstable_timeline"):
        emmitt, wasp = _heroes(session)
        card_a = _card(emmitt, id_a)
        card_b = _card(emmitt, id_b)
        session.commit_card(HeroID(emmitt.id), card_a)
        session.commit_card(HeroID(emmitt.id), card_b)
        result = session.commit_card(HeroID(wasp.id), wasp.hand[0])
        return emmitt, wasp, card_a, card_b, result

    def test_retrieve_prompt_after_reveal(self, session):
        """H1/H2: both cards revealed; mandatory card choice routed to Emmitt
        before any hero resolves."""
        emmitt, _wasp, card_a, card_b, result = self._commit_two_and_close(session)
        assert session.current_phase == GamePhase.RESOLUTION
        assert result.result_type == SessionResultType.INPUT_NEEDED
        req = result.input_request
        assert req.player_id == str(emmitt.id)
        option_ids = {o.id for o in req.options}
        assert option_ids == {card_a.id, card_b.id}
        # Both revealed (public) while the choice is pending
        assert card_a.is_facedown is False
        assert card_b.is_facedown is False
        # Nobody has started resolving
        assert session.state.current_actor_id is None

    def test_retrieve_returns_card_to_hand_and_keeps_other(self, session):
        """H2: the chosen card returns to hand; the other stays as the
        unresolved turn card."""
        emmitt, _wasp, card_a, card_b, _ = self._commit_two_and_close(session)
        session.advance({"selection": card_a.id})
        assert card_a in emmitt.hand
        assert card_a.state == CardState.HAND
        assert emmitt.current_turn_card is card_b
        assert emmitt.current_turn_card.state == CardState.UNRESOLVED
        assert emmitt.extra_turn_card is None

    def test_resolution_order_uses_remaining_card(self, session):
        """H3: after retrieving, initiative order uses the remaining card.
        reverse_time has initiative 11 (highest in play) → Emmitt acts first."""
        emmitt, _wasp, card_a, card_b, _ = self._commit_two_and_close(session)
        # retrieve unstable_timeline (init 1), keep reverse_time (init 11)
        session.advance({"selection": card_b.id})
        assert emmitt.current_turn_card is card_a
        assert str(session.state.current_actor_id) == str(emmitt.id)

    def test_opponent_view_shows_both_revealed_cards(self, session):
        """U3: between reveal and retrieve, opponents see both of Emmitt's
        cards (public info)."""
        from goa2.domain.views import build_view

        emmitt, wasp, card_a, card_b, _ = self._commit_two_and_close(session)
        view = build_view(session.state, for_hero_id=str(wasp.id))
        emmitt_view = next(
            h for t in view["teams"].values() for h in t["heroes"] if h["id"] == str(emmitt.id)
        )
        assert emmitt_view["current_turn_card"]["id"] == card_a.id
        assert emmitt_view["extra_turn_card"]["id"] == card_b.id
        # After the retrieve, the extra slot clears and the retrieved card is
        # hidden from opponents again (hand is private)
        session.advance({"selection": card_b.id})
        view = build_view(session.state, for_hero_id=str(wasp.id))
        emmitt_view = next(
            h for t in view["teams"].values() for h in t["heroes"] if h["id"] == str(emmitt.id)
        )
        assert emmitt_view["extra_turn_card"] is None
        assert emmitt_view["hand"] == []

    def test_persistence_roundtrip_mid_retrieve_prompt(self, session):
        """U6: saving and restoring while the retrieve prompt is pending
        preserves both cards and re-emits the same choice."""
        from goa2.domain.state import GameState
        from goa2.engine.handler import process_stack

        emmitt, _wasp, card_a, card_b, _ = self._commit_two_and_close(session)
        dump = session.state.model_dump(mode="json")
        restored = GameState.model_validate(dump)

        r_emmitt = restored.teams[TeamColor.RED].heroes[0]
        assert r_emmitt.current_turn_card.id == card_a.id
        assert r_emmitt.extra_turn_card.id == card_b.id

        # The pending step round-trips and re-emits the choice on the restored state
        result = process_stack(restored)
        assert result.input_request is not None
        assert result.input_request.player_id == str(emmitt.id)
        assert {o.id for o in result.input_request.options} == {card_a.id, card_b.id}
