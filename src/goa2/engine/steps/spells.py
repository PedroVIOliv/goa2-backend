"""Spellbook selection and lifecycle steps."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import Field

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.models import CardState, SpellCard, StepType
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.steps.base import GameStep, StepResult
from goa2.engine.steps.cards import PerformCardActionStep

WISH_CAST_COUNTED_CASTER_KEY = "wish_cast_counted_caster_id"


class CastSpellStep(GameStep):
    """Spend one currently prepared allowed spell, then perform its action."""

    type: StepType = StepType.CAST_SPELL
    allowed_spell_ids: list[str]
    caster_id: str | None = None
    caster_key: str | None = None

    def _caster_id(self, state: GameState, context: dict[str, Any]) -> str | None:
        caster_id = self.caster_id
        if self.caster_key:
            caster_id = context.get(self.caster_key) or caster_id
        if caster_id is None and state.current_actor_id is not None:
            caster_id = str(state.current_actor_id)
        if caster_id is None or state.get_hero(HeroID(str(caster_id))) is None:
            return None
        return str(caster_id)

    @staticmethod
    def _request(caster_id: str, eligible: Sequence[SpellCard]) -> StepResult:
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_CARD,
                player_id=caster_id,
                prompt="Choose a prepared spell to cast",
                options=[InputOption(id=spell.id, text=spell.name) for spell in eligible],
            ),
        )

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        owner = state.get_spellbook_owner()
        caster_id = self._caster_id(state, context)
        if owner is None or caster_id is None:
            return StepResult(is_finished=True)

        allowed = set(self.allowed_spell_ids)
        eligible = [spell for spell in owner.spellbook if spell.id in allowed]
        if not eligible:
            return StepResult(is_finished=True)

        selected = None
        if self.pending_input is not None:
            selection = self.pending_input.get("selection")
            selected = next((spell for spell in eligible if spell.id == selection), None)
            if selected is None:
                return self._request(caster_id, eligible)
        elif len(eligible) == 1:
            selected = eligible[0]
        else:
            return self._request(caster_id, eligible)

        selected.state = CardState.OUTSIDE_SPELLBOOK
        selected.is_facedown = False
        context["spell_owner_id"] = str(owner.id)
        context["spell_caster_id"] = caster_id
        context["cast_spell_id"] = selected.id

        performed_step: GameStep
        if selected.id == "wish":
            performed_step = WishSequenceStep(
                caster_id=caster_id,
                perform_wish_action=True,
            )
        else:
            performed_step = PerformCardActionStep(
                card_key="cast_spell_id",
                card_owner_key="spell_owner_id",
                hero_id=caster_id,
                suppress_after_resolve_card=True,
            )

        return StepResult(
            is_finished=True,
            new_steps=[performed_step],
            events=[
                GameEvent(
                    event_type=GameEventType.SPELL_CAST,
                    actor_id=caster_id,
                    metadata={
                        "spell_id": selected.id,
                        "owner_id": str(owner.id),
                        "caster_id": caster_id,
                    },
                )
            ],
        )


class WishSequenceStep(GameStep):
    """Count a Wish cast, resolve another prepared spell, then check victory.

    The sequence is an action-abort boundary because the selected spell must
    resolve (or fizzle) before the third-Wish victory is checked. A mandatory
    failure inside that spell therefore ends the nested spell, not this
    completion check.
    """

    type: StepType = StepType.WISH_SEQUENCE
    survives_action_abort: ClassVar[bool] = True
    caster_id: str
    started: bool = False
    required_casts: int = 3
    perform_wish_action: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        caster = state.get_hero(HeroID(self.caster_id))
        if caster is None:
            return StepResult(is_finished=True)

        if not self.started:
            self.started = True
            caster.wish_cast_count += 1
            if self.perform_wish_action:
                context[WISH_CAST_COUNTED_CASTER_KEY] = str(caster.id)
                nested_step: GameStep = PerformCardActionStep(
                    card_key="cast_spell_id",
                    card_owner_key="spell_owner_id",
                    hero_id=str(caster.id),
                    suppress_after_resolve_card=True,
                )
            else:
                owner = state.get_spellbook_owner()
                allowed_spell_ids = (
                    [spell.id for spell in owner.spellbook if spell.id != "wish"]
                    if owner is not None
                    else []
                )
                nested_step = CastSpellStep(
                    allowed_spell_ids=allowed_spell_ids,
                    caster_id=str(caster.id),
                )
            return StepResult(
                is_finished=False,
                new_steps=[nested_step],
                events=[
                    GameEvent(
                        event_type=GameEventType.WISH_CAST_COUNT_CHANGED,
                        actor_id=str(caster.id),
                        metadata={
                            "count": caster.wish_cast_count,
                            "required": self.required_casts,
                        },
                    )
                ],
            )

        if context.get(WISH_CAST_COUNTED_CASTER_KEY) == str(caster.id):
            context.pop(WISH_CAST_COUNTED_CASTER_KEY, None)

        if caster.wish_cast_count >= self.required_casts and caster.team is not None:
            from goa2.engine.steps.combat import TriggerGameOverStep

            return StepResult(
                is_finished=True,
                new_steps=[TriggerGameOverStep(winner=caster.team, condition="WISH")],
            )
        return StepResult(is_finished=True)


class PrepareSpellbookStep(GameStep):
    """Return every spent spell to the unique owner's hidden spellbook."""

    type: StepType = StepType.PREPARE_SPELLBOOK

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        owner = state.get_spellbook_owner()
        if owner is None:
            return StepResult(is_finished=True)

        returned_spell_ids = sorted(spell.id for spell in owner.cast_spells)
        for spell_id in returned_spell_ids:
            spell = state.get_card_for_hero(str(owner.id), spell_id)
            if spell is None:
                continue
            EffectManager.expire_by_card(state, spell.id)
            spell.state = CardState.SPELLBOOK
            spell.is_facedown = True

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.SPELLBOOK_PREPARED,
                    actor_id=(
                        str(state.current_actor_id)
                        if state.current_actor_id is not None
                        else str(owner.id)
                    ),
                    metadata={
                        "returned_spell_ids": returned_spell_ids,
                        "spellbook_count": len(owner.spellbook),
                    },
                )
            ],
        )


