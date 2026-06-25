import random

import pytest

from goa2.domain.models import TeamColor
from goa2.draft import service
from goa2.draft.errors import (
    DraftFullError,
    HeroNotClaimableError,
    HeroUnavailableError,
    InvalidDraftPhaseError,
    InvalidTeamError,
    NotActingCaptainError,
)
from goa2.draft.models import DraftStatus

HEROES = ["Arien", "Wasp", "Brogan", "Sabina", "Bain", "Min"]


def _lobby_2v2():
    st = service.create_draft(
        "d1", "forgotten_island", "LONG", "sequential_ban_pick", 2, 2, "Alice", now=0.0
    )
    service.join(st, "Bob")
    service.join(st, "Carol")
    service.join(st, "Dave")
    return st


def test_create_adds_host_as_player_one():
    st = service.create_draft("d1", "m", "LONG", "sequential_ban_pick", 2, 2, "Alice", now=0.0)
    assert st.players[0].id == "p1" and st.players[0].is_host
    assert st.status is DraftStatus.LOBBY


def test_join_full_lobby_rejected():
    st = _lobby_2v2()
    with pytest.raises(DraftFullError):
        service.join(st, "Eve")


def test_set_team_and_auto_captain():
    st = _lobby_2v2()
    service.set_team(st, "p1", TeamColor.RED)
    service.set_team(st, "p2", TeamColor.RED)
    reds = [p for p in st.players if p.team is TeamColor.RED]
    assert sum(p.is_captain for p in reds) == 1
    assert reds[0].is_captain


def test_set_team_over_capacity_rejected():
    st = _lobby_2v2()
    service.set_team(st, "p1", TeamColor.RED)
    service.set_team(st, "p2", TeamColor.RED)
    with pytest.raises(InvalidTeamError):
        service.set_team(st, "p3", TeamColor.RED)


def test_randomize_teams_balanced_with_captains():
    st = _lobby_2v2()
    service.randomize_teams(st, random.Random(0))
    reds = [p for p in st.players if p.team is TeamColor.RED]
    blues = [p for p in st.players if p.team is TeamColor.BLUE]
    assert len(reds) == 2 and len(blues) == 2
    assert sum(p.is_captain for p in reds) == 1
    assert sum(p.is_captain for p in blues) == 1


def _start_2v2(st):
    service.set_team(st, "p1", TeamColor.RED)
    service.set_team(st, "p2", TeamColor.RED)
    service.set_team(st, "p3", TeamColor.BLUE)
    service.set_team(st, "p4", TeamColor.BLUE)
    service.start_draft(st, HEROES, random.Random(0))


def test_full_draft_then_claim_then_ready():
    st = _lobby_2v2()
    _start_2v2(st)
    assert st.status is DraftStatus.DRAFTING
    red_cap = next(p.id for p in st.players if p.team is TeamColor.RED and p.is_captain)
    blue_cap = next(p.id for p in st.players if p.team is TeamColor.BLUE and p.is_captain)

    pool = iter(HEROES)
    for step in st.sequence:
        cap = red_cap if step.team is TeamColor.RED else blue_cap
        service.apply_action(st, cap, next(pool))
    assert st.status is DraftStatus.CLAIMING
    assert not service.is_ready_to_create_game(st)

    for team in (TeamColor.RED, TeamColor.BLUE):
        drafted = list(st.picks[team])
        members = [p for p in st.players if p.team is team]
        for player, hero in zip(members, drafted, strict=True):
            service.claim_hero(st, player.id, hero)
    assert service.is_ready_to_create_game(st)
    red, blue = service.team_hero_lists(st)
    assert len(red) == 2 and len(blue) == 2


def test_action_wrong_captain_rejected():
    st = _lobby_2v2()
    _start_2v2(st)
    first = st.sequence[0]
    wrong_team = TeamColor.BLUE if first.team is TeamColor.RED else TeamColor.RED
    wrong_cap = next(p.id for p in st.players if p.team is wrong_team and p.is_captain)
    with pytest.raises(NotActingCaptainError):
        service.apply_action(st, wrong_cap, "Arien")


def test_action_unavailable_hero_rejected():
    st = _lobby_2v2()
    _start_2v2(st)
    cap = next(p.id for p in st.players if p.team is st.sequence[0].team and p.is_captain)
    service.apply_action(st, cap, "Arien")
    nxt = st.sequence[st.current_index]
    cap2 = next(p.id for p in st.players if p.team is nxt.team and p.is_captain)
    with pytest.raises(HeroUnavailableError):
        service.apply_action(st, cap2, "Arien")


def test_claim_outside_team_pool_rejected():
    st = _lobby_2v2()
    _start_2v2(st)
    cap_by_team = {
        t: next(p.id for p in st.players if p.team is t and p.is_captain)
        for t in (TeamColor.RED, TeamColor.BLUE)
    }
    pool = iter(HEROES)
    for step in st.sequence:
        service.apply_action(st, cap_by_team[step.team], next(pool))
    red_player = next(p for p in st.players if p.team is TeamColor.RED)
    blue_hero = st.picks[TeamColor.BLUE][0]
    with pytest.raises(HeroNotClaimableError):
        service.claim_hero(st, red_player.id, blue_hero)


def test_start_before_lobby_full_rejected():
    st = _lobby_2v2()
    service.set_team(st, "p1", TeamColor.RED)
    with pytest.raises(InvalidDraftPhaseError):
        service.start_draft(st, HEROES, random.Random(0))
