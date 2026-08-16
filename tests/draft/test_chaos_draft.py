"""Chaos Draft: random hero pool sized to the teams, table-driven ban/pick order."""

from __future__ import annotations

import random

import pytest

from goa2.domain.models import TeamColor
from goa2.draft import service
from goa2.draft.errors import (
    ChaosRequiresFullRosterError,
    InvalidDraftPhaseError,
    NotActingCaptainError,
)
from goa2.draft.models import DraftActionType, DraftStatus
from goa2.draft.modes import DRAFT_MODES, ChaosDraftMode, get_mode

ROSTER = [f"Hero{i:02d}" for i in range(32)]

A = "A"
B = "B"
BAN = DraftActionType.BAN
PICK = DraftActionType.PICK

# The spec's draft order, verbatim, in coin-flip-relative slots.
EXPECTED_ORDER: dict[int, list[tuple[DraftActionType, str]]] = {
    2: [
        (BAN, A),
        (BAN, B),
        (PICK, A),
        (PICK, B),
        (BAN, B),
        (BAN, A),
        (PICK, B),
        (PICK, A),
    ],
    3: [
        (BAN, A),
        (BAN, B),
        (PICK, A),
        (PICK, B),
        (BAN, B),
        (BAN, A),
        (PICK, B),
        (PICK, A),
        (BAN, A),
        (BAN, B),
        (PICK, B),
        (PICK, A),
    ],
    4: [
        (BAN, A),
        (BAN, B),
        (PICK, A),
        (PICK, B),
        (BAN, B),
        (BAN, A),
        (PICK, B),
        (PICK, A),
        (BAN, A),
        (BAN, B),
        (PICK, B),
        (PICK, A),
        (BAN, B),
        (BAN, A),
        (PICK, A),
        (PICK, B),
    ],
    5: [
        (BAN, A),
        (BAN, B),
        (PICK, A),
        (PICK, B),
        (BAN, B),
        (BAN, A),
        (PICK, B),
        (PICK, A),
        (BAN, A),
        (BAN, B),
        (PICK, B),
        (PICK, A),
        (BAN, B),
        (BAN, A),
        (PICK, A),
        (PICK, B),
        (BAN, B),
        (BAN, A),
        (PICK, B),
        (PICK, A),
    ],
}


def _resolve(slots: list[tuple[DraftActionType, str]], first: TeamColor):
    other = TeamColor.BLUE if first is TeamColor.RED else TeamColor.RED
    return [(action, first if slot == A else other) for action, slot in slots]


# ---------------------------------------------------------------- mode: registry


def test_chaos_is_registered():
    assert "chaos" in DRAFT_MODES
    assert get_mode("chaos").name == "chaos"


# ---------------------------------------------------------------- mode: sequence


@pytest.mark.parametrize("n", [2, 3, 4, 5])
@pytest.mark.parametrize("first", [TeamColor.RED, TeamColor.BLUE])
def test_sequence_matches_spec_order(n: int, first: TeamColor):
    seq = get_mode("chaos").build_sequence(n, n, first)
    assert [(s.action, s.team) for s in seq] == _resolve(EXPECTED_ORDER[n], first)
    assert [s.index for s in seq] == list(range(len(seq)))


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_sequence_gives_every_player_exactly_one_pick(n: int):
    seq = get_mode("chaos").build_sequence(n, n, TeamColor.RED)
    picks = [s.team for s in seq if s.action is DraftActionType.PICK]
    bans = [s.team for s in seq if s.action is DraftActionType.BAN]
    assert picks.count(TeamColor.RED) == picks.count(TeamColor.BLUE) == n
    assert bans.count(TeamColor.RED) == bans.count(TeamColor.BLUE) == n


def test_sequence_rejects_unequal_teams():
    with pytest.raises(InvalidDraftPhaseError):
        get_mode("chaos").build_sequence(3, 2, TeamColor.RED)


def test_sequence_rejects_unsupported_team_size():
    with pytest.raises(InvalidDraftPhaseError):
        get_mode("chaos").build_sequence(6, 6, TeamColor.RED)


# ---------------------------------------------------------------- mode: pool


@pytest.mark.parametrize("n,expected", [(2, 12), (3, 16), (4, 20), (5, 24)])
def test_pool_size_is_four_n_plus_four(n: int, expected: int):
    pool = get_mode("chaos").hero_pool(ROSTER, red_size=n, blue_size=n, rng=random.Random(1))
    assert len(pool) == expected
    assert len(set(pool)) == expected
    assert set(pool) <= set(ROSTER)


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_pool_leaves_exactly_four_heroes_unused(n: int):
    mode = get_mode("chaos")
    pool = mode.hero_pool(ROSTER, red_size=n, blue_size=n, rng=random.Random(2))
    assert len(pool) - len(mode.build_sequence(n, n, TeamColor.RED)) == 4


def test_pool_is_random_but_reproducible_for_a_seed():
    mode = ChaosDraftMode()
    kwargs = {"red_size": 2, "blue_size": 2}
    same = mode.hero_pool(ROSTER, rng=random.Random(7), **kwargs)
    again = mode.hero_pool(ROSTER, rng=random.Random(7), **kwargs)
    other = mode.hero_pool(ROSTER, rng=random.Random(8), **kwargs)
    assert same == again
    assert same != other


def test_pool_rejects_roster_too_small_for_the_bracket():
    with pytest.raises(InvalidDraftPhaseError):
        get_mode("chaos").hero_pool(ROSTER[:11], red_size=2, blue_size=2, rng=random.Random(0))


def test_pool_rejects_unequal_teams():
    with pytest.raises(InvalidDraftPhaseError):
        get_mode("chaos").hero_pool(ROSTER, red_size=3, blue_size=2, rng=random.Random(0))


