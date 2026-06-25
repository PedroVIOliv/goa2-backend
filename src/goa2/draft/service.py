from __future__ import annotations

import random

from goa2.domain.models import TeamColor
from goa2.draft.errors import (
    DraftFullError,
    HeroNotClaimableError,
    HeroUnavailableError,
    InvalidDraftPhaseError,
    InvalidTeamError,
    NotActingCaptainError,
    PlayerNotFoundError,
)
from goa2.draft.models import DraftActionType, DraftPlayer, DraftState, DraftStatus
from goa2.draft.modes import get_mode


def get_player(state: DraftState, player_id: str) -> DraftPlayer:
    for p in state.players:
        if p.id == player_id:
            return p
    raise PlayerNotFoundError(f"Player '{player_id}' not found")


def _require_phase(state: DraftState, expected: DraftStatus) -> None:
    if state.status is not expected:
        raise InvalidDraftPhaseError(
            f"Expected draft phase {expected.value}, but draft is {state.status.value}"
        )


def _team_size(state: DraftState, team: TeamColor) -> int:
    return state.red_size if team is TeamColor.RED else state.blue_size


def _members(state: DraftState, team: TeamColor) -> list[DraftPlayer]:
    return [p for p in state.players if p.team is team]


def _ensure_captains(state: DraftState) -> None:
    """Guarantee each team with members has exactly one captain (first member)."""
    for team in (TeamColor.RED, TeamColor.BLUE):
        members = _members(state, team)
        if not members:
            continue
        if not any(p.is_captain for p in members):
            members[0].is_captain = True
        seen = False
        for p in members:
            if p.is_captain and not seen:
                seen = True
            elif p.is_captain:
                p.is_captain = False


def create_draft(
    draft_id: str,
    map_name: str,
    game_type: str,
    draft_mode: str,
    red_size: int,
    blue_size: int,
    host_name: str,
    now: float,
) -> DraftState:
    get_mode(draft_mode)  # validate mode name early (raises KeyError -> caller maps)
    state = DraftState(
        draft_id=draft_id,
        map_name=map_name,
        game_type=game_type,
        draft_mode=draft_mode,
        red_size=red_size,
        blue_size=blue_size,
        created_at=now,
    )
    state.players.append(DraftPlayer(id="p1", display_name=host_name, is_host=True))
    return state


def join(state: DraftState, display_name: str) -> DraftPlayer:
    _require_phase(state, DraftStatus.LOBBY)
    if len(state.players) >= state.red_size + state.blue_size:
        raise DraftFullError("Lobby is full")
    player = DraftPlayer(id=f"p{len(state.players) + 1}", display_name=display_name)
    state.players.append(player)
    return player


def set_team(state: DraftState, player_id: str, team: TeamColor) -> None:
    _require_phase(state, DraftStatus.LOBBY)
    player = get_player(state, player_id)
    if player.team is not team and len(_members(state, team)) >= _team_size(state, team):
        raise InvalidTeamError(f"Team {team.value} is full")
    player.team = team
    player.is_captain = False
    _ensure_captains(state)


def randomize_teams(state: DraftState, rng: random.Random) -> None:
    _require_phase(state, DraftStatus.LOBBY)
    shuffled = list(state.players)
    rng.shuffle(shuffled)
    for p in state.players:
        p.team = None
        p.is_captain = False
    for i, p in enumerate(shuffled):
        p.team = TeamColor.RED if i < state.red_size else TeamColor.BLUE
    _ensure_captains(state)


def set_captain(state: DraftState, player_id: str) -> None:
    _require_phase(state, DraftStatus.LOBBY)
    player = get_player(state, player_id)
    if player.team is None:
        raise InvalidTeamError("Player must be on a team to be captain")
    for p in _members(state, player.team):
        p.is_captain = p.id == player_id


def start_draft(state: DraftState, all_heroes: list[str], rng: random.Random) -> None:
    _require_phase(state, DraftStatus.LOBBY)
    for team in (TeamColor.RED, TeamColor.BLUE):
        members = _members(state, team)
        if len(members) != _team_size(state, team):
            raise InvalidDraftPhaseError(f"Team {team.value} is not full")
        if not any(p.is_captain for p in members):
            raise InvalidDraftPhaseError(f"Team {team.value} has no captain")
    mode = get_mode(state.draft_mode)
    state.hero_pool = mode.hero_pool(all_heroes)
    state.first_team = rng.choice([TeamColor.RED, TeamColor.BLUE])
    state.sequence = mode.build_sequence(state.red_size, state.blue_size, state.first_team)
    state.current_index = 0
    state.status = DraftStatus.DRAFTING


def available_heroes(state: DraftState) -> list[str]:
    taken = set(state.bans[TeamColor.RED]) | set(state.bans[TeamColor.BLUE])
    taken |= set(state.picks[TeamColor.RED]) | set(state.picks[TeamColor.BLUE])
    return [h for h in state.hero_pool if h not in taken]


def apply_action(state: DraftState, player_id: str, hero: str) -> None:
    _require_phase(state, DraftStatus.DRAFTING)
    step = state.sequence[state.current_index]
    player = get_player(state, player_id)
    if not (player.is_captain and player.team is step.team):
        raise NotActingCaptainError(f"Only team {step.team.value}'s captain may act on this step")
    if hero not in available_heroes(state):
        raise HeroUnavailableError(f"Hero '{hero}' is not available")
    if step.action is DraftActionType.BAN:
        state.bans[step.team].append(hero)
    else:
        state.picks[step.team].append(hero)
    state.current_index += 1
    if state.current_index >= len(state.sequence):
        state.status = DraftStatus.CLAIMING


def claim_hero(state: DraftState, player_id: str, hero: str) -> None:
    _require_phase(state, DraftStatus.CLAIMING)
    player = get_player(state, player_id)
    if player.team is None:
        raise InvalidTeamError("Player has no team")
    if hero not in state.picks[player.team]:
        raise HeroNotClaimableError(f"Hero '{hero}' was not drafted by your team")
    if any(p.claimed_hero == hero for p in state.players if p.id != player_id):
        raise HeroNotClaimableError(f"Hero '{hero}' already claimed")
    player.claimed_hero = hero


def is_ready_to_create_game(state: DraftState) -> bool:
    return state.status is DraftStatus.CLAIMING and all(
        p.claimed_hero is not None for p in state.players
    )


def team_hero_lists(state: DraftState) -> tuple[list[str], list[str]]:
    red = [p.claimed_hero for p in _members(state, TeamColor.RED) if p.claimed_hero]
    blue = [p.claimed_hero for p in _members(state, TeamColor.BLUE) if p.claimed_hero]
    return red, blue
