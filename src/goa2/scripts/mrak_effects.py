"""Mrak card effects.

Mrak is a Rock-token / terrain-adjacency controller, structurally close to Wuk
(`src/goa2/scripts/wuk_effects.py`). Rock tokens (TokenType.ROCK) are standard
obstacles: supply 3, removed at end of round. The board edge counts as terrain.
See docs/superpowers/specs (Mrak) and the project memory for locked decisions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import CardContainerType, TargetType, TokenType
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_composite import CountMatchFilter, OrFilter
from goa2.engine.filters_geometry import (
    FarthestEmptyAdjacentFilter,
    InStraightLineFilter,
    MaxEmptySpacesInLineFilter,
    SameDirectionFromOriginFilter,
    StraightLinePathFilter,
)
from goa2.engine.filters_hex import AdjacentToTerrainFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import (
    ExcludeIdentityFilter,
    TeamFilter,
    TokenTypeFilter,
    UnitTypeFilter,
)
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardOrDefeatStep,
    GameStep,
    MayRepeatOnceStep,
    MoveSequenceStep,
    MoveUnitStep,
    OfferRockUltimateStep,
    PlaceTokenBatchStep,
    PlaceTokensInLineStep,
    PlaceTokenStep,
    PushUnitStep,
    RecordHexStep,
    RetrieveCardStep,
    SelectStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


def _adjacent_to_rock_filter() -> CountMatchFilter:
    """Candidate (unit or hex) passes if at least one Rock token sits adjacent."""
    return CountMatchFilter(
        include_tokens=True,
        min_count=1,
        sub_filters=[
            TokenTypeFilter(token_type=TokenType.ROCK),
            RangeFilter(max_range=1, origin_hex_key=CountMatchFilter.ORIGIN_HEX_KEY),
        ],
    )


def _adjacent_to_terrain_or_rock() -> OrFilter:
    """ "adjacent to terrain, or to a Rock token" — terrain includes the board edge."""
    return OrFilter(filters=[AdjacentToTerrainFilter(), _adjacent_to_rock_filter()])


# ---------------------------------------------------------------------------
# Seismic Slam / Seismic Assault / Epicenter — "An enemy hero in radius
# adjacent to terrain, or to a Rock token, discards a card, or is defeated.
# [Epicenter: May repeat once on a different target.]"
# ---------------------------------------------------------------------------
def _seismic_select(
    output_key: str, radius: int, *, exclude: list[str] | None = None
) -> SelectStep:
    filters: list = [
        UnitTypeFilter(unit_type="HERO"),
        TeamFilter(relation="ENEMY"),
        RangeFilter(max_range=radius),
        _adjacent_to_terrain_or_rock(),
    ]
    if exclude:
        filters.append(ExcludeIdentityFilter(exclude_keys=exclude))
    return SelectStep(
        target_type=TargetType.UNIT,
        prompt="An enemy hero in radius adjacent to terrain or a Rock token",
        output_key=output_key,
        is_mandatory=exclude is None,  # base target mandatory; the repeat is optional
        filters=filters,
    )


class _SeismicEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        return [
            _seismic_select("seismic_victim", radius),
            ForceDiscardOrDefeatStep(victim_key="seismic_victim"),
        ]


@register_effect("seismic_slam")
class SeismicSlamEffect(_SeismicEffect):
    pass


@register_effect("seismic_assault")
class SeismicAssaultEffect(_SeismicEffect):
    pass


@register_effect("epicenter")
class EpicenterEffect(_SeismicEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        base = super().build_steps(state, hero, card, stats)
        repeat_template = [
            _seismic_select("seismic_victim_2", radius, exclude=["seismic_victim"]),
            ForceDiscardOrDefeatStep(
                victim_key="seismic_victim_2", active_if_key="seismic_victim_2"
            ),
        ]
        return [*base, MayRepeatOnceStep(steps_template=repeat_template)]


# ---------------------------------------------------------------------------
# Treacherous Ground / Rockslide / Avalanche — "You may move a unit in range 1
# space to a space adjacent to terrain, or a Rock token. [Avalanche: repeat once]"
# ---------------------------------------------------------------------------
def _rockslide_steps(range_val: int, unit_key: str, dest_key: str) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="You may move a unit in range",
            output_key=unit_key,
            is_mandatory=False,
            filters=[RangeFilter(max_range=range_val)],
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Move it 1 space to a space adjacent to terrain or a Rock token",
            output_key=dest_key,
            is_mandatory=False,
            active_if_key=unit_key,
            filters=[
                RangeFilter(max_range=1, origin_key=unit_key),
                ObstacleFilter(is_obstacle=False),
                _adjacent_to_terrain_or_rock(),
            ],
        ),
        MoveUnitStep(
            unit_key=unit_key,
            destination_key=dest_key,
            is_movement_action=False,
            active_if_key=dest_key,
        ),
    ]


class _RockslideEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _rockslide_steps(stats.range or 0, "rockslide_unit", "rockslide_dest")


@register_effect("treacherous_ground")
class TreacherousGroundEffect(_RockslideEffect):
    pass


@register_effect("rockslide")
class RockslideEffect(_RockslideEffect):
    pass


@register_effect("avalanche")
class AvalancheEffect(_RockslideEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        range_val = stats.range or 0
        base = _rockslide_steps(range_val, "rockslide_unit", "rockslide_dest")
        repeat = _rockslide_steps(range_val, "rockslide_unit_2", "rockslide_dest_2")
        return [*base, MayRepeatOnceStep(steps_template=repeat)]


# ---------------------------------------------------------------------------
# Stomping Step / Ground Shaker — "Move a unit in radius which is adjacent to
# terrain, or to a Rock token, 1 space. Place a Rock token in the space it
# occupied. [Ground Shaker: May repeat once on a different target.]"
# ---------------------------------------------------------------------------
def _stomping_steps(
    radius: int, unit_key: str, dest_key: str, vacated_key: str, *, exclude: list[str] | None = None
) -> list[GameStep]:
    unit_filters: list = [RangeFilter(max_range=radius), _adjacent_to_terrain_or_rock()]
    if exclude:
        unit_filters.append(ExcludeIdentityFilter(exclude_keys=exclude))
    mandatory = exclude is None  # base move is mandatory; the repeat is optional
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Move a unit in radius adjacent to terrain or a Rock token",
            output_key=unit_key,
            is_mandatory=mandatory,
            filters=unit_filters,
        ),
        RecordHexStep(unit_key=unit_key, output_key=vacated_key),
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Move it 1 space",
            output_key=dest_key,
            is_mandatory=mandatory,
            active_if_key=unit_key,
            filters=[
                RangeFilter(max_range=1, origin_key=unit_key),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        MoveUnitStep(
            unit_key=unit_key,
            destination_key=dest_key,
            is_movement_action=False,
            active_if_key=dest_key,
        ),
        # Rock fills the vacated space (now empty after the move).
        PlaceTokenStep(token_type=TokenType.ROCK, hex_key=vacated_key, active_if_key=dest_key),
        # Ultimate fires per placement group (so Ground Shaker can offer twice).
        OfferRockUltimateStep(rock_hex_keys=[vacated_key]),
    ]


@register_effect("stomping_step")
class StompingStepEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _stomping_steps(stats.radius or 0, "stomp_unit", "stomp_dest", "stomp_vacated")


@register_effect("ground_shaker")
class GroundShakerEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        base = _stomping_steps(radius, "stomp_unit", "stomp_dest", "stomp_vacated")
        repeat = _stomping_steps(
            radius, "stomp_unit_2", "stomp_dest_2", "stomp_vacated_2", exclude=["stomp_unit"]
        )
        return [*base, MayRepeatOnceStep(steps_template=repeat)]


# ---------------------------------------------------------------------------
# Rolling Stone / Strolling Stone — "Move any number of spaces in a straight
# line, ignoring obstacles, without moving through more than N empty spaces."
# Only empty interior hexes count toward the budget (start/destination never).
# ---------------------------------------------------------------------------
def _rolling_steps(hero_id: str, max_empty: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Move any number of spaces in a straight line, ignoring obstacles",
            output_key="rolling_dest",
            is_mandatory=False,
            filters=[
                RangeFilter(min_range=1, max_range=99),
                InStraightLineFilter(origin_id=hero_id),
                StraightLinePathFilter(origin_id=hero_id, pass_through_obstacles=True),
                ObstacleFilter(is_obstacle=False),
                MaxEmptySpacesInLineFilter(origin_id=hero_id, max_empty=max_empty),
            ],
        ),
        MoveUnitStep(
            unit_id=hero_id,
            destination_key="rolling_dest",
            range_val=99,
            pass_through_obstacles=True,
            is_movement_action=False,
            active_if_key="rolling_dest",
        ),
    ]


@register_effect("rolling_stone")
class RollingStoneEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _rolling_steps(str(hero.id), max_empty=1)


@register_effect("strolling_stone")
class StrollingStoneEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _rolling_steps(str(hero.id), max_empty=2)


# ---------------------------------------------------------------------------
# Boulder Rush / Blitz / dozer — "Push a token, or an enemy unit, adjacent to
# you 1..N spaces, ignoring obstacles; you may move up to N spaces in the
# direction of the push, ignoring obstacles."
# ---------------------------------------------------------------------------
def _boulder_steps(hero_id: str, max_n: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Push a token or an adjacent enemy unit",
            output_key="boulder_target",
            is_mandatory=True,
            filters=[
                RangeFilter(max_range=1),
                OrFilter(filters=[UnitTypeFilter(unit_type="TOKEN"), TeamFilter(relation="ENEMY")]),
            ],
        ),
        # Record the target's original hex to fix the push direction for the follow-move.
        RecordHexStep(unit_key="boulder_target", output_key="boulder_target_origin"),
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Push how many spaces?",
            output_key="boulder_push_dist",
            number_options=list(range(1, max_n + 1)),
        ),
        PushUnitStep(
            target_key="boulder_target",
            distance_key="boulder_push_dist",
            ignore_obstacles=True,
        ),
        SelectStep(
            target_type=TargetType.HEX,
            prompt=f"You may move up to {max_n} spaces in the direction of the push",
            output_key="boulder_follow_dest",
            is_mandatory=False,
            filters=[
                RangeFilter(min_range=1, max_range=max_n),
                SameDirectionFromOriginFilter(
                    origin_id=hero_id, reference_key="boulder_target_origin"
                ),
                StraightLinePathFilter(origin_id=hero_id, pass_through_obstacles=True),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        MoveUnitStep(
            unit_id=hero_id,
            destination_key="boulder_follow_dest",
            range_val=99,
            pass_through_obstacles=True,
            is_movement_action=False,
            active_if_key="boulder_follow_dest",
        ),
    ]


@register_effect("boulder_rush")
class BoulderRushEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _boulder_steps(str(hero.id), max_n=2)


@register_effect("boulder_blitz")
class BoulderBlitzEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _boulder_steps(str(hero.id), max_n=3)


@register_effect("boulderdozer")
class BoulderdozerEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _boulder_steps(str(hero.id), max_n=4)


# ---------------------------------------------------------------------------
# Stone Grip (Silver) — "Place exactly 3 Rock tokens into empty spaces adjacent
# to an enemy hero in range, and as far away from you as possible."
# Place 3 or none: gate on >=3 empty adjacent hexes, then 3 sequential selects
# each offering only the current farthest-from-you empty hex(es).
# ---------------------------------------------------------------------------
@register_effect("stone_grip")
class StoneGripEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        hero_id = str(hero.id)
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target an enemy hero in range",
                output_key="grip_hero",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range or 0),
                ],
            ),
            # "exactly 3 or none": the batch's all-or-nothing feasibility
            # precheck (which also counts hexes the forced supply removals
            # would free) replaces the old empty-neighbour count gate.
            PlaceTokenBatchStep(
                token_type=TokenType.ROCK,
                count=3,
                key_prefix="grip",
                slot_filters=[
                    [
                        FarthestEmptyAdjacentFilter(
                            origin_id=hero_id,
                            anchor_key="grip_hero",
                            occupied_hex_keys=[f"grip_hex_{j}" for j in range(i)],
                        )
                    ]
                    for i in range(3)
                ],
                is_mandatory=False,
            ),
            # Ultimate: after this single placement batch (all 3 rocks),
            # affected enemy heroes discard. key_prefix="grip" makes the batch
            # write the same grip_hex_i keys the offer reads.
            OfferRockUltimateStep(rock_hex_keys=["grip_hex_0", "grip_hex_1", "grip_hex_2"]),
        ]


# ---------------------------------------------------------------------------
# Fissure (Gold) — Attack 4 adjacent; "After the attack: Place a Rock token in
# each of the first three empty spaces in the straight line from you in the
# direction of the attack."
# ---------------------------------------------------------------------------
@register_effect("fissure")
class FissureEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        hero_id = str(hero.id)
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Target a unit adjacent to you",
                output_key="fissure_target",
                is_mandatory=True,
                filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
            ),
            # Record the target's hex before the attack fixes the line direction
            # (the target may be defeated/displaced by the attack).
            RecordHexStep(unit_key="fissure_target", output_key="fissure_dir_ref"),
            AttackSequenceStep(
                damage=stats.primary_value, range_val=1, target_id_key="fissure_target"
            ),
            PlaceTokensInLineStep(
                token_type=TokenType.ROCK,
                origin_id=hero_id,
                direction_ref_key="fissure_dir_ref",
                count=3,
                output_key="fissure_rock_hexes",
            ),
            OfferRockUltimateStep(rock_hexes_key="fissure_rock_hexes"),
        ]


# ---------------------------------------------------------------------------
# Stone Carapace / Rock Solid — primary Move 4 that activates a this-round
# discard-shield. "This round: If you would discard a card from your hand, you
# may discard this card instead; you may discard this card to perform its
# defense action, as if it was in your hand." Rock Solid additionally lets you
# retrieve a discarded card on play.
#
# The shield is a card-bound THIS_ROUND DISCARD_SHIELD effect (source_card_id
# auto-bound from context["current_card_id"]). The discard/reaction systems
# consult active shields so the played card behaves as if held this round.
# ---------------------------------------------------------------------------
@register_effect("stone_carapace")
class StoneCarapaceEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            MoveSequenceStep(unit_id=str(hero.id), range_val=stats.primary_value),
            CreateEffectStep(
                effect_type=EffectType.DISCARD_SHIELD,
                scope=EffectScope(shape=Shape.POINT, origin_id=str(hero.id)),
                duration=DurationType.THIS_ROUND,
                is_active=True,
            ),
        ]


@register_effect("rock_solid")
class RockSolidEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            MoveSequenceStep(unit_id=str(hero.id), range_val=stats.primary_value),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="You may retrieve a discarded card",
                output_key="rs_retrieve_card",
                is_mandatory=False,
            ),
            RetrieveCardStep(card_key="rs_retrieve_card", active_if_key="rs_retrieve_card"),
            CreateEffectStep(
                effect_type=EffectType.DISCARD_SHIELD,
                scope=EffectScope(shape=Shape.POINT, origin_id=str(hero.id)),
                duration=DurationType.THIS_ROUND,
                is_active=True,
            ),
        ]
