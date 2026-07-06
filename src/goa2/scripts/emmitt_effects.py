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
# REVERSE TIME (Gold — Untiered, ATK 4)
# "Target a unit adjacent to you. After the attack:
#  Next turn: Heroes with lower initiative act before heroes with higher
#  initiative; this effect ignores immunity. (Resolve ties as normal.)"
# =============================================================================


@register_effect("reverse_time")
class ReverseTimeEffect(CardEffect):
    """Global NEXT_TURN initiative inversion, applied in resolve_next_action.
    Card-bound: deactivates if Emmitt is defeated or the card leaves play.
    Played on the round's last turn it fizzles (NEXT_TURN never crosses
    rounds). No immunity gate anywhere — it is a global ordering rule."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        from goa2.engine.steps import AttackSequenceStep

        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            CreateEffectStep(
                effect_type=EffectType.REVERSED_INITIATIVE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.NEXT_TURN,
                is_active=True,
            ),
        ]


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


# =============================================================================
# GLITCH TOKENS (Flashback / Déjà Vu / Unstable Timeline)
# Shared pieces: pairwise spacing ≥ 3, all-or-nothing batch placement,
# end-of-turn removal of ALL Glitch tokens.
# =============================================================================

GLITCH_SPACING = 3


def _glitch_slot_filters(count: int, radius: int, hero_id: str, key_prefix: str):
    from goa2.engine.filters import RangeFilter

    base = [RangeFilter(max_range=radius, origin_id=hero_id)]
    return [
        [
            *base,
            *[
                RangeFilter(
                    min_range=GLITCH_SPACING,
                    max_range=None,
                    origin_hex_key=f"{key_prefix}_hex_{j}",
                )
                for j in range(i)
            ],
        ]
        for i in range(count)
    ]


def _glitch_cleanup_step(active_if_key: str | None = None) -> GameStep:
    """'End of turn: Remove all Glitch tokens' — a THIS_TURN timer whose
    finishing steps sweep every Glitch token off the board (Min's grenade
    DELAYED_TRIGGER pattern)."""
    from goa2.domain.models import TokenType
    from goa2.engine.filters import TokenTypeFilter, UnitTypeFilter
    from goa2.engine.steps import CollectUnitsStep, RemoveTokenStep

    return CreateEffectStep(
        effect_type=EffectType.DELAYED_TRIGGER,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_TURN,
        is_active=True,
        finishing_steps=[
            CollectUnitsStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                filters=[
                    UnitTypeFilter(unit_type="TOKEN"),
                    TokenTypeFilter(token_type=TokenType.GLITCH),
                ],
                output_key="_glitch_cleanup_ids",
                skip_immunity_filter=True,
                skip_self_filter=True,
            ),
            ForEachStep(
                list_key="_glitch_cleanup_ids",
                item_key="_glitch_cleanup_id",
                steps_template=[RemoveTokenStep(token_key="_glitch_cleanup_id")],
            ),
        ],
        active_if_key=active_if_key,
    )


@register_effect("flashback")
class FlashbackEffect(CardEffect):
    """Attack adjacent. After the attack: you may place 3 Glitch tokens in
    radius (pairwise spacing ≥ 3, all-or-nothing); if you do, up to 1 enemy
    hero in radius swaps with a Glitch token of THEIR choice. End of turn:
    remove all Glitch tokens."""

    token_count = 3

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        from goa2.domain.models import TokenType
        from goa2.engine.filters import RangeFilter, TeamFilter, TokenTypeFilter, UnitTypeFilter
        from goa2.engine.steps import AttackSequenceStep, PlaceTokenBatchStep, SwapUnitsStep

        radius = stats.radius or 0
        return [
            AttackSequenceStep(damage=stats.primary_value, range_val=1),
            PlaceTokenBatchStep(
                token_type=TokenType.GLITCH,
                count=self.token_count,
                slot_filters=_glitch_slot_filters(self.token_count, radius, str(hero.id), "glitch"),
                opt_in_prompt=f"Place {self.token_count} Glitch tokens in radius?",
                owner_id=str(hero.id),
                placed_flag_key="glitch_placed",
                key_prefix="glitch",
                is_mandatory=False,
            ),
            _glitch_cleanup_step(active_if_key="glitch_placed"),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Up to 1 enemy hero in radius swaps with a Glitch token",
                output_key="glitch_victim",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=radius, origin_id=str(hero.id)),
                ],
                is_mandatory=False,
                active_if_key="glitch_placed",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Choose the Glitch token to swap with",
                output_key="glitch_swap_token",
                filters=[
                    UnitTypeFilter(unit_type="TOKEN"),
                    TokenTypeFilter(token_type=TokenType.GLITCH),
                ],
                skip_immunity_filter=True,
                skip_self_filter=True,
                override_player_id_key="glitch_victim",
                is_mandatory=True,
                active_if_key="glitch_victim",
            ),
            SwapUnitsStep(
                unit_a_key="glitch_victim",
                unit_b_key="glitch_swap_token",
                active_if_key="glitch_swap_token",
            ),
        ]


@register_effect("deja_vu")
class DejaVuEffect(FlashbackEffect):
    """Déjà Vu — same as Flashback with 2 Glitch tokens."""

    token_count = 2


@register_effect("unstable_timeline")
class UnstableTimelineEffect(CardEffect):
    """Place 2 Glitch tokens in radius (3 when used as a defense); an enemy
    hero in play — Emmitt picks which — chooses one of the Glitch tokens and
    EMMITT swaps with it (mandatory, no range limit). End of turn: remove all
    Glitch tokens.

    If the tokens cannot all be placed the whole text stops (flag gating, no
    abort) — as a defense the card's defense value 6 still counts. During
    defense resolution the defender is the current actor (SetActorStep wrap
    in ResolveDefenseTextStep), so TeamFilter/default routing are correct."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return self._timeline_steps(hero, stats, count=2)

    def build_defense_steps(self, state, defender, card, stats, context):
        return self._timeline_steps(defender, stats, count=3)

    def _timeline_steps(self, hero: Hero, stats: CardStats, count: int) -> list[GameStep]:
        from goa2.domain.models import TokenType
        from goa2.engine.filters import TeamFilter, TokenTypeFilter, UnitTypeFilter
        from goa2.engine.steps import CountStep, PlaceTokenBatchStep, SwapUnitsStep

        radius = stats.radius or 0
        return [
            PlaceTokenBatchStep(
                token_type=TokenType.GLITCH,
                count=count,
                slot_filters=_glitch_slot_filters(count, radius, str(hero.id), "ut"),
                owner_id=str(hero.id),
                placed_flag_key="ut_placed",
                key_prefix="ut",
                is_mandatory=False,
            ),
            _glitch_cleanup_step(active_if_key="ut_placed"),
            # "An enemy hero in play" — no range limit; skipped (not aborted)
            # when none exists so a defense block still resolves normally.
            CountStep(
                target_type=TargetType.UNIT,
                filters=[UnitTypeFilter(unit_type="HERO"), TeamFilter(relation="ENEMY")],
                output_key="ut_enemy_count",
                skip_immunity_filter=True,
                active_if_key="ut_placed",
            ),
            CheckContextConditionStep(
                input_key="ut_enemy_count",
                operator=">=",
                threshold=1,
                output_key="ut_has_chooser",
                active_if_key="ut_placed",
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Choose the enemy hero who will pick a Glitch token",
                output_key="ut_chooser",
                filters=[UnitTypeFilter(unit_type="HERO"), TeamFilter(relation="ENEMY")],
                skip_immunity_filter=True,  # they only choose; not targeted
                is_mandatory=True,
                override_player_id_key="ut_owner",
                active_if_key="ut_has_chooser",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Choose one of the Glitch tokens",
                output_key="ut_token",
                filters=[
                    UnitTypeFilter(unit_type="TOKEN"),
                    TokenTypeFilter(token_type=TokenType.GLITCH),
                ],
                skip_immunity_filter=True,
                skip_self_filter=True,
                override_player_id_key="ut_chooser",
                is_mandatory=True,
                active_if_key="ut_chooser",
            ),
            SwapUnitsStep(
                unit_a_id=str(hero.id),
                unit_b_key="ut_token",
                active_if_key="ut_token",
            ),
        ]


