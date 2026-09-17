"""Optional opening deployment edits, while a hero has no committed R1T1 card.

These are setup corrections, not movement effects. Live play and replay share
apply_position; consent requests are persisted UI state, not game decisions.
"""

from __future__ import annotations

from uuid import uuid4

from goa2.domain.hex import Hex
from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.models.spawn import SpawnType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID


def eligible(state: GameState, hero_id: str) -> bool:
    return (
        state.phase == GamePhase.PLANNING
        and state.round == 1
        and state.turn == 1
        and state.get_hero(HeroID(hero_id)) is not None
        and hero_id not in state.pending_inputs
        and len(state.get_piece_ids(hero_id)) == 1
    )


def clear_requests(state: GameState, hero_id: str) -> None:
    state.starting_position_requests = {
        key: req
        for key, req in state.starting_position_requests.items()
        if hero_id not in (req["from"], req["to"])
    }


def _team(state: GameState, hero_id: str) -> TeamColor:
    hero = state.get_hero(HeroID(hero_id))
    if hero is None or hero.team is None:
        raise ValueError(f"Hero {hero_id} has no team")
    return hero.team


def _position(state: GameState, piece: BoardEntityID) -> Hex:
    position = state.get_position(piece)
    if position is None:
        raise ValueError(f"{piece} is not on the board")
    return position


def _piece(state: GameState, hero_id: str) -> BoardEntityID:
    if not eligible(state, hero_id):
        raise ValueError(
            "Starting positions can only change during R1T1 planning with no committed card"
        )
    return BoardEntityID(state.get_piece_ids(hero_id)[0])


def _legal_arrangement(state: GameState, hero_id: str, changes: dict[BoardEntityID, Hex]) -> bool:
    team = _team(state, hero_id)
    spawns = {
        sp.location
        for sp in state.board.spawn_points
        if sp.type == SpawnType.HERO and sp.team == team
    }
    throne_zones = {
        lane[0] if team == TeamColor.RED else lane[-1]
        for lane in state.board.lanes.values()
        if lane
    }
    occupied = {loc for entity, loc in state.entity_locations.items() if entity not in changes}
    if len(set(changes.values())) != len(changes):
        return False
    for dest in changes.values():
        tile = state.board.tiles.get(dest)
        if tile is None or tile.is_terrain or dest in occupied:
            return False
    occupied.update(changes.values())
    for dest in changes.values():
        if dest in spawns:
            continue
        if (
            spawns - occupied
            or state.board.tiles[dest].zone_id not in throne_zones
            or not any(dest in spawn.neighbors() for spawn in spawns)
        ):
            return False
    # Moving away from a spawn must not leave an existing overflow hero behind
    # while that spawn is empty.
    if spawns - occupied:
        for teammate in state.teams[team].heroes:
            for piece in state.get_piece_ids(str(teammate.id)):
                pos = changes.get(BoardEntityID(piece), state.get_position(piece))
                if pos not in spawns:
                    return False
    return True


def destinations(state: GameState, hero_id: str) -> list[Hex]:
    if not eligible(state, hero_id):
        return []
    piece = _piece(state, hero_id)
    origin = state.get_position(piece)
    team = _team(state, hero_id)
    candidates = set()
    for spawn in state.board.spawn_points:
        if spawn.type == SpawnType.HERO and spawn.team == team:
            candidates.add(spawn.location)
            candidates.update(spawn.location.neighbors())
    return [
        h
        for h in sorted(candidates, key=lambda h: (h.q, h.r, h.s))
        if h != origin and _legal_arrangement(state, hero_id, {piece: h})
    ]


def _swap_changes(state: GameState, hero_id: str, target: str) -> dict[BoardEntityID, Hex]:
    piece, other = _piece(state, hero_id), _piece(state, target)
    if hero_id == target or _team(state, hero_id) != _team(state, target):
        raise ValueError("Starting positions may only be swapped with a teammate")
    changes = {piece: _position(state, other), other: _position(state, piece)}
    if not _legal_arrangement(state, hero_id, changes):
        raise ValueError("Invalid starting-position swap")
    return changes


def apply_position(
    state: GameState, hero_id: str, destination: Hex | None = None, swap_with: str | None = None
) -> None:
    """Apply an authorized, atomic change; also used by trusted replay records."""
    piece = _piece(state, hero_id)
    if swap_with is not None:
        changes = _swap_changes(state, hero_id, swap_with)
    else:
        if destination is None or destination == state.get_position(piece):
            raise ValueError("Choose a different starting space")
        changes = {piece: destination}
        if not _legal_arrangement(state, hero_id, changes):
            raise ValueError(
                "Invalid starting space: use your team's spawn or legal throne overflow"
            )
    # All validation happens before either piece is lifted.
    for board_id in changes:
        state.remove_entity(board_id)
    for board_id, dest in changes.items():
        state.place_entity(board_id, dest)
    clear_requests(state, hero_id)
    if swap_with is not None:
        clear_requests(state, swap_with)
    from goa2.engine.phases import record_position_snapshot

    record_position_snapshot(state)


def request_swap(state: GameState, hero_id: str, target: str) -> str:
    _swap_changes(state, hero_id, target)
    # One outstanding request per requester. Unique IDs prevent stale acceptance.
    clear_requests(state, hero_id)
    request_id = uuid4().hex
    state.starting_position_requests[request_id] = {"from": hero_id, "to": target}
    return request_id


def respond_swap(state: GameState, hero_id: str, request_id: str, accept: bool) -> str | None:
    req = state.starting_position_requests.get(request_id)
    if req is None or req["to"] != hero_id:
        raise ValueError("Starting-position request is no longer available")
    if accept:
        apply_position(state, req["from"], swap_with=hero_id)
        return req["from"]
    del state.starting_position_requests[request_id]
    return None


def position_view(state: GameState, hero_id: str | None) -> dict | None:
    if hero_id is None or not eligible(state, hero_id):
        return None
    targets = []
    for teammate in state.teams[_team(state, hero_id)].heroes:
        try:
            _swap_changes(state, hero_id, str(teammate.id))
        except ValueError:
            continue
        targets.append(str(teammate.id))
    return {
        "destinations": [h.model_dump() for h in destinations(state, hero_id)],
        "swap_targets": targets,
        "requests": [
            {"id": key, **req}
            for key, req in state.starting_position_requests.items()
            if hero_id in (req["from"], req["to"])
        ],
    }
