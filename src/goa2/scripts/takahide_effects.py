"""Takahide — discard-support samurai with a three-gold card cycle.

Two engines drive the kit:

* **Ally discard-for-benefit** — "a friendly hero in range/radius may discard
  a card; if that hero has a card in the discard, <benefit>". The shared
  ``_ally_discard_gate`` helper builds that pipeline.
* **Gold cycle** — Float Like a Butterfly / Sting Like a Bee / Strike Like a
  Tiger rotate through the deck via ``SwapWithDeckCardStep``; Bushido swaps the
  out-of-deck gold; the ultimate ends the cycle by taking all three into hand.

Design notes live in ``docs/superpowers/plans/2026-07-11-takahide-tdd-paths.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import ActionType, CardContainerType, TargetType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import TeamFilter, UnitTypeFilter
from goa2.engine.steps import (
    CheckContextConditionStep,
    CountCardsStep,
    DiscardCardStep,
    GainCoinsStep,
    MoveUnitStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats
    from goa2.engine.steps import GameStep


# Context keys shared by the discard-support families.
ALLY_KEY = "tk_ally"
ALLY_DISCARD_KEY = "tk_ally_discard"
ALLY_DISCARD_COUNT_KEY = "tk_ally_discard_count"
HAS_DISCARD_KEY = "tk_has_discard"
SELF_KEY = "tk_self"  # Takahide's own id (GainCoinsStep only takes a context key)
RETRIEVE_KEY = "tk_retrieve"


# =============================================================================
# Lane A: discard-support families (Come to Aid / Pledge / Calculated Risk)
# =============================================================================


def _ally_discard_gate(
    distance: int,
    *,
    attack_cards_only: bool = False,
) -> list[GameStep]:
    """ "A friendly hero in range/radius may discard a card. If that hero has a
    card in the discard, …" — the pipeline every support card opens with.

    Takahide picks the ally (mandatory: no ally ⇒ the whole action aborts). The
    ALLY's own player then decides whether to discard (optional). The gate flag
    `tk_has_discard` is set from the ally's discard pile AFTER that choice, so a
    pre-existing discard satisfies it just as well (interp 5).
    """
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Choose a friendly hero",
            output_key=ALLY_KEY,
            is_mandatory=True,
            filters=[
                TeamFilter(relation="FRIENDLY"),
                UnitTypeFilter(unit_type="HERO"),
                RangeFilter(max_range=distance),
            ],
        ),
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.HAND,
            prompt=(
                "You may discard an attack card" if attack_cards_only else "You may discard a card"
            ),
            output_key=ALLY_DISCARD_KEY,
            is_mandatory=False,
            active_if_key=ALLY_KEY,
            context_hero_id_key=ALLY_KEY,
            override_player_id_key=ALLY_KEY,
            card_action_types=[ActionType.ATTACK] if attack_cards_only else None,
        ),
        DiscardCardStep(
            card_key=ALLY_DISCARD_KEY,
            hero_key=ALLY_KEY,
            active_if_key=ALLY_DISCARD_KEY,
        ),
        CountCardsStep(
            hero_key=ALLY_KEY,
            card_container=CardContainerType.DISCARD,
            output_key=ALLY_DISCARD_COUNT_KEY,
            active_if_key=ALLY_KEY,
        ),
        CheckContextConditionStep(
            input_key=ALLY_DISCARD_COUNT_KEY,
            operator=">=",
            threshold=1,
            output_key=HAS_DISCARD_KEY,
        ),
    ]


def _optional_move(
    distance: int,
    *,
    output_key: str,
    prompt: str,
    unit_id: str | None = None,
    unit_key: str | None = None,
    ignore_obstacles: bool = False,
    player_id_key: str | None = None,
    active_if_key: str | None = None,
) -> list[GameStep]:
    """Effect-side "may move up to N spaces" (SelectStep + MoveUnitStep).

    The MOVING hero picks the destination (`player_id_key` routes the prompt to
    them). Not a MOVEMENT action, so MoveSequenceStep is deliberately not used.
    """
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt=prompt,
            output_key=output_key,
            is_mandatory=False,
            active_if_key=active_if_key,
            override_player_id_key=player_id_key,
            filters=[
                RangeFilter(max_range=distance, origin_id=unit_id, origin_key=unit_key),
                MovementPathFilter(
                    range_val=distance,
                    unit_id=unit_id,
                    unit_key=unit_key,
                    pass_through_obstacles=ignore_obstacles,
                ),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        MoveUnitStep(
            unit_id=unit_id,
            unit_key=unit_key,
            destination_key=output_key,
            range_val=distance,
            pass_through_obstacles=ignore_obstacles,
            active_if_key=output_key,
        ),
    ]


class SupportMoveEffect(CardEffect):
    """ "A friendly hero in range may discard a card. If that hero has a card in
    the discard, you may move up to N spaces[, ignoring obstacles]."

    Come to Aid (3) / Bring the Relief (4) / Commit Reserves (4, ignoring
    obstacles).
    """

    move_distance: int = 3
    ignore_obstacles: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            *_ally_discard_gate(stats.range),
            *_optional_move(
                self.move_distance,
                unit_id=str(hero.id),
                output_key="tk_self_move",
                prompt=f"You may move up to {self.move_distance} spaces",
                ignore_obstacles=self.ignore_obstacles,
                active_if_key=HAS_DISCARD_KEY,
            ),
        ]


@register_effect("come_to_aid")
class ComeToAidEffect(SupportMoveEffect):
    move_distance: int = 3


@register_effect("bring_the_relief")
class BringTheReliefEffect(SupportMoveEffect):
    move_distance: int = 4


@register_effect("commit_reserves")
class CommitReservesEffect(SupportMoveEffect):
    move_distance: int = 4
    ignore_obstacles: bool = True


class SupportEconomyEffect(CardEffect):
    """ "… If that hero has a card in the discard, both you and that hero gain N
    coin(s) and you may retrieve a discarded card."

    Pledge of Allegiance (1 coin) / Loyal Retainer (2 coins). The retrieve reads
    Takahide's OWN discard (interp 7) and may take a facedown card (S15): moving
    a card between zones needs no knowledge of its face.
    """

    coins: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            *_ally_discard_gate(stats.range),
            SetContextFlagStep(key=SELF_KEY, value=str(hero.id)),
            GainCoinsStep(hero_key=SELF_KEY, amount=self.coins, active_if_key=HAS_DISCARD_KEY),
            GainCoinsStep(hero_key=ALLY_KEY, amount=self.coins, active_if_key=HAS_DISCARD_KEY),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="You may retrieve a discarded card",
                output_key=RETRIEVE_KEY,
                is_mandatory=False,
                include_facedown=True,
                active_if_key=HAS_DISCARD_KEY,
            ),
            RetrieveCardStep(card_key=RETRIEVE_KEY, active_if_key=RETRIEVE_KEY),
        ]


@register_effect("pledge_of_allegiance")
class PledgeOfAllegianceEffect(SupportEconomyEffect):
    coins: int = 1


@register_effect("loyal_retainer")
class LoyalRetainerEffect(SupportEconomyEffect):
    coins: int = 2


class SupportRepositionEffect(CardEffect):
    """ "A friendly hero in radius may discard an attack card. If that hero has a
    card in the discard, that hero may move up to 2 spaces[, ignoring obstacles]."

    Calculated Risk / Tactical Gambit (ignoring obstacles). "An attack card" is a
    card whose PRIMARY action is Attack (interp 6); the pre-existing discard that
    satisfies the condition may be any card (interp 5).
    """

    move_distance: int = 2
    ignore_obstacles: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            *_ally_discard_gate(stats.radius or 0, attack_cards_only=True),
            *_optional_move(
                self.move_distance,
                unit_key=ALLY_KEY,
                output_key="tk_ally_move",
                prompt=f"You may move up to {self.move_distance} spaces",
                ignore_obstacles=self.ignore_obstacles,
                player_id_key=ALLY_KEY,
                active_if_key=HAS_DISCARD_KEY,
            ),
        ]


@register_effect("calculated_risk")
class CalculatedRiskEffect(SupportRepositionEffect):
    pass


@register_effect("tactical_gambit")
class TacticalGambitEffect(SupportRepositionEffect):
    ignore_obstacles: bool = True


# =============================================================================
# Lane B: color-discard punish family (Proven Warrior / The Right Hand)
# =============================================================================


# =============================================================================
# Lane C: unresolved-card swap family (Set an Example / Hold My Saké)
# =============================================================================


# =============================================================================
# Lane D: spatial denial family (Spinning Blade / Blade Helix)
# =============================================================================


# =============================================================================
# Lane E: gold cycle (Float / Sting / Strike / Bushido) + Ready for War
# =============================================================================
