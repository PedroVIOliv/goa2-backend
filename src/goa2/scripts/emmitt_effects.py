"""
Emmitt - Time-manipulation hero card effects.

Design rulings locked with the user are documented in
docs/superpowers/plans/2026-07-05-emmitt-tdd-paths.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import TargetType
from goa2.domain.models.effect import AffectsFilter, DurationType, EffectScope, EffectType, Shape
from goa2.domain.types import HeroID
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    CheckContextConditionStep,
    CreateEffectStep,
    ForEachStep,
    GameStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.topology import get_topology_service

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats

# =============================================================================
# ALTERNATIVE TIMELINES (Ultimate — Tier IV Passive)
# "You may play two cards each turn; if you do, after the cards are revealed,
#  retrieve one of your unresolved cards."
# =============================================================================


# =============================================================================
# TIME CAPSULE (Green II — radius 4)
# "You, and friendly heroes in radius, may retrieve all cards discarded
#  this turn."
# =============================================================================


@register_effect("time_capsule")
class TimeCapsuleEffect(CardEffect):
    """Each eligible hero (Emmitt always; friendly heroes within radius)
    with at least one card in this turn's discard log independently chooses
    (all-or-nothing) to retrieve all their own this-turn discards."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return self._build_retrieval_steps(state, hero, stats)

    def _build_retrieval_steps(
        self,
        state: GameState,
        hero: Hero,
        stats: CardStats,
        active_if_key: str | None = None,
    ) -> list[GameStep]:
        radius = stats.radius or 0
        topology = get_topology_service()
        my_hex = state.get_position(str(hero.id))

        # "You, and friendly heroes in radius" — Emmitt regardless of radius,
        # allies (any board piece) within it. Eligibility and the card list are
        # both evaluated now, at resolution time.
        eligible: list[str] = []
        team = state.teams.get(hero.team) if hero.team else None
        for ally in team.heroes if team else []:
            hid = str(ally.id)
            if not state.turn_discard_log.get(HeroID(hid)):
                continue
            if hid == str(hero.id):
                eligible.append(hid)
                continue
            if my_hex is None or radius <= 0:
                continue
            in_radius = any(
                (pos := state.get_position(piece_id)) is not None
                and topology.distance(my_hex, pos, state) <= radius
                for piece_id in state.get_piece_ids(hid)
            )
            if in_radius:
                eligible.append(hid)

        # Emmitt (the actor) decides first.
        eligible.sort(key=lambda hid: hid != str(hero.id))

        steps: list[GameStep] = []
        for i, hid in enumerate(eligible):
            hero_key = f"tc_hero_{i}"
            choice_key = f"tc_choice_{i}"
            yes_key = f"tc_yes_{i}"
            cards_key = f"tc_cards_{i}"
            card_key = f"tc_card_{i}"
            steps.extend(
                [
                    SetContextFlagStep(key=hero_key, value=hid, active_if_key=active_if_key),
                    SetContextFlagStep(
                        key=cards_key,
                        value=list(state.turn_discard_log.get(HeroID(hid), [])),
                        active_if_key=active_if_key,
                    ),
                    SelectStep(
                        target_type=TargetType.NUMBER,
                        prompt="Time Capsule: retrieve all cards you discarded this turn?",
                        output_key=choice_key,
                        number_options=[1, 0],
                        number_labels={1: "Retrieve all", 0: "Decline"},
                        override_player_id_key=hero_key,
                        is_mandatory=True,
                        active_if_key=active_if_key,
                    ),
                    CheckContextConditionStep(
                        input_key=choice_key,
                        operator="==",
                        threshold=1,
                        output_key=yes_key,
                        active_if_key=active_if_key,
                    ),
                    ForEachStep(
                        list_key=cards_key,
                        item_key=card_key,
                        steps_template=[
                            RetrieveCardStep(card_key=card_key, hero_key=hero_key),
                        ],
                        active_if_key=yes_key,
                    ),
                ]
            )
        return steps


# =============================================================================
# FUTURE PROOF (Green III — radius 4)
# "Choose one —
#  • You, and friendly heroes in radius, may retrieve all cards discarded
#    this turn.
#  • This turn: Friendly heroes in radius are immune to enemy actions."
# =============================================================================


@register_effect("future_proof")
class FutureProofEffect(TimeCapsuleEffect):
    """Bullet A inherits Time Capsule; bullet B creates a moving radius aura
    (evaluated at check time in is_immune) that excludes Emmitt himself."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Future Proof: choose one",
                output_key="fp_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Retrieve cards discarded this turn (you + allies in radius)",
                    2: "This turn: friendly heroes in radius are immune to enemy actions",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="fp_choice", operator="==", threshold=1, output_key="fp_retrieve"
            ),
            CheckContextConditionStep(
                input_key="fp_choice", operator="==", threshold=2, output_key="fp_immunity"
            ),
            *self._build_retrieval_steps(state, hero, stats, active_if_key="fp_retrieve"),
            CreateEffectStep(
                effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=str(hero.id),
                    affects=AffectsFilter.FRIENDLY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                is_active=True,
                active_if_key="fp_immunity",
            ),
        ]


@register_effect("alternative_timelines")
class AlternativeTimelinesEffect(CardEffect):
    """Planning-phase passive: enables the two-card commit flow.

    The mechanic lives in the planning/revelation machinery
    (engine/phases.py), which checks this capability flag on the ultimate's
    effect class. The effect itself produces no steps.
    """

    plays_two_cards = True
