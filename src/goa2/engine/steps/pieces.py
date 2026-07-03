"""Steps for multi-piece heroes (Razzle): acting-piece choice, spawn, removal."""

from __future__ import annotations

import logging
from typing import Any, Literal

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex
from goa2.domain.input import SKIP, InputOption, InputRequestType, create_input_request
from goa2.domain.models import StepType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.steps.base import GameStep, StepResult
from goa2.engine.topology import topology_distance

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
