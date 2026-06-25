# Character Draft Lobby Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pre-game draft lobby where a host shares a link, friends join and pick/randomize teams, per-team captains run a ban/pick draft, players claim a drafted hero, and the existing game is then created from the result.

**Architecture:** A standalone, framework-free `src/goa2/draft/` package (models, pluggable modes, pure transition service, typed errors) drives an in-memory `DraftRegistry` and REST router in the server layer. On completion the draft calls the unchanged `GameSetup.create_game(...)` and registers a normal game in the existing `GameRegistry`, then hands each player their hero bearer token.

**Tech Stack:** Python 3.11+, Pydantic V2, FastAPI, pytest, uv.

## Global Constraints

- Python 3.11+, Pydantic V2 models (`BaseModel`), `from __future__ import annotations` at top of each module (matches existing server files).
- Run tests with `PYTHONPATH=src uv run pytest <paths> -q`.
- Lint/type gates (pre-commit runs them): `uv run ruff check src/`, `uv run black src/`, `uv run mypy src/` must pass.
- Heroes are referenced by **display name** (e.g. `"Arien"`), matching `HeroRegistry` keys and `GameSetup.create_game`'s `red_heroes`/`blue_heroes` params.
- Draft is **in-memory only** — no disk persistence, no `save_dir`.
- This work is **additive**: do not change existing `/games` endpoints, `domain/` contracts, or game-side `server/models.py` shapes.
- Commit messages: no `Co-Authored-By` line, no mention of Claude/Claude Code. Commit directly on `main`.
- `TeamColor`, `GameType` import from `goa2.domain.models`. `TeamColor` is a `str` Enum with `.RED`/`.BLUE` and `.value` `"RED"`/`"BLUE"`.

---

### Task 1: Draft data models & enums

**Files:**
- Create: `src/goa2/draft/__init__.py` (empty)
- Create: `src/goa2/draft/models.py`
- Test: `tests/draft/test_draft_models.py`

**Interfaces:**
- Produces: `DraftStatus`, `DraftActionType` (str Enums); `DraftPlayer`, `DraftStep`, `DraftState` (Pydantic models). `DraftState` fields exactly as below.

- [ ] **Step 1: Write the failing test**

```python
# tests/draft/test_draft_models.py
from goa2.domain.models import TeamColor
from goa2.draft.models import (
    DraftState, DraftPlayer, DraftStep, DraftStatus, DraftActionType,
)


def test_draft_state_defaults_and_roundtrip():
    state = DraftState(
        draft_id="d1", map_name="forgotten_island", game_type="LONG",
        draft_mode="sequential_ban_pick", red_size=2, blue_size=2, created_at=1.0,
    )
    assert state.status is DraftStatus.LOBBY
    assert state.players == []
    assert state.bans == {TeamColor.RED: [], TeamColor.BLUE: []}
    assert state.picks == {TeamColor.RED: [], TeamColor.BLUE: []}
    assert state.current_index == 0
    assert state.game_id is None
    # JSON round-trip keeps enum keys as their string values
    dumped = state.model_dump(mode="json")
    assert dumped["bans"] == {"RED": [], "BLUE": []}
    assert dumped["status"] == "LOBBY"


def test_player_and_step():
    p = DraftPlayer(id="p1", display_name="Alice", is_host=True)
    assert p.team is None and p.claimed_hero is None and p.is_captain is False
    s = DraftStep(index=0, action=DraftActionType.BAN, team=TeamColor.RED)
    assert s.action is DraftActionType.BAN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'goa2.draft'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/goa2/draft/__init__.py
```
```python
# src/goa2/draft/models.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from goa2.domain.models import TeamColor


class DraftStatus(str, Enum):
    LOBBY = "LOBBY"
    DRAFTING = "DRAFTING"
    CLAIMING = "CLAIMING"
    COMPLETE = "COMPLETE"


class DraftActionType(str, Enum):
    BAN = "BAN"
    PICK = "PICK"


class DraftPlayer(BaseModel):
    id: str
    display_name: str
    team: TeamColor | None = None
    is_host: bool = False
    is_captain: bool = False
    claimed_hero: str | None = None


class DraftStep(BaseModel):
    index: int
    action: DraftActionType
    team: TeamColor


def _empty_team_lists() -> dict[TeamColor, list[str]]:
    return {TeamColor.RED: [], TeamColor.BLUE: []}


class DraftState(BaseModel):
    draft_id: str
    status: DraftStatus = DraftStatus.LOBBY
    map_name: str
    game_type: str
    draft_mode: str
    red_size: int
    blue_size: int
    players: list[DraftPlayer] = Field(default_factory=list)
    hero_pool: list[str] = Field(default_factory=list)
    sequence: list[DraftStep] = Field(default_factory=list)
    current_index: int = 0
    bans: dict[TeamColor, list[str]] = Field(default_factory=_empty_team_lists)
    picks: dict[TeamColor, list[str]] = Field(default_factory=_empty_team_lists)
    first_team: TeamColor | None = None
    game_id: str | None = None
    created_at: float
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_models.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/goa2/draft/__init__.py src/goa2/draft/models.py tests/draft/test_draft_models.py
git commit -m "feat(draft): draft state data models"
```