# =============================================================================
# TIME LOOP (Blue II — range 4)
# "Swap with an enemy hero in range who has already resolved a card this turn."
# =============================================================================


@register_effect("time_loop")
class TimeLoopEffect(CardEffect):
    """Position swap with a resolved enemy hero. SwapUnitsStep runs the
    displacement validation (swap prevention → mandatory abort)."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return self._swap_position_steps(hero, stats)

    def _swap_position_steps(
        self, hero: Hero, stats: CardStats, active_if_key: str | None = None
    ) -> list[GameStep]:
        from goa2.engine.filters import (
            HasResolvedCardFilter,
            RangeFilter,
            TeamFilter,
            UnitTypeFilter,
        )
        from goa2.engine.steps import SwapUnitsStep

        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Swap with an enemy hero who has already resolved a card this turn",
                output_key="tl_target",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 0),
                    HasResolvedCardFilter(),
                ],
                is_mandatory=True,
                active_if_key=active_if_key,
            ),
            SwapUnitsStep(
                unit_a_id=str(hero.id),
                unit_b_key="tl_target",
                is_mandatory=True,
                active_if_key=active_if_key,
            ),
        ]


# =============================================================================
# TIME WARP (Blue III — range 4)
# "Choose one —
#  • Swap with an enemy hero in range who has already resolved a card this
#    turn.
#  • An enemy hero in range swaps their unresolved card with one of their
#    resolved cards of their choice."
# =============================================================================


@register_effect("time_warp")
class TimeWarpEffect(TimeLoopEffect):
    """Bullet A inherits Time Loop's position swap. Bullet B reuses
    SwapCardStep (Hero.swap_cards exchanges location + state + facedown +
    played_this_round): the target needs an unresolved card AND ≥1 resolved
    card; THAT enemy picks which resolved card swaps in. The swapped-out card
    sits RESOLVED in the played slot and never resolves; turn order
    self-corrects because resolve_next_action re-scans unresolved cards."""

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        from goa2.domain.models.enums import CardContainerType
        from goa2.engine.filters import (
            CardsInContainerFilter,
            HasUnresolvedCardFilter,
            RangeFilter,
            TeamFilter,
            UnitTypeFilter,
        )
        from goa2.engine.steps import SwapCardStep

        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Time Warp: choose one",
                output_key="tw_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Swap positions with an enemy hero who has already resolved a card",
                    2: "An enemy hero swaps their unresolved card with a resolved card",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="tw_choice", operator="==", threshold=1, output_key="tw_positions"
            ),
            CheckContextConditionStep(
                input_key="tw_choice", operator="==", threshold=2, output_key="tw_cards"
            ),
            *self._swap_position_steps(hero, stats, active_if_key="tw_positions"),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero to swap their unresolved card",
                output_key="tw_victim",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 0),
                    HasUnresolvedCardFilter(),
                    CardsInContainerFilter(container=CardContainerType.PLAYED, min_cards=1),
                ],
                is_mandatory=True,
                active_if_key="tw_cards",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                prompt="Time Warp: choose one of your resolved cards to swap in",
                output_key="tw_swap_card",
                card_container=CardContainerType.PLAYED,
                context_hero_id_key="tw_victim",
                override_player_id_key="tw_victim",
                is_mandatory=True,
                active_if_key="tw_cards",
            ),
            SwapCardStep(
                target_card_key="tw_swap_card",
                context_hero_id_key="tw_victim",
                active_if_key="tw_cards",
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
