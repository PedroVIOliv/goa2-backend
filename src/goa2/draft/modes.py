from __future__ import annotations

import random
from abc import ABC, abstractmethod

from goa2.domain.models import TeamColor
from goa2.draft.errors import InvalidDraftPhaseError
from goa2.draft.models import DraftActionType, DraftStep


def _other(team: TeamColor) -> TeamColor:
    return TeamColor.BLUE if team is TeamColor.RED else TeamColor.RED


class DraftMode(ABC):
    name: str
    description: str

    def hero_pool(
        self,
        all_heroes: list[str],
        *,
        red_size: int,
        blue_size: int,
        rng: random.Random,
    ) -> list[str]:
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


_FIRST_SLOT = "A"  # the coin-flip winner

# One round per player: two bans, then two picks. Each entry is (ban order, pick
# order) in coin-flip-relative slots, and an n-vs-n draft uses the first n rounds.
# Hand-authored — the ban order alternates except in the last round, and the pick
# order does not track the ban order, so no formula states this more clearly.
#
# Rounds 4 and 5 are unreachable while service.MAX_PLAYERS caps the lobby at 6.
# They are kept so raising that cap is most of what 4v4/5v5 needs: the pool
# formula and the equal-teams rule already generalise, but 8- and 10-player games
# only seat on double-lane maps, so lifting the cap also means gating those
# brackets on a map that supports them.
_CHAOS_ROUNDS: list[tuple[str, str]] = [
    ("AB", "AB"),
    ("BA", "BA"),
    ("AB", "BA"),
    ("BA", "AB"),
    ("BA", "BA"),
]

CHAOS_MIN_TEAM_SIZE = 2
CHAOS_MAX_TEAM_SIZE = len(_CHAOS_ROUNDS)

# Every ban and pick consumes one hero (4n of them); the draft ends with four
# heroes that were never banned and never picked.
CHAOS_UNUSED_HEROES = 4


def _chaos_players_per_team(red_size: int, blue_size: int) -> int:
    if red_size != blue_size:
        raise InvalidDraftPhaseError(
            f"Chaos Draft requires equal teams; got {red_size} vs {blue_size}"
        )
    if not CHAOS_MIN_TEAM_SIZE <= red_size <= CHAOS_MAX_TEAM_SIZE:
        raise InvalidDraftPhaseError(
            f"Chaos Draft supports {CHAOS_MIN_TEAM_SIZE}v{CHAOS_MIN_TEAM_SIZE} through "
            f"{CHAOS_MAX_TEAM_SIZE}v{CHAOS_MAX_TEAM_SIZE}; got {red_size}v{blue_size}"
        )
    return red_size


class ChaosDraftMode(DraftMode):
    name = "chaos"
    description = "A random slice of the roster is the whole draft."

    def hero_pool(
        self,
        all_heroes: list[str],
        *,
        red_size: int,
        blue_size: int,
        rng: random.Random,
    ) -> list[str]:
        per_team = _chaos_players_per_team(red_size, blue_size)
        size = 4 * per_team + CHAOS_UNUSED_HEROES
        if len(all_heroes) < size:
            raise InvalidDraftPhaseError(
                f"Chaos Draft needs {size} heroes for {per_team}v{per_team}, "
                f"but only {len(all_heroes)} are available"
            )
        shuffled = list(all_heroes)
        rng.shuffle(shuffled)
        return shuffled[:size]

    def build_sequence(
        self, red_size: int, blue_size: int, first_team: TeamColor
    ) -> list[DraftStep]:
        per_team = _chaos_players_per_team(red_size, blue_size)
        second = _other(first_team)

        def team_for(slot: str) -> TeamColor:
            return first_team if slot == _FIRST_SLOT else second

        steps: list[DraftStep] = []
        for ban_order, pick_order in _CHAOS_ROUNDS[:per_team]:
            for action, order in (
                (DraftActionType.BAN, ban_order),
                (DraftActionType.PICK, pick_order),
            ):
                for slot in order:
                    steps.append(DraftStep(index=len(steps), action=action, team=team_for(slot)))
        return steps


DRAFT_MODES: dict[str, DraftMode] = {
    SequentialBanPickMode().name: SequentialBanPickMode(),
    SimpleDraftMode().name: SimpleDraftMode(),
    ChaosDraftMode().name: ChaosDraftMode(),
}


def get_mode(name: str) -> DraftMode:
    return DRAFT_MODES[name]
