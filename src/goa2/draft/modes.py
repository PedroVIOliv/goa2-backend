from __future__ import annotations

from abc import ABC, abstractmethod

from goa2.domain.models import TeamColor
from goa2.draft.models import DraftActionType, DraftStep


def _other(team: TeamColor) -> TeamColor:
    return TeamColor.BLUE if team is TeamColor.RED else TeamColor.RED


class DraftMode(ABC):
    name: str
    description: str

    def hero_pool(self, all_heroes: list[str]) -> list[str]:
        return list(all_heroes)

    @abstractmethod
    def build_sequence(
        self, red_size: int, blue_size: int, first_team: TeamColor
    ) -> list[DraftStep]: ...


class SequentialBanPickMode(DraftMode):
    name = "sequential_ban_pick"
    description = "Alternating bans then alternating picks; one captain drafts per team."

    def __init__(self, bans_per_team: int = 1) -> None:
        self.bans_per_team = bans_per_team

    def build_sequence(
        self, red_size: int, blue_size: int, first_team: TeamColor
    ) -> list[DraftStep]:
        second = _other(first_team)
        size = {TeamColor.RED: red_size, TeamColor.BLUE: blue_size}
        raw: list[tuple[DraftActionType, TeamColor]] = []

        for _ in range(self.bans_per_team):
            raw.append((DraftActionType.BAN, first_team))
            raw.append((DraftActionType.BAN, second))

        counts = {first_team: 0, second: 0}
        turn = first_team
        while counts[first_team] < size[first_team] or counts[second] < size[second]:
            if counts[turn] < size[turn]:
                raw.append((DraftActionType.PICK, turn))
                counts[turn] += 1
            turn = _other(turn)

        return [
            DraftStep(index=i, action=action, team=team) for i, (action, team) in enumerate(raw)
        ]


DRAFT_MODES: dict[str, DraftMode] = {
    SequentialBanPickMode().name: SequentialBanPickMode(),
}


def get_mode(name: str) -> DraftMode:
    return DRAFT_MODES[name]
