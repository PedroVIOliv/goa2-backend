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
    description = "Ban pair before each pick pair; one captain drafts per team."

    def build_sequence(
        self, red_size: int, blue_size: int, first_team: TeamColor
    ) -> list[DraftStep]:
        second = _other(first_team)
        size = {TeamColor.RED: red_size, TeamColor.BLUE: blue_size}
        counts = {first_team: 0, second: 0}
        steps: list[DraftStep] = []

        for round_index in range(max(red_size, blue_size)):
            ban_order = (first_team, second) if round_index % 2 == 0 else (second, first_team)
            for team in ban_order:
                steps.append(DraftStep(index=len(steps), action=DraftActionType.BAN, team=team))

            pick_order = (first_team, second) if round_index == 0 else (second, first_team)
            for team in pick_order:
                if counts[team] >= size[team]:
                    continue
                steps.append(DraftStep(index=len(steps), action=DraftActionType.PICK, team=team))
                counts[team] += 1

        return steps


class SimpleDraftMode(DraftMode):
    name = "simple_draft"
    description = "No bans; snake picks starting with one pick for the first team."

    def build_sequence(
        self, red_size: int, blue_size: int, first_team: TeamColor
    ) -> list[DraftStep]:
        second = _other(first_team)
        size = {TeamColor.RED: red_size, TeamColor.BLUE: blue_size}
        counts = {first_team: 0, second: 0}
        steps: list[DraftStep] = []
        turn = first_team
        quota = 1

        while counts[first_team] < size[first_team] or counts[second] < size[second]:
            remaining = size[turn] - counts[turn]
            for _ in range(min(quota, remaining)):
                steps.append(DraftStep(index=len(steps), action=DraftActionType.PICK, team=turn))
                counts[turn] += 1
            turn = _other(turn)
            quota = 2

        return steps


DRAFT_MODES: dict[str, DraftMode] = {
    SequentialBanPickMode().name: SequentialBanPickMode(),
    SimpleDraftMode().name: SimpleDraftMode(),
}


def get_mode(name: str) -> DraftMode:
    return DRAFT_MODES[name]
