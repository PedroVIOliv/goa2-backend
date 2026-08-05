"""Consensus-override op registry — the single mutation path for overrides.

Every override (live or replayed) goes through ``apply_override_decision``:
validate args -> snapshot -> apply -> revalidate the whole GameState (which
rebuilds the occupancy cache and re-unifies card/token references) -> on any
failure restore the snapshot and reject. Nothing else may mutate state for an
override; replay parity depends on this being the one code path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from goa2.domain.hex import Hex
from goa2.domain.models import GamePhase
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.session import GameSession, SessionResult


class OverrideRejectedError(Exception):
    """An override op could not be applied. ``code`` is machine-readable."""

    def __init__(self, message: str, *, code: str = "invalid_op") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class HexArg(BaseModel):
    q: int
    r: int
    s: int

    def to_hex(self) -> Hex:
        return Hex(q=self.q, r=self.r, s=self.s)


@dataclass(frozen=True)
class OverrideOp:
    name: str
    family: Literal["patch", "unstick"]
    label: str
    description: str
    args_model: type[BaseModel]
    apply: Callable[[GameSession, Any], None]
    summary_template: str  # .format(**args_dict)


OVERRIDE_OPS: dict[str, OverrideOp] = {}


def _register(op: OverrideOp) -> None:
    if op.name in OVERRIDE_OPS:
        raise ValueError(f"Duplicate override op {op.name!r}")
    OVERRIDE_OPS[op.name] = op


def get_op(name: str) -> OverrideOp:
    op = OVERRIDE_OPS.get(name)
    if op is None:
        raise OverrideRejectedError(f"Unknown override op {name!r}", code="unknown_op")
    return op


def summarize_op(op_name: str, args: dict[str, Any]) -> str:
    op = get_op(op_name)
    try:
        return op.summary_template.format(**args)
    except (KeyError, IndexError):
        return f"{op.label}: {args}"


def apply_override_decision(
    session: GameSession, op_name: str, args: dict[str, Any]
) -> SessionResult | None:
    """Validate, apply, and re-derive. The one code path for live + replay.

    Returns the SessionResult of the post-apply re-derivation (a fresh input
    request if a step was pending), or None during PLANNING where advance()
    is not allowed and clients rely on the broadcast view.
    """
    op = get_op(op_name)
    try:
        parsed = op.args_model.model_validate(args)
    except Exception as exc:  # pydantic.ValidationError
        raise OverrideRejectedError(str(exc), code="invalid_args") from exc

    baseline = session.state.model_dump(mode="json")
    try:
        op.apply(session, parsed)
        # Full revalidation: rebuild_occupancy_cache + unify_card_references +
        # unify_token_references run as model validators, so an op that broke
        # an invariant raises here and the whole override rolls back.
        session.state = GameState.model_validate(session.state.model_dump(mode="json"))
    except OverrideRejectedError:
        session.state = GameState.model_validate(baseline)
        raise
    except Exception as exc:
        session.state = GameState.model_validate(baseline)
        raise OverrideRejectedError(str(exc), code="invalid_result") from exc

    # Bump the pending request id so a stale in-flight answer (submitted
    # against the pre-patch board) is rejected by the normal request-id
    # mismatch check. Deliberate departure from the persistence convention
    # of preserving ids across re-derivation.
    if session.state.execution_stack:
        top = session.state.execution_stack[-1]
        if top.pending_request_id is not None:
            top.pending_request_id = None

    if session.state.phase == GamePhase.PLANNING:
        return None
    # Re-derive: re-runs the pending step's resolve() so filters and option
    # lists are recomputed against the patched board.
    return session.advance(None)


# ---------------------------------------------------------------------------
# Board patch ops
# ---------------------------------------------------------------------------


def _resolve_board_entity_id(state: GameState, entity_id: str) -> BoardEntityID:
    """Map an entity arg to a concrete on-board id, honoring multi-piece rules."""
    if state._multi_piece_hero(entity_id) is not None:
        pieces = state.get_piece_ids(entity_id)
        if len(pieces) == 1:
            return BoardEntityID(pieces[0])
        raise OverrideRejectedError(
            f"{entity_id} is a multi-piece hero; specify one of its piece ids "
            f"({pieces or 'no pieces on board'})",
            code="ambiguous_entity",
        )
    return BoardEntityID(str(entity_id))


class MoveEntityArgs(BaseModel):
    entity_id: str
    hex: HexArg


def _apply_move_entity(session: GameSession, args: MoveEntityArgs) -> None:
    state = session.state
    board_id = _resolve_board_entity_id(state, args.entity_id)
    if state.get_position(str(board_id)) is None:
        raise OverrideRejectedError(
            f"{args.entity_id} is not on the board (use place_entity)", code="not_on_board"
        )
    state.place_entity(board_id, args.hex.to_hex())  # raises on occupied/off-map


_register(
    OverrideOp(
        name="move_entity",
        family="patch",
        label="Move entity",
        description="Move a unit, hero piece, or token to a hex (fixes a refused legal move).",
        args_model=MoveEntityArgs,
        apply=_apply_move_entity,
        summary_template="Move {entity_id} to {hex}",
    )
)


class RemoveEntityArgs(BaseModel):
    entity_id: str


def _apply_remove_entity(session: GameSession, args: RemoveEntityArgs) -> None:
    state = session.state
    board_id = _resolve_board_entity_id(state, args.entity_id)
    if BoardEntityID(str(board_id)) not in state.entity_locations:
        raise OverrideRejectedError(f"{args.entity_id} is not on the board", code="not_on_board")
    state.remove_entity(board_id)


_register(
    OverrideOp(
        name="remove_entity",
        family="patch",
        label="Remove entity from board",
        description="Remove a unit that should have been defeated.",
        args_model=RemoveEntityArgs,
        apply=_apply_remove_entity,
        summary_template="Remove {entity_id} from the board",
    )
)


class PlaceEntityArgs(BaseModel):
    entity_id: str
    hex: HexArg


def _apply_place_entity(session: GameSession, args: PlaceEntityArgs) -> None:
    state = session.state
    if (
        state.get_entity(BoardEntityID(args.entity_id)) is None
        and state.get_hero(HeroID(args.entity_id)) is None
    ):
        raise OverrideRejectedError(f"Unknown entity {args.entity_id!r}", code="unknown_entity")
    board_id = _resolve_board_entity_id(state, args.entity_id)
    state.place_entity(board_id, args.hex.to_hex())


_register(
    OverrideOp(
        name="place_entity",
        family="patch",
        label="Place entity on board",
        description="Put a wrongly defeated unit back, or fix a bad respawn hex.",
        args_model=PlaceEntityArgs,
        apply=_apply_place_entity,
        summary_template="Place {entity_id} at {hex}",
    )
)