def test_other_modes_ignore_the_pool_arguments():
    for name in ("sequential_ban_pick", "simple_draft"):
        pool = get_mode(name).hero_pool(ROSTER, red_size=2, blue_size=2, rng=random.Random(0))
        assert pool == ROSTER


# ---------------------------------------------------------------- service


def _chaos_lobby(n: int = 2) -> object:
    st = service.create_draft("d1", "forgotten_island", "LONG", "chaos", "Alice", now=0.0)
    for i in range(2 * n - 1):
        service.join(st, f"P{i}")
    for i, player in enumerate(st.players):
        service.set_team(st, player.id, TeamColor.RED if i < n else TeamColor.BLUE)
    return st


def _start(st, seed: int = 0):
    service.start_draft(st, ROSTER, random.Random(seed))
    return st


def test_start_draws_a_random_subset_of_the_roster():
    st = _start(_chaos_lobby(2))
    assert len(st.hero_pool) == 12
    assert set(st.hero_pool) < set(ROSTER)
    assert len(st.sequence) == 8


def test_start_rejects_unequal_teams():
    # 3v2 passes the lobby's own balance rule (diff <= 1), so this reaches the
    # stricter n-vs-n requirement that chaos's pool and order tables depend on.
    st = _chaos_lobby(2)
    service.join(st, "Eve")
    service.set_team(st, st.players[4].id, TeamColor.RED)
    with pytest.raises(InvalidDraftPhaseError, match="equal teams"):
        service.start_draft(st, ROSTER, random.Random(0))


def test_only_the_captain_may_act():
    st = _start(_chaos_lobby(2))
    teammate = next(p for p in st.players if p.team is st.first_team and not p.is_captain)
    with pytest.raises(NotActingCaptainError):
        service.apply_action(st, teammate.id, st.hero_pool[0])

    captain = next(p for p in st.players if p.team is st.first_team and p.is_captain)
    service.apply_action(st, captain.id, st.hero_pool[0])
    assert st.bans[st.first_team] == [st.hero_pool[0]]


def test_a_player_may_not_act_on_the_other_teams_step():
    st = _start(_chaos_lobby(2))
    second = TeamColor.BLUE if st.first_team is TeamColor.RED else TeamColor.RED
    wrong = next(p for p in st.players if p.team is second)
    with pytest.raises(NotActingCaptainError):
        service.apply_action(st, wrong.id, st.hero_pool[0])


def test_unassigned_players_may_not_act():
    st = _chaos_lobby(2)
    spectator = service.join(st, "Zed")
    _start(st)
    with pytest.raises(NotActingCaptainError):
        service.apply_action(st, spectator.id, st.hero_pool[0])


def test_full_chaos_draft_ends_in_claiming_with_four_heroes_unused():
    st = _start(_chaos_lobby(2))
    while st.status is DraftStatus.DRAFTING:
        step = st.sequence[st.current_index]
        actor = next(p for p in st.players if p.team is step.team)
        service.apply_action(st, actor.id, service.available_heroes(st)[0])

    assert st.status is DraftStatus.CLAIMING
    assert len(service.available_heroes(st)) == 4
    assert len(st.picks[TeamColor.RED]) == len(st.picks[TeamColor.BLUE]) == 2
    assert len(st.bans[TeamColor.RED]) == len(st.bans[TeamColor.BLUE]) == 2


def test_claiming_still_assigns_from_the_team_pool():
    st = _start(_chaos_lobby(2))
    while st.status is DraftStatus.DRAFTING:
        step = st.sequence[st.current_index]
        actor = next(p for p in st.players if p.team is step.team)
        service.apply_action(st, actor.id, service.available_heroes(st)[0])

    for team in (TeamColor.RED, TeamColor.BLUE):
        members = [p for p in st.players if p.team is team]
        for player, hero in zip(members, st.picks[team], strict=False):
            service.claim_hero(st, player.id, hero)
    assert service.is_ready_to_create_game(st)


# ---------------------------------------------------------------- star-cap coupling


def test_chaos_cannot_be_created_below_four_stars():
    with pytest.raises(ChaosRequiresFullRosterError):
        service.create_draft(
            "d1", "forgotten_island", "LONG", "chaos", "Alice", now=0.0, max_hero_stars=3
        )


def test_chaos_cannot_be_selected_while_the_cap_is_low():
    st = service.create_draft(
        "d1",
        "forgotten_island",
        "LONG",
        "sequential_ban_pick",
        "Alice",
        now=0.0,
        max_hero_stars=2,
    )
    with pytest.raises(ChaosRequiresFullRosterError):
        service.update_settings(st, draft_mode="chaos")
    assert st.draft_mode == "sequential_ban_pick"
    assert st.max_hero_stars == 2


def test_the_cap_cannot_be_lowered_while_chaos_is_selected():
    st = service.create_draft("d1", "forgotten_island", "LONG", "chaos", "Alice", now=0.0)
    with pytest.raises(ChaosRequiresFullRosterError):
        service.update_settings(st, max_hero_stars=3)
    assert st.max_hero_stars == 4


def test_chaos_and_the_full_roster_may_be_set_together():
    st = service.create_draft(
        "d1",
        "forgotten_island",
        "LONG",
        "sequential_ban_pick",
        "Alice",
        now=0.0,
        max_hero_stars=2,
    )
    service.update_settings(st, draft_mode="chaos", max_hero_stars=4)
    assert st.draft_mode == "chaos" and st.max_hero_stars == 4


def test_start_rejects_chaos_below_four_stars():
    st = _chaos_lobby(2)
    st.max_hero_stars = 3  # bypass the setting guards
    with pytest.raises(ChaosRequiresFullRosterError):
        service.start_draft(st, ROSTER, random.Random(0))