---

### Task 2: Draft mode abstraction & sequential ban/pick mode

**Files:**
- Create: `src/goa2/draft/modes.py`
- Test: `tests/draft/test_draft_modes.py`

**Interfaces:**
- Consumes: `DraftStep`, `DraftActionType` from `draft.models`; `TeamColor`.
- Produces: `DraftMode` (ABC) with `name: str`, `description: str`, `hero_pool(all_heroes: list[str]) -> list[str]`, `build_sequence(red_size: int, blue_size: int, first_team: TeamColor) -> list[DraftStep]`. `SequentialBanPickMode(bans_per_team: int = 1)`. `DRAFT_MODES: dict[str, DraftMode]`. `get_mode(name: str) -> DraftMode` (raises `KeyError`).

- [ ] **Step 1: Write the failing test**

```python
# tests/draft/test_draft_modes.py
from goa2.domain.models import TeamColor
from goa2.draft.models import DraftActionType
from goa2.draft.modes import DRAFT_MODES, get_mode, SequentialBanPickMode


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_modes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'goa2.draft.modes'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/goa2/draft/modes.py
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
            DraftStep(index=i, action=action, team=team)
            for i, (action, team) in enumerate(raw)
        ]


DRAFT_MODES: dict[str, DraftMode] = {
    SequentialBanPickMode().name: SequentialBanPickMode(),
}


def get_mode(name: str) -> DraftMode:
    return DRAFT_MODES[name]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_modes.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/goa2/draft/modes.py tests/draft/test_draft_modes.py
git commit -m "feat(draft): pluggable draft modes with sequential ban/pick"
```

---

### Task 3: Draft errors & pure transition service

**Files:**
- Create: `src/goa2/draft/errors.py`
- Create: `src/goa2/draft/service.py`
- Test: `tests/draft/test_draft_service.py`

**Interfaces:**
- Consumes: `DraftState`, `DraftPlayer`, `DraftStatus`, `DraftActionType` from `draft.models`; `get_mode` from `draft.modes`; `TeamColor`.
- Produces (in `draft.errors`): `DraftError(Exception)` with class attr `status_code: int = 400`; subclasses `DraftNotFoundError(404)`, `DraftFullError(409)`, `NotHostError(403)`, `NotActingCaptainError(403)`, `InvalidDraftPhaseError(409)`, `HeroUnavailableError(409)`, `HeroNotClaimableError(409)`, `InvalidTeamError(400)`, `PlayerNotFoundError(404)`.
- Produces (in `draft.service`):
  - `create_draft(draft_id, map_name, game_type, draft_mode, red_size, blue_size, host_name, now) -> DraftState` — host added as player `"p1"` (`is_host=True`).
  - `join(state, display_name) -> DraftPlayer`
  - `set_team(state, player_id, team: TeamColor) -> None`
  - `randomize_teams(state, rng) -> None`
  - `set_captain(state, player_id) -> None`
  - `start_draft(state, all_heroes, rng) -> None`
  - `apply_action(state, player_id, hero) -> None`
  - `claim_hero(state, player_id, hero) -> None`
  - `is_ready_to_create_game(state) -> bool`
  - `team_hero_lists(state) -> tuple[list[str], list[str]]`
  - `available_heroes(state) -> list[str]`
  - `get_player(state, player_id) -> DraftPlayer`

- [ ] **Step 1: Write the failing test**

