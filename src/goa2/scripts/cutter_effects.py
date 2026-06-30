"""Cutter card effects.

Cutter is a pirate. His kit centers on forcing enemy heroes to discard cards
(Bombardment family / Brace-charge family), repositioning enemies, and a coin
economy (X Marks the Spot / A Fistful of Coins) toward an alternate solo-win.

Card interpretations are locked in the project memory
(project-cutter-design-decisions). Key reuse:
- Bombardment/Barrage/Broadside  -> ForceDiscardStep with a radius/adjacency filter combo
- Brace/Ramming/Crashland         -> straight-line charge (ignore obstacles) + discard
- Daring/Bold/Fearless            -> modal charge attack (collinear ahead) vs adjacent attack
- Evasive/Tumble                  -> ranged straight-line attack + opposite-direction move
- Outmaneuver/Outsmart            -> swap with enemy minion + optional nudge
- X Marks/A Fistful               -> enemy chooses: place vs gain coins
- Legend of the Skies (ultimate)  -> re-perform previous turn slot's primary action
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import TargetType
from goa2.domain.models.enums import PassiveTrigger
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.filters_composite import CountMatchFilter
from goa2.engine.filters_geometry import (
    InStraightLineFilter,
    SameDirectionFromOriginFilter,
    StraightLinePathFilter,
)
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import (
    AdjacencyFilter,
    ExcludeIdentityFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CheckSoloWinStep,
    CheckZoneChangeStep,
    ComputeHexStep,
    DefeatUnitStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GainCoinsStep,
    GameStep,
    MoveTowardTargetStep,
    MoveUnitStep,
    PerformPrimaryActionStep,
    PlaceUnitStep,
    PushUnitStep,
    RecordHexStep,
    SelectStep,
    SetContextFlagStep,
    SwapUnitsStep,
)
from goa2.engine.steps.utility import MayRepeatOnceStep

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


# =============================================================================
# BLUE — Bombardment / Barrage / Broadside
# "An enemy hero in radius, adjacent to another enemy unit and not adjacent to
#  you, discards a card, if able." (Broadside: "May repeat once on a different
#  target.")
# =============================================================================


def _bombardment_select(output_key: str, radius: int | None, exclude_keys: list[str]) -> SelectStep:
    """Select an enemy hero that is: in radius, NOT adjacent to Cutter
    (min_range 2), and adjacent to another enemy unit."""
    return SelectStep(
        target_type=TargetType.UNIT,
        prompt="Select an enemy hero to make discard",
        output_key=output_key,
        filters=[
            UnitTypeFilter(unit_type="HERO"),
            TeamFilter(relation="ENEMY"),
            # In radius, but not adjacent to you (min_range 2 = "not adjacent").
            RangeFilter(min_range=2, max_range=radius),
            # Adjacent to ANOTHER enemy unit: count enemy units (of Cutter)
            # within 1 of the candidate hex, excluding the candidate itself
            # (min_range 1 from the candidate hex drops distance-0 self).
            CountMatchFilter(
                min_count=1,
                sub_filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(
                        min_range=1,
                        max_range=1,
                        origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY,
                    ),
                ],
            ),
            *([ExcludeIdentityFilter(exclude_keys=exclude_keys)] if exclude_keys else []),
        ],
    )


class _BombardmentEffect(CardEffect):
    """Base for the Bombardment discard family. Subclasses set radius and repeat."""

    repeat: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius
        steps: list[GameStep] = [
            _bombardment_select("bombard_target_1", radius, exclude_keys=[]),
            ForceDiscardStep(victim_key="bombard_target_1"),
        ]
        if self.repeat:
            steps.append(
                MayRepeatOnceStep(
                    prompt="Bombard a different enemy hero?",
                    steps_template=[
                        _bombardment_select(
                            "bombard_target_2", radius, exclude_keys=["bombard_target_1"]
                        ),
                        ForceDiscardStep(victim_key="bombard_target_2"),
                    ],
                )
            )
        return steps


@register_effect("bombardment")
class BombardmentEffect(_BombardmentEffect):
    """Radius 3, no repeat."""


@register_effect("barrage")
class BarrageEffect(_BombardmentEffect):
    """Radius 4, no repeat (evolution of Bombardment)."""


@register_effect("broadside")
class BroadsideEffect(_BombardmentEffect):
    """Radius 4, may repeat once on a different target."""

    repeat = True


# =============================================================================
# GREEN — Outmaneuver / Outsmart
# "Swap with an enemy minion in radius; you may move that minion up to N spaces."
# =============================================================================


class _OutmaneuverEffect(CardEffect):
    """Base for the swap-and-nudge family. Subclasses set the nudge distance."""

    nudge: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            # Swap is mandatory: an enemy minion in radius (immune minions are
            # excluded by the default offensive immunity filter on SelectStep).
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy minion to swap with",
                output_key="swap_minion",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius),
                ],
            ),
            SwapUnitsStep(unit_a_id=str(hero.id), unit_b_key="swap_minion"),
            # Optional nudge of that minion, up to N spaces (real movement path).
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"You may move that minion up to {self.nudge} spaces",
                output_key="nudge_dest",
                is_mandatory=False,
                filters=[
                    MovementPathFilter(range_val=self.nudge, unit_key="swap_minion"),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_key="swap_minion",
                destination_key="nudge_dest",
                range_val=self.nudge,
                is_movement_action=False,
                active_if_key="nudge_dest",
            ),
        ]


@register_effect("outmaneuver")
class OutmaneuverEffect(_OutmaneuverEffect):
    """Radius 3, nudge up to 2."""

    nudge = 2


@register_effect("outsmart")
class OutsmartEffect(_OutmaneuverEffect):
    """Radius 3, nudge up to 3."""

    nudge = 3


# =============================================================================
# BLUE — X Marks the Spot / A Fistful of Coins
# "An enemy hero in radius chooses one — • You place that hero in a space in
#  radius. • You gain N coins." (A Fistful: 13+ coins => you alone win — stubbed.)
# =============================================================================


class _CoinChoiceEffect(CardEffect):
    """Base for the enemy-chooses place-vs-coins family.

    The chosen enemy hero picks the option (their player), Cutter executes it.
    Subclasses set the coin amount and whether the solo-win check applies.
    """

    coins: int = 2
    solo_win: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius
        coins_steps: list[GameStep] = [
            CheckContextConditionStep(
                input_key="coin_choice", operator="==", threshold=2, output_key="chose_coins"
            ),
            SetContextFlagStep(key="self", value=str(hero.id)),
            GainCoinsStep(hero_key="self", amount=self.coins, active_if_key="chose_coins"),
        ]
        if self.solo_win:
            coins_steps.append(CheckSoloWinStep(hero_key="self", active_if_key="chose_coins"))

        return [
            # Cutter chooses which enemy hero in radius is affected.
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in radius",
                output_key="coin_target",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=radius),
                ],
            ),
            # That enemy hero's player chooses the option.
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="coin_choice",
                number_options=[1, 2],
                number_labels={
                    1: "Be placed by the enemy",
                    2: f"Give the enemy {self.coins} coins",
                },
                is_mandatory=True,
                context_hero_id_key="coin_target",
                override_player_id_key="coin_target",
            ),
            # Option 1: Cutter places that hero in an empty space in radius.
            CheckContextConditionStep(
                input_key="coin_choice", operator="==", threshold=1, output_key="chose_place"
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Place that hero in a space in radius",
                output_key="place_dest",
                is_mandatory=True,
                active_if_key="chose_place",
                filters=[
                    RangeFilter(max_range=radius),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            PlaceUnitStep(
                unit_key="coin_target",
                destination_key="place_dest",
                active_if_key="place_dest",
            ),
            # Option 2: Cutter gains coins (and, for A Fistful, the win check).
            *coins_steps,
        ]


@register_effect("x_marks_the_spot")
class XMarksTheSpotEffect(_CoinChoiceEffect):
    """Radius 3, 2 coins, no win."""

    coins = 2
    solo_win = False


@register_effect("a_fistful_of_coins")
class AFistfulOfCoinsEffect(_CoinChoiceEffect):
    """Radius 3, 3 coins, solo-win check (stubbed)."""

    coins = 3
    solo_win = True


# =============================================================================
# GREEN — Brace for Impact / Ramming Speed / Crashland
# "Move N in a straight line, ignoring obstacles, to a space adjacent to an enemy
#  hero; that hero discards a card, if able."
#
# Bound sentence: the landing must enable the discard, so the destination must be
# adjacent to a NON-IMMUNE enemy hero (skip_immune on the adjacency anchor).
# =============================================================================


class _BraceChargeEffect(CardEffect):
    """Base for the straight-line charge-and-discard family.

    Subclasses set the min/max charge distance.
    """

    min_dist: int = 3
    max_dist: int = 3

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            # Mandatory straight-line move (ignoring obstacles) onto an empty hex
            # adjacent to a non-immune enemy hero.
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Charge in a straight line to a space adjacent to an enemy hero",
                output_key="charge_dest",
                is_mandatory=True,
                filters=[
                    RangeFilter(min_range=self.min_dist, max_range=self.max_dist),
                    InStraightLineFilter(origin_id=str(hero.id)),
                    StraightLinePathFilter(origin_id=str(hero.id), pass_through_obstacles=True),
                    ObstacleFilter(is_obstacle=False),
                    AdjacencyFilter(target_tags=["ENEMY", "HERO"], skip_immune=True),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="charge_dest",
                range_val=99,
                pass_through_obstacles=True,
            ),
            # That hero discards (Cutter chooses which adjacent non-immune hero).
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select the adjacent enemy hero to make discard",
                output_key="charge_victim",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            ForceDiscardStep(victim_key="charge_victim"),
        ]


@register_effect("brace_for_impact")
class BraceForImpactEffect(_BraceChargeEffect):
    """Move exactly 3."""

    min_dist = 3
    max_dist = 3


@register_effect("ramming_speed")
class RammingSpeedEffect(_BraceChargeEffect):
    """Move 3 or 4."""

    min_dist = 3
    max_dist = 4


@register_effect("crashland")
class CrashlandEffect(_BraceChargeEffect):
    """Move 3, 4 or 5."""

    min_dist = 3
    max_dist = 5


# =============================================================================
# RED — Evasive Shot / Tumble Shot
# "Target a unit in range and in a straight line. After the attack: Move up to N
#  spaces in the opposite direction." (ranged, range 2)
#
# The opposite direction is captured BEFORE the attack (via a reference hex one
# step beyond Cutter, away from the target) so the retreat still works if the
# target is defeated by the attack.
# =============================================================================


class _TumbleShotEffect(CardEffect):
    """Base for the ranged straight-line attack + opposite-direction retreat."""

    retreat: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            # Select the target first so we can record the retreat direction
            # before the attack possibly removes it.
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit in range and in a straight line",
                output_key="tumble_victim",
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                    InStraightLineFilter(origin_id=str(hero.id)),
                ],
            ),
            SetContextFlagStep(key="tumble_self", value=str(hero.id)),
            # away_ref = Cutter + normalize(Cutter - victim): one hex beyond Cutter
            # directly away from the target, defining the "opposite direction".
            ComputeHexStep(
                origin_key="tumble_victim",
                target_key="tumble_self",
                scale=1,
                output_key="away_ref",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_id_key="tumble_victim",
            ),
            # Optional retreat up to N in the opposite direction.
            SelectStep(
                target_type=TargetType.HEX,
                prompt=f"You may move up to {self.retreat} spaces in the opposite direction",
                output_key="retreat_dest",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=self.retreat),
                    SameDirectionFromOriginFilter(reference_key="away_ref"),
                    StraightLinePathFilter(origin_id=str(hero.id)),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="retreat_dest",
                range_val=self.retreat,
                active_if_key="retreat_dest",
            ),
        ]


@register_effect("evasive_shot")
class EvasiveShotEffect(_TumbleShotEffect):
    """Retreat up to 2."""

    retreat = 2


@register_effect("tumble_shot")
class TumbleShotEffect(_TumbleShotEffect):
    """Retreat up to 3."""

    retreat = 3


# =============================================================================
# SILVER — Grappling Bolt
# "Target an obstacle in range and in a straight line, with no obstacles between
#  you; ignore immunity. Move in a straight line towards that obstacle until you
#  are adjacent to it."
#
# Target a HEX that is an obstacle: terrain / token / unit / turret all qualify
# (tile.is_obstacle), and targeting a hex ignores occupant immunity. The clear
# intermediate path ("no obstacles between") is enforced by StraightLinePathFilter.
# =============================================================================


# =============================================================================
# RED — Daring Strike / Bold Thrust / Fearless Lunge
# "Choose one — • Move 1/2/3 in a straight line. Target a hero adjacent to you in
#  the direction of the move; +2 Attack. • Target a unit adjacent to you."
#
# Separate sentences: the charge MOVE is committed independently; the attack is a
# conditional follow-up on a hero collinear-ahead. Both branches are always
# offered. Branch B is a plain adjacent attack with no bonus.
# =============================================================================


class _ChargeAttackEffect(CardEffect):
    """Base for the modal charge-attack family. Subclasses set the charge range."""

    max_charge: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="charge_choice",
                number_options=[1, 2],
                number_labels={1: "Charge + attack a hero ahead", 2: "Attack adjacent unit"},
                is_mandatory=True,
            ),
            # ---- Branch A: charge (move committed), then conditional +2 attack.
            CheckContextConditionStep(
                input_key="charge_choice", operator="==", threshold=1, output_key="chose_charge"
            ),
            RecordHexStep(unit_id=str(hero.id), output_key="charge_origin"),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move in a straight line",
                output_key="charge_dest",
                is_mandatory=True,
                active_if_key="chose_charge",
                filters=[
                    RangeFilter(min_range=1, max_range=self.max_charge),
                    InStraightLineFilter(origin_id=str(hero.id)),
                    StraightLinePathFilter(origin_id=str(hero.id)),
                    ObstacleFilter(is_obstacle=False),
                ],
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="charge_dest",
                range_val=99,
                active_if_key="charge_dest",
            ),
            # Optional: a hero adjacent and in the direction of the move (+2).
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a hero in the direction of the move.",
                output_key="charge_victim",
                active_if_key="charge_dest",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                    SameDirectionFromOriginFilter(
                        origin_hex_key="charge_origin", reference_key="charge_dest"
                    ),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value + 2,
                target_id_key="charge_victim",
                range_val=1,
                active_if_key="charge_victim",
            ),
            # ---- Branch B: plain adjacent attack, no bonus.
            CheckContextConditionStep(
                input_key="charge_choice", operator="==", threshold=2, output_key="chose_adjacent"
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                active_if_key="chose_adjacent",
            ),
        ]


@register_effect("daring_strike")
class DaringStrikeEffect(_ChargeAttackEffect):
    """Move 1."""

    max_charge = 1


@register_effect("bold_thrust")
class BoldThrustEffect(_ChargeAttackEffect):
    """Move 1 or 2."""

    max_charge = 2


@register_effect("fearless_lunge")
class FearlessLungeEffect(_ChargeAttackEffect):
    """Move 1, 2 or 3."""

    max_charge = 3


@register_effect("grappling_bolt")
class GrapplingBoltEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Target an obstacle in range and in a straight line",
                output_key="grapple_target",
                filters=[
                    RangeFilter(min_range=1, max_range=stats.range),
                    InStraightLineFilter(origin_id=str(hero.id)),
                    StraightLinePathFilter(origin_id=str(hero.id)),
                    ObstacleFilter(is_obstacle=True),
                ],
            ),
            MoveTowardTargetStep(target_hex_key="grapple_target"),
        ]


# =============================================================================
# GOLD — Walk the Plank
# "Choose one — • Push an enemy hero adjacent to you up to 4 spaces; if that hero
#  is pushed into another zone, that hero discards a card, or is defeated.
#  • Defeat a minion adjacent to you." Both branches always offered.
# =============================================================================


@register_effect("walk_the_plank")
class WalkThePlankEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose one",
                output_key="plank_choice",
                number_options=[1, 2],
                number_labels={1: "Push an adjacent enemy hero", 2: "Defeat an adjacent minion"},
                is_mandatory=True,
            ),
            # ---- Branch A: push an adjacent enemy hero up to 4.
            CheckContextConditionStep(
                input_key="plank_choice", operator="==", threshold=1, output_key="chose_push"
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Push which adjacent enemy hero?",
                output_key="plank_victim",
                is_mandatory=True,
                active_if_key="chose_push",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            RecordHexStep(
                unit_key="plank_victim", output_key="plank_before", active_if_key="plank_victim"
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Push how far?",
                output_key="push_dist",
                number_options=[0, 1, 2, 3, 4],
                is_mandatory=True,
                active_if_key="plank_victim",
            ),
            PushUnitStep(
                target_key="plank_victim", distance_key="push_dist", active_if_key="plank_victim"
            ),
            CheckZoneChangeStep(
                unit_key="plank_victim",
                before_hex_key="plank_before",
                output_key="crossed_zone",
            ),
            ForceDiscardOrDefeatStep(victim_key="plank_victim", active_if_key="crossed_zone"),
            # ---- Branch B: defeat an adjacent enemy minion (immune excluded).
            CheckContextConditionStep(
                input_key="plank_choice", operator="==", threshold=2, output_key="chose_defeat"
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Defeat which adjacent minion?",
                output_key="plank_minion",
                is_mandatory=True,
                active_if_key="chose_defeat",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                ],
            ),
            DefeatUnitStep(victim_key="plank_minion"),
        ]


# =============================================================================
# ULTIMATE — Legend of the Skies (passive)
# "The first time each turn after you perform a primary action, you may perform
#  the primary action of a card in the previous turn slot."
#
# Fires on AFTER_PRIMARY_ACTION (once per turn) — NOT on secondary actions. At
# that point the just-resolved card is still current_turn_card (moved to
# played_cards only at FinalizeHeroTurn), so resolved_turn_count still reflects
# PRIOR turns: the previous turn slot is played_cards[resolved_turn_count - 1].
# Does nothing on the first turn of a round.
# =============================================================================


def _previous_slot_card(hero: Hero):
    idx = hero.resolved_turn_count - 1
    if idx < 0 or idx >= len(hero.played_cards):
        return None
    return hero.played_cards[idx]


@register_effect("legend_of_the_skies")
class LegendOfTheSkiesEffect(CardEffect):
    def get_passive_config(self) -> PassiveConfig:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_PRIMARY_ACTION,
            uses_per_turn=1,  # "the first time each turn"
            is_optional=True,
            prompt="Legend of the Skies: perform the primary action of your previous turn slot?",
        )

    def should_offer_passive(
        self, state: GameState, hero: Hero, card: Card, trigger: PassiveTrigger, context: dict
    ) -> bool:
        if trigger != PassiveTrigger.AFTER_PRIMARY_ACTION:
            return False
        return _previous_slot_card(hero) is not None

    def get_passive_steps(
        self, state: GameState, hero: Hero, card: Card, trigger: PassiveTrigger, context: dict
    ) -> list[GameStep]:
        prev = _previous_slot_card(hero)
        if prev is None:
            return []
        return [
            SetContextFlagStep(key="ult_prev_card_id", value=prev.id),
            PerformPrimaryActionStep(card_key="ult_prev_card_id", hero_id=str(hero.id)),
        ]
