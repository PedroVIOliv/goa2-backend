"""Card effects for Cordelia."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import (
    ActionType,
    CardContainerType,
    PassiveTrigger,
    StatType,
    TargetType,
)
from goa2.domain.types import UnitID
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.filters_cards import CardsInContainerFilter
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
    CollectUnitsStep,
    CreateEffectStep,
    DiscardCardStep,
    ForEachStep,
    GainCoinsStep,
    GameStep,
    LoseCoinsStep,
    MoveUnitStep,
    PlaceUnitStep,
    PushUnitStep,
    RetrieveCardStep,
    RevealHandCardStep,
    SelectStep,
    SetActorStep,
    SetContextFlagStep,
)
from goa2.engine.topology import topology_distance

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


# -----------------------------------------------------------------------------
# Broom family
# -----------------------------------------------------------------------------


class _BroomEffect(CardEffect):
    basic_bonus: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=False,
            ),
            CreateEffectStep(
                effect_type=EffectType.BASIC_ACTION_STAT_BONUS,
                scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.SELF),
                duration=DurationType.THIS_ROUND,
                stat_value=self.basic_bonus,
                is_active=True,
            ),
        ]


@register_effect("broom_for_improvement")
class BroomForImprovementEffect(_BroomEffect):
    basic_bonus = 1


@register_effect("broomstick_beatdown")
class BroomstickBeatdownEffect(_BroomEffect):
    basic_bonus = 2


@register_effect("this_is_my_broomstick")
class ThisIsMyBroomstickEffect(_BroomEffect):
    basic_bonus = 3


# -----------------------------------------------------------------------------
# Collateral Misfortune / Fatal Bonds
# -----------------------------------------------------------------------------


class _CollateralEffect(CardEffect):
    allow_both: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt=f"Choose which attack to resolve {'first' if self.allow_both else ''}",
                output_key="cordelia_bonds_mode",
                number_options=[1, 2],
                number_labels={
                    1: "Target a unit adjacent to Cordelia",
                    2: "Target a unit in range adjacent to an enemy hero",
                },
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="cordelia_bonds_mode",
                operator="==",
                threshold=1,
                output_key="cordelia_bonds_adjacent_first",
            ),
            CheckContextConditionStep(
                input_key="cordelia_bonds_mode",
                operator="==",
                threshold=2,
                output_key="cordelia_bonds_linked_first",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=True,
                active_if_key="cordelia_bonds_adjacent_first",
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=stats.range,
                is_ranged=True,
                target_filters=[AdjacencyFilter(target_tags=["ENEMY", "HERO"])],
                active_if_key="cordelia_bonds_linked_first",
            ),
        ]
        if not self.allow_both:
            return steps

        # Fatal Bonds may use the other bullet after the first attack. The
        # second target is optional, different, and re-evaluated after combat.
        steps.extend(
            [
                CheckContextConditionStep(
                    input_key="cordelia_bonds_mode",
                    operator="==",
                    threshold=1,
                    output_key="cordelia_bonds_adjacent_was_first",
                ),
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="You may choose a different target in range adjacent to an enemy hero",
                    output_key="cordelia_bonds_second_linked",
                    filters=[
                        TeamFilter(relation="ENEMY"),
                        RangeFilter(max_range=stats.range),
                        AdjacencyFilter(target_tags=["ENEMY", "HERO"]),
                        ExcludeIdentityFilter(
                            exclude_self=False,
                            exclude_keys=["victim_id"],
                        ),
                    ],
                    is_mandatory=False,
                    active_if_key="cordelia_bonds_adjacent_was_first",
                ),
                AttackSequenceStep(
                    damage=stats.primary_value,
                    range_val=stats.range,
                    is_ranged=True,
                    target_id_key="cordelia_bonds_second_linked",
                    active_if_key="cordelia_bonds_second_linked",
                ),
                CheckContextConditionStep(
                    input_key="cordelia_bonds_mode",
                    operator="==",
                    threshold=2,
                    output_key="cordelia_bonds_linked_was_first",
                ),
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="You may choose a different target adjacent to Cordelia",
                    output_key="cordelia_bonds_second_adjacent",
                    filters=[
                        TeamFilter(relation="ENEMY"),
                        RangeFilter(min_range=1, max_range=1),
                        ExcludeIdentityFilter(
                            exclude_self=False,
                            exclude_keys=["victim_id"],
                        ),
                    ],
                    is_mandatory=False,
                    active_if_key="cordelia_bonds_linked_was_first",
                ),
                AttackSequenceStep(
                    damage=stats.primary_value,
                    range_val=1,
                    is_ranged=True,
                    target_id_key="cordelia_bonds_second_adjacent",
                    active_if_key="cordelia_bonds_second_adjacent",
                ),
            ]
        )
        return steps


@register_effect("collateral_misfortune")
class CollateralMisfortuneEffect(_CollateralEffect):
    pass


@register_effect("fatal_bonds")
class FatalBondsEffect(_CollateralEffect):
    allow_both = True


# -----------------------------------------------------------------------------
# Healing Spores / Fungal Favor / Toxic Tranquility
# -----------------------------------------------------------------------------


def _retrieval_steps(radius: int) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select a friendly hero in radius who may retrieve a discarded card",
            output_key="cordelia_retrieve_hero",
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=radius),
                CardsInContainerFilter(
                    container=CardContainerType.DISCARD,
                    min_cards=1,
                ),
            ],
            is_mandatory=True,
        ),
        SelectStep(
            target_type=TargetType.CARD,
            card_container=CardContainerType.DISCARD,
            context_hero_id_key="cordelia_retrieve_hero",
            override_player_id_key="cordelia_retrieve_hero",
            prompt="You may retrieve one of your discarded cards",
            output_key="cordelia_retrieve_card",
            is_mandatory=False,
            active_if_key="cordelia_retrieve_hero",
        ),
        RetrieveCardStep(
            card_key="cordelia_retrieve_card",
            hero_key="cordelia_retrieve_hero",
            active_if_key="cordelia_retrieve_card",
        ),
    ]


class _HealingSporesEffect(CardEffect):
    all_enemies: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        radius = stats.radius or 0
        steps = _retrieval_steps(radius)
        if self.all_enemies:
            steps.extend(
                [
                    CollectUnitsStep(
                        filters=[
                            UnitTypeFilter(unit_type="HERO"),
                            TeamFilter(relation="ENEMY"),
                            RangeFilter(max_range=radius),
                        ],
                        output_key="cordelia_coin_victims",
                        active_if_key="cordelia_retrieve_card",
                    ),
                    ForEachStep(
                        list_key="cordelia_coin_victims",
                        item_key="cordelia_coin_victim",
                        steps_template=[LoseCoinsStep(victim_key="cordelia_coin_victim")],
                    ),
                ]
            )
        else:
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.UNIT,
                        prompt="Select an enemy hero in radius to lose 1 coin",
                        output_key="cordelia_coin_victim",
                        filters=[
                            UnitTypeFilter(unit_type="HERO"),
                            TeamFilter(relation="ENEMY"),
                            RangeFilter(max_range=radius),
                        ],
                        is_mandatory=True,
                        active_if_key="cordelia_retrieve_card",
                    ),
                    LoseCoinsStep(
                        victim_key="cordelia_coin_victim",
                        active_if_key="cordelia_coin_victim",
                    ),
                ]
            )
        return steps


@register_effect("healing_spores")
class HealingSporesEffect(_HealingSporesEffect):
    pass


@register_effect("fungal_favor")
class FungalFavorEffect(_HealingSporesEffect):
    pass


@register_effect("toxic_tranquility")
class ToxicTranquilityEffect(_HealingSporesEffect):
    all_enemies = True


# -----------------------------------------------------------------------------
# Vile Vial / Potion Explosion
# -----------------------------------------------------------------------------


class _VileVialEffect(CardEffect):
    discard_below: int = 2

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in radius",
                output_key="cordelia_reveal_target",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 0),
                    CardsInContainerFilter(
                        container=CardContainerType.HAND,
                        min_cards=1,
                    ),
                ],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.HAND,
                context_hero_id_key="cordelia_reveal_target",
                override_player_id_key="cordelia_reveal_target",
                prompt="Choose a card from your hand to reveal faceup",
                output_key="cordelia_revealed_card",
                is_mandatory=True,
                active_if_key="cordelia_reveal_target",
            ),
            SetContextFlagStep(key="cordelia_id", value=str(hero.id)),
            RevealHandCardStep(
                owner_key="cordelia_reveal_target",
                card_key="cordelia_revealed_card",
                tier_value_key="cordelia_revealed_tier",
            ),
            GainCoinsStep(
                hero_key="cordelia_id",
                amount_key="cordelia_revealed_tier",
            ),
            CheckContextConditionStep(
                input_key="cordelia_revealed_tier",
                operator="<",
                threshold=self.discard_below,
                output_key="cordelia_discard_revealed",
            ),
            DiscardCardStep(
                card_key="cordelia_revealed_card",
                hero_key="cordelia_reveal_target",
                source=CardContainerType.HAND,
                active_if_key="cordelia_discard_revealed",
            ),
        ]


@register_effect("vile_vial")
class VileVialEffect(_VileVialEffect):
    discard_below = 2


@register_effect("potion_explosion")
class PotionExplosionEffect(_VileVialEffect):
    discard_below = 3


# -----------------------------------------------------------------------------
# Charmed Step / Candy Trail / Enchanted Path
# -----------------------------------------------------------------------------


class _CharmedStepEffect(CardEffect):
    choose_push: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in range",
                output_key="cordelia_path_target",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                ],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select an empty space adjacent to that hero",
                output_key="cordelia_path_destination",
                filters=[
                    RangeFilter(
                        min_range=1,
                        max_range=1,
                        origin_key="cordelia_path_target",
                    ),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=True,
            ),
            PlaceUnitStep(
                unit_id=str(hero.id),
                destination_key="cordelia_path_destination",
            ),
        ]
        if self.choose_push:
            steps.append(
                SelectStep(
                    target_type=TargetType.NUMBER,
                    prompt="Choose how far to push that hero",
                    output_key="cordelia_path_push",
                    number_options=[1, 2],
                    number_labels={1: "1 space", 2: "2 spaces"},
                    is_mandatory=True,
                )
            )
            steps.append(
                PushUnitStep(
                    target_key="cordelia_path_target",
                    distance_key="cordelia_path_push",
                )
            )
        else:
            steps.append(PushUnitStep(target_key="cordelia_path_target", distance=1))
        return steps


@register_effect("charmed_step")
class CharmedStepEffect(_CharmedStepEffect):
    pass


@register_effect("candy_trail")
class CandyTrailEffect(_CharmedStepEffect):
    pass


@register_effect("enchanted_path")
class EnchantedPathEffect(_CharmedStepEffect):
    choose_push = True


# -----------------------------------------------------------------------------
# Trouble Brewing / Recipe for Disaster
# -----------------------------------------------------------------------------


class _TroubleBrewingEffect(CardEffect):
    retrieve_basic: bool = False

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps: list[GameStep] = [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy minion in range",
                output_key="cordelia_brew_minion",
                filters=[
                    UnitTypeFilter(unit_type="MINION"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.range),
                ],
                is_mandatory=True,
            ),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select an empty space adjacent to Cordelia",
                output_key="cordelia_brew_destination",
                filters=[
                    RangeFilter(min_range=1, max_range=1, origin_id=str(hero.id)),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=True,
            ),
            PlaceUnitStep(
                unit_key="cordelia_brew_minion",
                destination_key="cordelia_brew_destination",
            ),
        ]
        if self.retrieve_basic:
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.CARD,
                        card_container=CardContainerType.DISCARD,
                        prompt="You may retrieve a discarded basic card",
                        output_key="cordelia_recipe_card",
                        card_is_basic=True,
                        is_mandatory=False,
                    ),
                    RetrieveCardStep(
                        card_key="cordelia_recipe_card",
                        active_if_key="cordelia_recipe_card",
                    ),
                ]
            )
        return steps


@register_effect("trouble_brewing")
class TroubleBrewingEffect(_TroubleBrewingEffect):
    pass


@register_effect("recipe_for_disaster")
class RecipeForDisasterEffect(_TroubleBrewingEffect):
    retrieve_basic = True


# -----------------------------------------------------------------------------
# Bewitch / Jinx
# -----------------------------------------------------------------------------


@register_effect("bewitch")
class BewitchEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an adjacent unit to attack",
                output_key="cordelia_bewitch_target",
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(min_range=1, max_range=1),
                ],
                is_mandatory=True,
            ),
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=str(hero.id),
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                stat_type=StatType.RANGE,
                stat_value=-1,
                apply_stat_value_only_if_result_at_least=1,
                is_active=True,
            ),
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                is_ranged=False,
                target_id_key="cordelia_bewitch_target",
            ),
        ]


@register_effect("jinx")
class JinxEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=str(hero.id),
                    affects=AffectsFilter.ENEMY_HEROES,
                ),
                duration=DurationType.THIS_TURN,
                stat_type=StatType.ATTACK,
                stat_value=-10,
                is_active=True,
                granted_passive_effect_id="jinx",
            )
        ]

    def get_passive_config(self) -> PassiveConfig:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_CARD_DISCARD,
            uses_per_turn=0,
            is_optional=True,
            prompt="Jinx: Move 1 space after discarding a card?",
        )

    def should_offer_passive(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> bool:
        is_active_own_discard = (
            trigger == PassiveTrigger.AFTER_CARD_DISCARD
            and context.get("discarded_card_owner_id") == str(hero.id)
            and any(
                effect.source_card_id == card.id
                and str(effect.source_id) == str(hero.id)
                and effect.is_active
                for effect in state.active_effects
            )
        )
        if not is_active_own_discard:
            return False

        origin = state.get_position(str(hero.id))
        if origin is None:
            return False
        if not state.validator.can_move(
            state,
            str(hero.id),
            1,
            context,
            is_movement_action=False,
        ).allowed:
            return False

        from goa2.engine.rules import find_reachable_hexes

        reachable = find_reachable_hexes(
            board=state.board,
            start=origin,
            max_steps=1,
            state=state,
            actor_id=str(hero.id),
            topology_unit_ids=[str(hero.id)],
        )
        return any(destination != origin for destination in reachable)

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> list[GameStep]:
        if trigger != PassiveTrigger.AFTER_CARD_DISCARD:
            return []
        return [
            SetActorStep(actor_id=str(hero.id), save_key="_cordelia_jinx_saved_actor"),
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Move exactly 1 space",
                output_key="cordelia_jinx_destination",
                filters=[
                    RangeFilter(
                        min_range=1,
                        max_range=1,
                        origin_id=str(hero.id),
                    ),
                    MovementPathFilter(range_val=1, unit_id=str(hero.id)),
                    ObstacleFilter(is_obstacle=False),
                ],
                is_mandatory=True,
            ),
            MoveUnitStep(
                unit_id=str(hero.id),
                destination_key="cordelia_jinx_destination",
                range_val=1,
                is_movement_action=False,
            ),
            SetActorStep(
                actor_key="_cordelia_jinx_saved_actor",
                save_key="_cordelia_jinx_discard_actor",
            ),
        ]


# -----------------------------------------------------------------------------
# Witching Hour
# -----------------------------------------------------------------------------


@register_effect("witching_hour")
class WitchingHourEffect(CardEffect):
    def get_action_prevention_reason(
        self,
        state: GameState,
        source_hero: Hero,
        source_card: Card,
        actor_id: str,
        action_type: ActionType,
        action_card: Card | None,
    ) -> str | None:
        if action_type != ActionType.ATTACK or action_card is None:
            return None

        actor = state.get_unit(UnitID(actor_id))
        source_hex = state.get_position(str(source_hero.id))
        actor_hex = state.get_position(actor_id)
        if (
            actor is None
            or source_hex is None
            or actor_hex is None
            or actor.team == source_hero.team
        ):
            return None

        from goa2.engine.rules import is_immune_to_actor
        from goa2.engine.stats import compute_card_stats, get_computed_stat

        if is_immune_to_actor(actor, state, actor_id=str(source_hero.id)):
            return None

        radius = compute_card_stats(state, source_hero.id, source_card).radius or 0
        if topology_distance(source_hex, actor_hex, state, unit_ids=[actor_id]) > radius:
            return None

        base_attack: int
        if action_card.current_primary_action == ActionType.ATTACK:
            primary_attack = action_card.current_primary_action_value
            base_attack = primary_attack if primary_attack is not None else 0
        else:
            secondary_attack = action_card.current_secondary_actions.get(ActionType.ATTACK)
            if secondary_attack is None:
                return None
            base_attack = secondary_attack

        attack = get_computed_stat(
            state,
            UnitID(actor_id),
            StatType.ATTACK,
            base_attack,
            performing_card=action_card,
        )
        if attack < 0:
            return "Witching Hour: Attack value is below zero"
        return None