class RemovePreparedSpellsStep(GameStep):
    """Optionally reveal and remove up to ``max_removals`` prepared spells.

    The unique spellbook owner supplies the cards, while ``caster_id`` identifies
    the player making the choices. Removing a spell is not casting it: no card
    action is performed and no ``SPELL_CAST`` event is emitted.
    """

    type: StepType = StepType.REMOVE_PREPARED_SPELLS
    caster_id: str | None = None
    caster_key: str | None = None
    max_removals: int = 3
    removed_spell_ids: list[str] = Field(default_factory=list)

    def _caster_id(self, state: GameState, context: dict[str, Any]) -> str | None:
        caster_id = self.caster_id
        if self.caster_key:
            caster_id = context.get(self.caster_key) or caster_id
        if caster_id is None and state.current_actor_id is not None:
            caster_id = str(state.current_actor_id)
        return str(caster_id) if caster_id is not None else None

    def _request(self, caster_id: str, eligible: Sequence[SpellCard]) -> StepResult:
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_CARD,
                player_id=caster_id,
                prompt=(
                    "Find Familiar: remove up to three other prepared spells "
                    f"({len(self.removed_spell_ids)}/{self.max_removals})"
                ),
                options=[InputOption(id=spell.id, text=spell.name) for spell in eligible],
                can_skip=True,
            ),
        )

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        owner = state.get_spellbook_owner()
        caster_id = self._caster_id(state, context)
        if owner is None or caster_id is None or len(self.removed_spell_ids) >= self.max_removals:
            return StepResult(is_finished=True)

        eligible = [spell for spell in owner.spellbook if spell.id not in self.removed_spell_ids]
        if not eligible:
            return StepResult(is_finished=True)

        events: list[GameEvent] = []
        if self.pending_input is not None:
            selection = self.pending_input.get("selection")
            self.pending_input = None
            if selection == "SKIP":
                return StepResult(is_finished=True)
            selected = next((spell for spell in eligible if spell.id == selection), None)
            if selected is None:
                return self._request(caster_id, eligible)

            selected.state = CardState.OUTSIDE_SPELLBOOK
            selected.is_facedown = False
            self.removed_spell_ids.append(selected.id)
            events.append(
                GameEvent(
                    event_type=GameEventType.SPELL_REMOVED_FROM_SPELLBOOK,
                    actor_id=caster_id,
                    metadata={
                        "spell_id": selected.id,
                        "owner_id": str(owner.id),
                        "caster_id": caster_id,
                    },
                )
            )
            if len(self.removed_spell_ids) >= self.max_removals:
                return StepResult(is_finished=True, events=events)
            eligible = [spell for spell in owner.spellbook]
            if not eligible:
                return StepResult(is_finished=True, events=events)

        request = self._request(caster_id, eligible)
        request.events = events
        return request
