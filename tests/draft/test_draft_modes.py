import random

from goa2.domain.models import TeamColor
from goa2.draft.models import DraftActionType
from goa2.draft.modes import DRAFT_MODES, SequentialBanPickMode, get_mode


def test_registry_has_sequential_mode():
    assert "sequential_ban_pick" in DRAFT_MODES
    assert get_mode("sequential_ban_pick").name == "sequential_ban_pick"


def test_registry_has_simple_draft_mode():
    assert "simple_draft" in DRAFT_MODES
    assert get_mode("simple_draft").name == "simple_draft"


def test_simple_draft_2v2_snake_order():
    seq = get_mode("simple_draft").build_sequence(2, 2, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
    ]
    assert [s.index for s in seq] == list(range(len(seq)))


def test_simple_draft_3v3_snake_order():
    seq = get_mode("simple_draft").build_sequence(3, 3, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
    ]


def test_simple_draft_uneven_3v2_fills_each_team():
    seq = get_mode("simple_draft").build_sequence(3, 2, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.RED),
    ]


def test_sequence_2v2_bans_before_each_pick_round():
    mode = SequentialBanPickMode()
    seq = mode.build_sequence(2, 2, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
    ]
    assert [s.index for s in seq] == list(range(len(seq)))


def test_sequence_3v3_uses_requested_pick_ban_order():
    seq = SequentialBanPickMode().build_sequence(3, 3, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
    ]


def test_sequence_uneven_3v2_fills_each_team():
    seq = SequentialBanPickMode().build_sequence(3, 2, TeamColor.RED)
    picks = [s.team for s in seq if s.action is DraftActionType.PICK]
    assert picks.count(TeamColor.RED) == 3
    assert picks.count(TeamColor.BLUE) == 2


def test_hero_pool_is_all_heroes():
    pool = get_mode("sequential_ban_pick").hero_pool(
        ["Arien", "Wasp"], red_size=1, blue_size=1, rng=random.Random(0)
    )
    assert pool == ["Arien", "Wasp"]