```python
# tests/draft/test_draft_service.py
import random

import pytest

from goa2.domain.models import TeamColor
from goa2.draft.models import DraftStatus
from goa2.draft import service
from goa2.draft.errors import (
    DraftFullError, InvalidDraftPhaseError, NotActingCaptainError,
    HeroUnavailableError, HeroNotClaimableError, InvalidTeamError,
)

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
    st = service.create_draft(
        "d1", "m", "LONG", "sequential_ban_pick", 2, 2, "Alice", now=0.0
    )
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
    assert reds[0].is_captain  # first to join the team


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

    # Walk the resolved sequence using whichever captain the step belongs to.
    pool = iter(HEROES)
    for step in st.sequence:
        cap = red_cap if step.team is TeamColor.RED else blue_cap
        service.apply_action(st, cap, next(pool))
    assert st.status is DraftStatus.CLAIMING
    assert not service.is_ready_to_create_game(st)

    # Each player claims one of their team's drafted heroes.
    for team in (TeamColor.RED, TeamColor.BLUE):
        drafted = list(st.picks[team])
        members = [p for p in st.players if p.team is team]
        for player, hero in zip(members, drafted):
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
    cap = next(p.id for p in st.players
               if p.team is st.sequence[0].team and p.is_captain)
    service.apply_action(st, cap, "Arien")  # consume Arien (ban or pick)
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
    service.set_team(st, "p1", TeamColor.RED)  # teams not fully assigned
    with pytest.raises(InvalidDraftPhaseError):
        service.start_draft(st, HEROES, random.Random(0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'goa2.draft.errors'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/goa2/draft/errors.py
from __future__ import annotations


class DraftError(Exception):
    status_code: int = 400


class DraftNotFoundError(DraftError):
    status_code = 404


class PlayerNotFoundError(DraftError):
    status_code = 404


class DraftFullError(DraftError):
    status_code = 409


class NotHostError(DraftError):
    status_code = 403


class NotActingCaptainError(DraftError):
    status_code = 403


class InvalidDraftPhaseError(DraftError):
    status_code = 409


class HeroUnavailableError(DraftError):
    status_code = 409


class HeroNotClaimableError(DraftError):
    status_code = 409


class InvalidTeamError(DraftError):
    status_code = 400
```

```python
# src/goa2/draft/service.py
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
        # collapse extras to a single captain
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
        raise NotActingCaptainError(
            f"Only team {step.team.value}'s captain may act on this step"
        )
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/draft/test_draft_service.py -q`
Expected: PASS (all service tests pass)

- [ ] **Step 5: Commit**

```bash
git add src/goa2/draft/errors.py src/goa2/draft/service.py tests/draft/test_draft_service.py
git commit -m "feat(draft): pure draft transition service and typed errors"
```

---

### Task 4: In-memory DraftRegistry

**Files:**
- Create: `src/goa2/server/draft_registry.py`
- Test: `tests/server/test_draft_registry.py`

**Interfaces:**
- Consumes: `DraftState` from `draft.models`.
- Produces:
  - `ManagedDraft` dataclass: `draft_id: str`, `state: DraftState`, `player_tokens: dict[str, str]` (token→player_id), `player_to_token: dict[str, str]`, `host_token: str`, `spectator_token: str`, `lock: asyncio.Lock`, `player_game_tokens: dict[str, str]` (player_id→hero game token), `created_at: float`.
  - `DraftRegistry`: `create(state, now=None) -> ManagedDraft` (generates host token for `"p1"`, spectator token), `get(draft_id) -> ManagedDraft` (raises `DraftNotFoundError`), `add_player_token(draft_id, player_id) -> str`, `resolve_token(token) -> tuple[draft_id, player_id, is_spectator, is_host] | None`, `remove(draft_id)`, `__len__`.

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_draft_registry.py
import pytest

from goa2.draft import service
from goa2.draft.errors import DraftNotFoundError
from goa2.server.draft_registry import DraftRegistry


def _state():
    return service.create_draft(
        "d1", "m", "LONG", "sequential_ban_pick", 2, 2, "Alice", now=0.0
    )


def test_create_issues_host_and_spectator_tokens():
    reg = DraftRegistry()
    md = reg.create(_state())
    assert md.host_token and md.spectator_token
    assert md.player_tokens[md.host_token] == "p1"
    resolved = reg.resolve_token(md.host_token)
    assert resolved == (md.draft_id, "p1", False, True)


def test_add_player_token_and_resolve():
    reg = DraftRegistry()
    md = reg.create(_state())
    service.join(md.state, "Bob")  # creates p2
    tok = reg.add_player_token(md.draft_id, "p2")
    assert reg.resolve_token(tok) == (md.draft_id, "p2", False, False)


