"""Steps for multi-piece heroes (Razzle): acting-piece choice, spawn, removal."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex
from goa2.domain.input import SKIP, InputOption, InputRequestType, create_input_request
from goa2.domain.models import StepType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine.steps.base import GameStep, StepResult
from goa2.engine.topology import are_connected, get_topology_service, topology_distance

logger = logging.getLogger(__name__)


class ChooseActingPieceStep(GameStep):
    """Bind which piece of a multi-piece hero performs the current action."""

    type: StepType = StepType.CHOOSE_ACTING_PIECE
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece:
            return StepResult(is_finished=True)

        pieces = state.get_piece_ids(self.hero_id)
        if not pieces:
            return StepResult(is_finished=True)

        if len(pieces) == 1:
            state.acting_piece_id = BoardEntityID(pieces[0])
            logger.debug("   [PIECE] Auto-bound acting piece %s", pieces[0])
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection in pieces:
                state.acting_piece_id = BoardEntityID(str(selection))
                logger.debug("   [PIECE] Bound acting piece %s", selection)
                return StepResult(is_finished=True)
            raise ValueError(f"Invalid acting piece selection: {selection}")

        options = []
        for pid in pieces:
            loc = state.entity_locations.get(BoardEntityID(pid))
            options.append(
                InputOption(
                    id=pid,
                    text=f"{hero.name} at ({loc.q}, {loc.r}, {loc.s})" if loc else pid,
                )
            )

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=self.hero_id,
                prompt="Choose which of you performs this action.",
                options=options,
            ),
        )


class SetActingPieceStep(GameStep):
    """Bind a specific already-selected piece as the acting piece."""

    type: StepType = StepType.SET_ACTING_PIECE
    hero_id: str
    piece_id: str | None = None
    piece_key: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        piece_id = self.piece_id
        if piece_id is None and self.piece_key:
            piece_id = context.get(self.piece_key)
        if not piece_id:
            return StepResult(is_finished=True)

        pieces = state.get_piece_ids(self.hero_id)
        if str(piece_id) not in pieces:
            logger.debug("   [PIECE] Invalid acting-piece binding: %s", piece_id)
            return StepResult(is_finished=True, abort_action=self.is_mandatory)

        state.acting_piece_id = BoardEntityID(str(piece_id))
        logger.debug("   [PIECE] Re-bound acting piece %s", piece_id)
        return StepResult(is_finished=True)


class SpawnHeroPieceStep(GameStep):
    """Spawn up to max_count pieces from supply into empty hexes in radius."""

    type: StepType = StepType.SPAWN_HERO_PIECE
    hero_id: str
    max_count: int = 1
    radius: int = 1
    origin_key: str | None = None
    is_mandatory: bool = False

    def _origin_hex(self, state: GameState, context: dict[str, Any]) -> Hex | None:
        if self.origin_key:
            origin_id = context.get(self.origin_key)
            if origin_id:
                return state.get_position(str(origin_id))
        return state.get_position(self.hero_id)

    def _valid_hexes(self, state: GameState, context: dict[str, Any]) -> list[Hex]:
        origin = self._origin_hex(state, context)
        if origin is None:
            return []

        valid: list[Hex] = []
        actor_id = str(state.current_actor_id) if state.current_actor_id else self.hero_id
        for candidate in state.board.tiles:
            if candidate == origin:
                continue
            if topology_distance(origin, candidate, state) > self.radius:
                continue
            if state.validator.is_obstacle_for_actor(state, candidate, actor_id, context):
                continue
            valid.append(candidate)
        return valid

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.hero_pieces import pieces_in_supply

        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece or self.max_count <= 0:
            return StepResult(is_finished=True)

        supply = pieces_in_supply(state, hero)
        if not supply:
            return StepResult(is_finished=True)

        valid_hexes = self._valid_hexes(state, context)
        if not valid_hexes:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == SKIP:
                return StepResult(is_finished=True)

            if isinstance(selection, dict):
                target = Hex(**selection)
                if target not in valid_hexes:
                    raise ValueError(f"Invalid spawn hex: {selection}")

                new_piece = supply[0]
                state.place_entity(BoardEntityID(new_piece), target)
                return StepResult(
                    is_finished=True,
                    events=[
                        GameEvent(
                            event_type=GameEventType.UNIT_PLACED,
                            actor_id=self.hero_id,
                            target_id=new_piece,
                            to_hex=_hex_dict(target),
                            metadata={"owner_hero_id": self.hero_id},
                        )
                    ],
                    new_steps=[
                        SpawnHeroPieceStep(
                            hero_id=self.hero_id,
                            max_count=self.max_count - 1,
                            radius=self.radius,
                            origin_key=self.origin_key,
                        )
                    ],
                )

            raise ValueError(f"Unexpected spawn selection: {selection}")

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=self.hero_id,
                prompt=f"Spawn another {hero.name}? ({len(supply)} in supply)",
                options=valid_hexes,
                can_skip=True,
            ),
        )


@dataclass(frozen=True)
class _PushPreview:
    target_dest: Hex
    moved_distance: int
    direction_idx: int


class RazzleMirroredPushStep(GameStep):
    """Push a nearby unit, then move Razzle's acting piece the actual distance back.

    The chosen push distance is an intent. Obstacles, board edge, and topology
    can stop the pushed unit early; the acting piece must be able to move exactly
    that actual distance in the opposite direction for the distance choice to be
    legal.
    """

    type: StepType = StepType.RAZZLE_MIRRORED_PUSH
    hero_id: str
    max_distance: int
    selected_target_id: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.movement import MoveUnitStep, PushUnitStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

        actor_piece = state.resolve_board_actor(self.hero_id)
        actor_hex = state.get_position(actor_piece)
        if actor_hex is None:
            return StepResult(is_finished=True, abort_action=self.is_mandatory)

        if self.selected_target_id is None:
            targets = self._valid_targets(state, context, actor_piece, actor_hex)
            if not targets:
                return StepResult(is_finished=True, abort_action=self.is_mandatory)

            if self.pending_input:
                selection = str(self.pending_input.get("selection"))
                self.pending_input = None
                if selection in targets:
                    self.selected_target_id = selection
                else:
                    return self._target_request(targets)
            else:
                return self._target_request(targets)

        target_id = self.selected_target_id
        if target_id is None:
            return StepResult(is_finished=True, abort_action=self.is_mandatory)

        legal = self._legal_distances(state, context, actor_piece, actor_hex, target_id)
        if not legal:
            return StepResult(is_finished=True, abort_action=self.is_mandatory)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            self.pending_input = None
            try:
                distance = int(selection)
            except (TypeError, ValueError):
                return self._distance_request(legal)

            if distance in legal:
                preview, mirror_dest = legal[distance]
                steps: list[GameStep] = []
                if distance > 0:
                    steps.append(PushUnitStep(target_id=target_id, distance=distance))
                if preview.moved_distance > 0 and mirror_dest is not None:
                    context["razzle_mirror_dest"] = mirror_dest
                    steps.append(
                        MoveUnitStep(
                            unit_id=actor_piece,
                            destination_key="razzle_mirror_dest",
                            range_val=preview.moved_distance,
                            is_movement_action=False,
                        )
                    )
                return StepResult(is_finished=True, new_steps=steps)

        return self._distance_request(legal)

    def _target_request(self, targets: list[str]) -> StepResult:
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=self.hero_id,
                prompt="Select an adjacent unit to push",
                options=targets,
            ),
        )

    def _distance_request(self, legal: dict[int, tuple[_PushPreview, Hex | None]]) -> StepResult:
        options = [
            InputOption(
                id=str(distance),
                text=str(distance),
                metadata={"actual_moved": preview.moved_distance},
            )
            for distance, (preview, _) in sorted(legal.items())
        ]
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_NUMBER,
                player_id=self.hero_id,
                prompt="Choose push distance",
                options=options,
            ),
        )

    def _valid_targets(
        self,
        state: GameState,
        context: dict[str, Any],
        actor_piece: str,
        actor_hex: Hex,
    ) -> list[str]:
        topology = get_topology_service()
        targets: list[str] = []
        actor_id = str(state.current_actor_id) if state.current_actor_id else self.hero_id
        for entity_id in state.entity_locations:
            target_id = str(entity_id)
            if target_id == actor_piece:
                continue
            if not state.get_unit(UnitID(target_id)):
                continue
            target_hex = state.get_position(target_id)
            if target_hex is None or not topology.are_adjacent(actor_hex, target_hex, state):
                continue
            if not state.validator.can_be_targeted(state, actor_id, target_id, context).allowed:
                continue
            if not state.validator.can_be_pushed(state, target_id, actor_id, context).allowed:
                continue

            from goa2.engine.filters_units import ImmunityFilter

            if not ImmunityFilter().apply(target_id, state, context):
                continue
            targets.append(target_id)
        return targets

    def _legal_distances(
        self,
        state: GameState,
        context: dict[str, Any],
        actor_piece: str,
        actor_hex: Hex,
        target_id: str,
    ) -> dict[int, tuple[_PushPreview, Hex | None]]:
        legal: dict[int, tuple[_PushPreview, Hex | None]] = {}
        for distance in range(0, self.max_distance + 1):
            preview = self._preview_push(state, context, actor_hex, target_id, distance)
            if preview is None:
                continue
            mirror_dest = self._mirror_destination(
                state,
                context,
                actor_piece,
                actor_hex,
                preview.direction_idx,
                preview.moved_distance,
            )
            if preview.moved_distance == 0 or mirror_dest is not None:
                legal[distance] = (preview, mirror_dest)
        return legal

    def _preview_push(
        self,
        state: GameState,
        context: dict[str, Any],
        source_hex: Hex,
        target_id: str,
        distance: int,
    ) -> _PushPreview | None:
        target_hex = state.get_position(target_id)
        if target_hex is None:
            return None

        direction_idx = source_hex.direction_to(target_hex)
        if direction_idx is None:
            return None

        path: list[Hex] = [target_hex]
        for _ in range(distance):
            prev = path[-1]
            next_hex = prev.neighbor(direction_idx)
            if next_hex not in state.board.tiles:
                break
            if not are_connected(prev, next_hex, state):
                break

            is_obstacle = state.validator.is_obstacle_for_actor(
                state,
                next_hex,
                str(state.current_actor_id) if state.current_actor_id else target_id,
                context,
            )
            if is_obstacle:
                if state.validator.is_passable_token(state, next_hex):
                    path.append(next_hex)
                    continue
                break
            path.append(next_hex)

        while len(path) > 1 and state.validator.is_passable_token(state, path[-1]):
            path.pop()

        return _PushPreview(
            target_dest=path[-1],
            moved_distance=len(path) - 1,
            direction_idx=direction_idx,
        )

    def _mirror_destination(
        self,
        state: GameState,
        context: dict[str, Any],
        actor_piece: str,
        actor_hex: Hex,
        push_direction_idx: int,
        distance: int,
    ) -> Hex | None:
        if distance == 0:
            return None

        actor_id = str(state.current_actor_id) if state.current_actor_id else self.hero_id
        if not state.validator.can_be_moved(state, actor_piece, actor_id, context).allowed:
            return None
        if not state.validator.can_move(
            state,
            actor_piece,
            distance,
            context,
            is_movement_action=False,
        ).allowed:
            return None

        direction_idx = (push_direction_idx + 3) % 6
        current = actor_hex
        for _ in range(distance):
            next_hex = current.neighbor(direction_idx)
            if next_hex not in state.board.tiles:
                return None
            if not are_connected(current, next_hex, state):
                return None
            if state.validator.is_obstacle_for_actor(state, next_hex, actor_id, context):
                return None
            current = next_hex
        return current


class RemoveHeroPieceStep(GameStep):
    """Voluntarily remove piece(s), without defeat rewards or cascade."""

    type: StepType = StepType.REMOVE_HERO_PIECE
    hero_id: str
    mode: Literal["choose_one", "all_others", "choose_any"] = "choose_one"
    min_remaining: int = 1
    is_mandatory: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.is_multi_piece:
            return StepResult(is_finished=True)

        pieces = state.get_piece_ids(self.hero_id)

        def remove_piece(pid: str) -> GameEvent:
            from_hex = state.entity_locations.get(BoardEntityID(pid))
            for marker in state.markers.values():
                if marker.target_id == pid:
                    marker.remove()
            state.remove_entity(BoardEntityID(pid))
            if str(state.acting_piece_id) == pid:
                state.acting_piece_id = None
            return GameEvent(
                event_type=GameEventType.UNIT_REMOVED,
                actor_id=self.hero_id,
                target_id=pid,
                from_hex=_hex_dict(from_hex),
                metadata={"owner_hero_id": self.hero_id, "voluntary": True},
            )

        if self.mode == "all_others":
            keep = str(state.acting_piece_id) if state.acting_piece_id else None
            if keep not in pieces and pieces:
                keep = pieces[0]
            return StepResult(
                is_finished=True,
                events=[remove_piece(pid) for pid in pieces if pid != keep],
            )

        if len(pieces) <= self.min_remaining:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == SKIP:
                return StepResult(is_finished=True)
            if selection in pieces:
                new_steps: list[GameStep] = []
                if self.mode == "choose_any":
                    new_steps.append(
                        RemoveHeroPieceStep(
                            hero_id=self.hero_id,
                            mode="choose_any",
                            min_remaining=self.min_remaining,
                        )
                    )
                return StepResult(
                    is_finished=True,
                    events=[remove_piece(str(selection))],
                    new_steps=new_steps,
                )
            raise ValueError(f"Invalid piece removal selection: {selection}")

        options = [InputOption(id=pid, text=pid) for pid in pieces]
        options.append(InputOption(id=SKIP, text="Keep all pieces"))
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=self.hero_id,
                prompt=f"Remove one of you? ({len(pieces)} in play)",
                options=options,
                can_skip=True,
            ),
        )
