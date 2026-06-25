from goa2.domain.models import TeamColor
from goa2.draft.models import DraftActionType
from goa2.draft.modes import DRAFT_MODES, SequentialBanPickMode, get_mode


def test_registry_has_sequential_mode():
    assert "sequential_ban_pick" in DRAFT_MODES
    assert get_mode("sequential_ban_pick").name == "sequential_ban_pick"


def test_sequence_2v2_one_ban_each():
    mode = SequentialBanPickMode(bans_per_team=1)
    seq = mode.build_sequence(2, 2, TeamColor.RED)
    kinds = [(s.action, s.team) for s in seq]
    assert kinds == [
        (DraftActionType.BAN, TeamColor.RED),
        (DraftActionType.BAN, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
        (DraftActionType.PICK, TeamColor.RED),
        (DraftActionType.PICK, TeamColor.BLUE),
    ]
    assert [s.index for s in seq] == [0, 1, 2, 3, 4, 5]


def test_sequence_uneven_3v2_fills_each_team():
    seq = SequentialBanPickMode(bans_per_team=1).build_sequence(3, 2, TeamColor.RED)
    picks = [s.team for s in seq if s.action is DraftActionType.PICK]
    assert picks.count(TeamColor.RED) == 3
    assert picks.count(TeamColor.BLUE) == 2


def test_hero_pool_is_all_heroes():
    pool = get_mode("sequential_ban_pick").hero_pool(["Arien", "Wasp"])
    assert pool == ["Arien", "Wasp"]