def test_spectator_token_resolves_readonly():
    reg = DraftRegistry()
    md = reg.create(_state())
    assert reg.resolve_token(md.spectator_token) == (md.draft_id, "", True, False)


def test_get_missing_raises():
    reg = DraftRegistry()
    with pytest.raises(DraftNotFoundError):
        reg.get("nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'goa2.server.draft_registry'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/goa2/server/draft_registry.py
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from goa2.draft.errors import DraftNotFoundError
from goa2.draft.models import DraftState


@dataclass
class ManagedDraft:
    draft_id: str
    state: DraftState
    host_token: str
    spectator_token: str
    player_tokens: dict[str, str] = field(default_factory=dict)
    player_to_token: dict[str, str] = field(default_factory=dict)
    player_game_tokens: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DraftRegistry:
    """In-memory store for draft lobbies. No disk persistence."""

    def __init__(self) -> None:
        self._drafts: dict[str, ManagedDraft] = {}

    def create(self, state: DraftState, now: float | None = None) -> ManagedDraft:
        host_token = uuid.uuid4().hex
        md = ManagedDraft(
            draft_id=state.draft_id,
            state=state,
            host_token=host_token,
            spectator_token=uuid.uuid4().hex,
            created_at=now if now is not None else time.time(),
        )
        # Host is always p1.
        md.player_tokens[host_token] = "p1"
        md.player_to_token["p1"] = host_token
        self._drafts[state.draft_id] = md
        return md

    def get(self, draft_id: str) -> ManagedDraft:
        md = self._drafts.get(draft_id)
        if md is None:
            raise DraftNotFoundError(f"Draft '{draft_id}' not found")
        return md

    def add_player_token(self, draft_id: str, player_id: str) -> str:
        md = self.get(draft_id)
        token = uuid.uuid4().hex
        md.player_tokens[token] = player_id
        md.player_to_token[player_id] = token
        return token

    def resolve_token(self, token: str) -> tuple[str, str, bool, bool] | None:
        for draft_id, md in self._drafts.items():
            if token in md.player_tokens:
                player_id = md.player_tokens[token]
                return (draft_id, player_id, False, token == md.host_token)
            if token == md.spectator_token:
                return (draft_id, "", True, False)
        return None

    def remove(self, draft_id: str) -> None:
        self._drafts.pop(draft_id, None)

    def __len__(self) -> int:
        return len(self._drafts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_registry.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/goa2/server/draft_registry.py tests/server/test_draft_registry.py
git commit -m "feat(draft): in-memory draft registry with tokens"
```

---

### Task 5: Server request/response models & DraftError exception handler

**Files:**
- Modify: `src/goa2/server/models.py` (append draft models)
- Modify: `src/goa2/server/app.py` (register `DraftError` handler + `DraftRegistry` on `app.state`, include router placeholder)
- Test: `tests/server/test_draft_models.py`

**Interfaces:**
- Consumes: nothing new beyond Pydantic.
- Produces (in `server/models.py`): `CreateDraftRequest`, `JoinDraftRequest`, `SetTeamRequest`, `SetCaptainRequest`, `DraftActionRequest`, `ClaimHeroRequest`, `CreateDraftResponse`, `JoinDraftResponse`, `DraftViewResponse`, `DraftModeInfo`.
- Produces (in `app.py`): `app.state.draft_registry: DraftRegistry`; `DraftError` mapped to its `status_code`.

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_draft_models.py
from goa2.server.models import (
    CreateDraftRequest, CreateDraftResponse, DraftViewResponse, DraftActionRequest,
)


def test_create_request_defaults():
    req = CreateDraftRequest(host_name="Alice", red_size=2, blue_size=2)
    assert req.map_name == "forgotten_island"
    assert req.game_type == "LONG"
    assert req.draft_mode == "sequential_ban_pick"
    assert req.cheats_enabled is False


def test_view_response_shape():
    resp = DraftViewResponse(draft={}, you=None)
    assert resp.draft == {} and resp.you is None and resp.game_token is None


def test_action_request():
    assert DraftActionRequest(hero="Arien").hero == "Arien"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'CreateDraftRequest'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/goa2/server/models.py`:

```python
# -- Draft requests --


class CreateDraftRequest(BaseModel):
    host_name: str
    red_size: int
    blue_size: int
    map_name: str = "forgotten_island"
    game_type: str = "LONG"
    draft_mode: str = "sequential_ban_pick"
    cheats_enabled: bool = False


class JoinDraftRequest(BaseModel):
    display_name: str


class SetTeamRequest(BaseModel):
    team: str  # "RED" | "BLUE"


class SetCaptainRequest(BaseModel):
    player_id: str


class DraftActionRequest(BaseModel):
    hero: str


class ClaimHeroRequest(BaseModel):
    hero: str


# -- Draft responses --


class DraftModeInfo(BaseModel):
    name: str
    description: str


class CreateDraftResponse(BaseModel):
    draft_id: str
    player_id: str
    player_token: str
    spectator_token: str


class JoinDraftResponse(BaseModel):
    draft_id: str
    player_id: str
    player_token: str


class DraftViewResponse(BaseModel):
    draft: dict[str, Any]
    you: dict[str, Any] | None = None
    game_id: str | None = None
    game_token: str | None = None
```

In `src/goa2/server/app.py`, add import near the other error imports:

```python
from goa2.draft.errors import DraftError
from goa2.server.draft_registry import DraftRegistry
```

Inside `lifespan`, after `app.state.registry = registry`, add:

```python
    app.state.draft_registry = DraftRegistry()
```

Inside `create_app`, after the existing exception handlers, add:

```python
    @app.exception_handler(DraftError)
    async def _draft_error(request: Request, exc: DraftError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_models.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/goa2/server/models.py src/goa2/server/app.py tests/server/test_draft_models.py
git commit -m "feat(draft): server models and DraftError handler wiring"
```

---

### Task 6: Draft REST router & game-creation handoff

**Files:**
- Create: `src/goa2/server/routes_draft.py`
- Modify: `src/goa2/server/app.py` (include `draft_router`)
- Test: `tests/server/test_draft_rest.py`

**Interfaces:**
- Consumes: `DraftRegistry`/`ManagedDraft` (task 4), draft `service` (task 3), `get_mode`/`DRAFT_MODES` (task 2), draft request/response models (task 5), existing `GameRegistry`, `GameSetup.create_game`, `GameSession`.
- Produces: `router = APIRouter(prefix="/drafts", tags=["drafts"])` with endpoints from the spec. A `_draft_view(md, player_id, is_spectator)` helper returns a `DraftViewResponse`. A `_maybe_create_game(request, md)` helper creates the game when `service.is_ready_to_create_game` is true.

**Auth note:** Draft endpoints use their own bearer resolution against `app.state.draft_registry` (the existing `PlayerDep` resolves against the *game* registry and must not be reused here). Implement a local dependency.

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_draft_rest.py
import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _bears(client):
    """Drive a full 2v2 draft to a created game; return (game_id, player_game_tokens)."""
    r = client.post("/drafts", json={"host_name": "Alice", "red_size": 2, "blue_size": 2})
    assert r.status_code == 201
    d = r.json()
    draft_id, host_tok = d["draft_id"], d["player_token"]

    toks = {"p1": host_tok}
    for name in ("Bob", "Carol", "Dave"):
        jr = client.post(f"/drafts/{draft_id}/join", json={"display_name": name})
        assert jr.status_code == 200
        toks[jr.json()["player_id"]] = jr.json()["player_token"]

    for pid, team in (("p1", "RED"), ("p2", "RED"), ("p3", "BLUE"), ("p4", "BLUE")):
        assert client.post(f"/drafts/{draft_id}/team", json={"team": team},
                           headers=_auth(toks[pid])).status_code == 200

    assert client.post(f"/drafts/{draft_id}/start", headers=_auth(host_tok)).status_code == 200

    # Walk the sequence with the acting captain each step.
    view = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()["draft"]
    cap = {p["team"]: p["id"] for p in view["players"] if p["is_captain"]}
    heroes = client.get("/heroes").json()
    hi = iter(heroes)
    for step in view["sequence"]:
        pid = cap[step["team"]]
        rr = client.post(f"/drafts/{draft_id}/action", json={"hero": next(hi)},
                         headers=_auth(toks[pid]))
        assert rr.status_code == 200

    # Claim phase.
    view = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()["draft"]
    for team in ("RED", "BLUE"):
        members = [p for p in view["players"] if p["team"] == team]
        drafted = list(view["picks"][team])
        for player, hero in zip(members, drafted):
            cr = client.post(f"/drafts/{draft_id}/claim", json={"hero": hero},
                             headers=_auth(toks[player["id"]]))
            assert cr.status_code == 200

    final = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()
    return draft_id, toks, final


def test_full_draft_creates_playable_game(client):
    draft_id, toks, final = _bears(client)
    assert final["game_id"]
    assert final["draft"]["status"] == "COMPLETE"
    # Host's game token should work against the existing /games endpoint.
    assert final["game_token"]
    gv = client.get(f"/games/{final['game_id']}", headers=_auth(final["game_token"]))
    assert gv.status_code == 200


def test_modes_endpoint(client):
    r = client.get("/drafts/modes")
    assert r.status_code == 200
    assert any(m["name"] == "sequential_ban_pick" for m in r.json())


def test_non_host_cannot_start(client):
    r = client.post("/drafts", json={"host_name": "Alice", "red_size": 2, "blue_size": 2})
    d = r.json()
    jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": "Bob"})
    bob = jr.json()["player_token"]
    rr = client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(bob))
    assert rr.status_code == 403


def test_randomize_then_start(client):
    r = client.post("/drafts", json={"host_name": "A", "red_size": 2, "blue_size": 2})
    d = r.json()
    host = d["player_token"]
    for name in ("B", "C", "D"):
        client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": name})
    assert client.post(f"/drafts/{d['draft_id']}/randomize-teams",
                       headers=_auth(host)).status_code == 200
    assert client.post(f"/drafts/{d['draft_id']}/start",
                       headers=_auth(host)).status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_rest.py -q`
Expected: FAIL — 404s / `create_app` has no `/drafts` routes.

- [ ] **Step 3: Write minimal implementation**

```python
# src/goa2/server/routes_draft.py
"""REST endpoints under /drafts (pre-game draft lobby)."""

from __future__ import annotations

import os
import random
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import TeamColor
from goa2.draft import service
from goa2.draft.errors import InvalidTeamError, NotHostError
from goa2.draft.modes import DRAFT_MODES
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.draft_registry import DraftRegistry, ManagedDraft
from goa2.server.models import (
    ClaimHeroRequest,
    CreateDraftRequest,
    CreateDraftResponse,
    DraftActionRequest,
    DraftModeInfo,
    DraftViewResponse,
    JoinDraftRequest,
    JoinDraftResponse,
    SetCaptainRequest,
    SetTeamRequest,
)

router = APIRouter(prefix="/drafts", tags=["drafts"])


def get_draft_registry(request: Request) -> DraftRegistry:
    return request.app.state.draft_registry


DraftRegistryDep = Annotated[DraftRegistry, Depends(get_draft_registry)]


@dataclass
class DraftContext:
    draft_id: str
    player_id: str
    is_spectator: bool
    is_host: bool


def get_draft_player(request: Request, registry: DraftRegistryDep) -> DraftContext:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[len("Bearer ") :]
    resolved = registry.resolve_token(token)
    if resolved is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    draft_id, player_id, is_spectator, is_host = resolved
    path_draft_id = request.path_params.get("draft_id")
    if path_draft_id and path_draft_id != draft_id:
        raise HTTPException(status_code=403, detail="Token does not match this draft")
    return DraftContext(draft_id, player_id, is_spectator, is_host)


DraftPlayerDep = Annotated[DraftContext, Depends(get_draft_player)]


def _map_path(map_name: str) -> str:
    base = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    path = os.path.normpath(os.path.join(base, f"{map_name}.json"))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Map '{map_name}' not found")
    return path


def _draft_view(md: ManagedDraft, player_id: str, is_spectator: bool) -> DraftViewResponse:
    you = None
    if not is_spectator:
        you = next(
            (p.model_dump(mode="json") for p in md.state.players if p.id == player_id),
            None,
        )
    return DraftViewResponse(
        draft=md.state.model_dump(mode="json"),
        you=you,
        game_id=md.state.game_id,
        game_token=md.player_game_tokens.get(player_id),
    )


def _maybe_create_game(request: Request, md: ManagedDraft) -> None:
    if not service.is_ready_to_create_game(md.state):
        return
    state = md.state
    red_heroes, blue_heroes = service.team_hero_lists(state)
    game_seed_id = uuid.uuid4().hex
    game_id = game_seed_id[:12]
    seed = int(game_seed_id, 16)
    game_state = GameSetup.create_game(
        _map_path(state.map_name),
        red_heroes,
        blue_heroes,
        False,
        state.game_type,
        seed=seed,
    )
    session = GameSession(game_state)
    hero_ids = [h.id for team in game_state.teams.values() for h in team.heroes]
    game_registry = request.app.state.registry
    game = game_registry.create_game(session, hero_ids, game_id=game_id)
    if game.replay_recorder:
        game.replay_recorder.record_setup(
            map_name=state.map_name,
            red_heroes=red_heroes,
            blue_heroes=blue_heroes,
            game_type=state.game_type,
            cheats=False,
            seed=seed,
        )
    name_to_id = {h.name: h.id for team in game_state.teams.values() for h in team.heroes}
    for player in state.players:
        if player.claimed_hero:
            hero_id = name_to_id[player.claimed_hero]
            md.player_game_tokens[player.id] = game.hero_to_token[hero_id]
    state.game_id = game.game_id
    state.status = service.DraftStatus.COMPLETE


# ---- Endpoints ----


@router.get("/modes", response_model=list[DraftModeInfo])
async def list_modes() -> list[DraftModeInfo]:
    return [DraftModeInfo(name=m.name, description=m.description) for m in DRAFT_MODES.values()]


@router.post("", response_model=CreateDraftResponse, status_code=201)
async def create_draft(body: CreateDraftRequest, registry: DraftRegistryDep) -> CreateDraftResponse:
    if body.game_type not in ("QUICK", "LONG"):
        raise HTTPException(status_code=400, detail="game_type must be QUICK or LONG")
    if body.draft_mode not in DRAFT_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown draft_mode '{body.draft_mode}'")
    # Validate the resulting player count against the engine's brackets.
    GameSetup.get_game_config(body.game_type, body.red_size + body.blue_size)
    _map_path(body.map_name)
    draft_id = uuid.uuid4().hex[:12]
    import time

    state = service.create_draft(
        draft_id, body.map_name, body.game_type, body.draft_mode,
        body.red_size, body.blue_size, body.host_name, now=time.time(),
    )
    md = registry.create(state)
    return CreateDraftResponse(
        draft_id=draft_id,
        player_id="p1",
        player_token=md.host_token,
        spectator_token=md.spectator_token,
    )


@router.post("/{draft_id}/join", response_model=JoinDraftResponse)
async def join_draft(
    draft_id: str, body: JoinDraftRequest, registry: DraftRegistryDep
) -> JoinDraftResponse:
    md = registry.get(draft_id)
    async with md.lock:
        player = service.join(md.state, body.display_name)
        token = registry.add_player_token(draft_id, player.id)
    return JoinDraftResponse(draft_id=draft_id, player_id=player.id, player_token=token)


@router.get("/{draft_id}", response_model=DraftViewResponse)
async def get_draft(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    md = registry.get(draft_id)
    return _draft_view(md, player.player_id, player.is_spectator)


def _reject_spectator(player: DraftContext) -> None:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot modify the draft")


@router.post("/{draft_id}/team", response_model=DraftViewResponse)
async def set_team(
    draft_id: str, body: SetTeamRequest, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    try:
        team = TeamColor(body.team)
    except ValueError as exc:
        raise InvalidTeamError(f"Invalid team '{body.team}'") from exc
    async with md.lock:
        service.set_team(md.state, player.player_id, team)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/randomize-teams", response_model=DraftViewResponse)
async def randomize_teams(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may randomize teams")
    md = registry.get(draft_id)
    async with md.lock:
        service.randomize_teams(md.state, random.Random())
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/captain", response_model=DraftViewResponse)
async def set_captain(
    draft_id: str, body: SetCaptainRequest, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may set captains")
    md = registry.get(draft_id)
    async with md.lock:
        service.set_captain(md.state, body.player_id)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/start", response_model=DraftViewResponse)
async def start_draft(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may start the draft")
    md = registry.get(draft_id)
    async with md.lock:
        service.start_draft(md.state, HeroRegistry.list_heroes(), random.Random())
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/action", response_model=DraftViewResponse)
async def draft_action(
    draft_id: str,
    body: DraftActionRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    async with md.lock:
        service.apply_action(md.state, player.player_id, body.hero)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/claim", response_model=DraftViewResponse)
async def claim_hero(
    draft_id: str,
    body: ClaimHeroRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
    request: Request,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    async with md.lock:
        service.claim_hero(md.state, player.player_id, body.hero)
        _maybe_create_game(request, md)
    return _draft_view(md, player.player_id, player.is_spectator)
```

Note: add `DraftStatus` access used by `_maybe_create_game` — at top of `service.py` it is already imported; expose it via `service.DraftStatus`. Add this line to `src/goa2/draft/service.py` imports so `service.DraftStatus` resolves (it already imports `DraftStatus` from `draft.models`, so `service.DraftStatus` works without change).

In `src/goa2/server/app.py`, add the import:

```python
from goa2.server.routes_draft import router as draft_router
```

and inside `create_app`, after `app.include_router(games_router)`:

```python
    app.include_router(draft_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src uv run pytest tests/server/test_draft_rest.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run full draft + server suites**

Run: `PYTHONPATH=src uv run pytest tests/draft/ tests/server/ -q`
Expected: PASS (no regressions)

- [ ] **Step 6: Commit**

```bash
git add src/goa2/server/routes_draft.py src/goa2/server/app.py tests/server/test_draft_rest.py
git commit -m "feat(draft): REST draft lobby endpoints with game handoff"
```

---

### Task 7: Client integration guide docs & full-suite gate

**Files:**
- Modify: `docs/CLIENT_INTEGRATION_GUIDE.md` (add a "Character Draft Lobby" section)

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the documentation section**

Append a new section to `docs/CLIENT_INTEGRATION_GUIDE.md` describing:
- The lifecycle `LOBBY → DRAFTING → CLAIMING → COMPLETE`.
- Each endpoint (method, path, auth, request body, response), copied from the spec's endpoint table, plus the `DraftViewResponse` shape (`draft`, `you`, `game_id`, `game_token`).
- The token model: host token (admin), per-player tokens from `/join`, spectator token; how `game_token`/`game_id` appear on the player-scoped view once `COMPLETE`, and that clients then switch to the existing `/games/{id}` flow with that token.
- That draft state is in-memory only (lost on restart) and updates are obtained by polling `GET /drafts/{id}` (WebSocket is a planned follow-on).

Write the section to match the existing guide's formatting (headers, code-fenced JSON examples). Use real example payloads consistent with the request/response models in `server/models.py`.

- [ ] **Step 2: Verify the guide renders / no broken references**

Run: `PYTHONPATH=src uv run pytest tests/draft/ tests/server/ -q`
Expected: PASS (docs change does not affect tests; this is the regression gate).

- [ ] **Step 3: Lint, format, type-check**

Run: `uv run ruff check src/ && uv run black --check src/ && uv run mypy src/`
Expected: all pass.

- [ ] **Step 4: Full test suite**

Run: `PYTHONPATH=src uv run pytest tests/ -q`
Expected: PASS (all prior tests + new draft tests).

- [ ] **Step 5: Commit**

```bash
git add docs/CLIENT_INTEGRATION_GUIDE.md
git commit -m "docs(draft): document character draft lobby API"
```

---

## Self-Review

**Spec coverage:**
- Pluggable modes → Task 2 (`DraftMode` ABC + registry). ✓
- Sequential ban/pick pilot → Task 2 (`SequentialBanPickMode`). ✓
- Captain-driven bans/picks → Task 3 (`apply_action` captain check). ✓
- Players claim after draft → Task 3 (`claim_hero`, CLAIMING phase). ✓
- Shared link + display name join → Task 4/6 (`join`, per-player token). ✓
- Self-select team + randomize button → Task 3/6 (`set_team`, `randomize_teams`). ✓
- Host can reassign captain → Task 3/6 (`set_captain`, host-only endpoint). ✓
- In-memory only → Task 4 (no save_dir). ✓
- Polling, WS follow-on → Task 6 (GET view) / out of scope. ✓
- Game handoff to existing flow → Task 6 (`_maybe_create_game`). ✓
- Client guide update → Task 7. ✓

**Placeholder scan:** Task 5 Step 1's `test_view_response_shape` contains a deliberately odd literal — replace it with the clean version below when implementing:

```python
def test_view_response_shape():
    resp = DraftViewResponse(draft={}, you=None)
    assert resp.draft == {} and resp.you is None and resp.game_token is None
```

**Type consistency:** `resolve_token` returns a 4-tuple `(draft_id, player_id, is_spectator, is_host)` in Task 4 and is unpacked identically in Task 6. `team_hero_lists` / `is_ready_to_create_game` / `available_heroes` signatures match between Task 3 definition and Task 6 usage. `DraftViewResponse(draft, you, game_id, game_token)` consistent between Task 5 and Task 6. ✓
