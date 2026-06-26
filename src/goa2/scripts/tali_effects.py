"""Tali card effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import (
    CardContainerType,
    CardState,
    MinionType,
    TargetType,
    TokenType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import PassiveTrigger, StatType
from goa2.engine.effects import CardEffect, PassiveConfig, register_effect
from goa2.engine.filters_cards import CardsInContainerFilter
from goa2.engine.filters_hex import ObstacleFilter, RangeFilter
from goa2.engine.filters_units import ExcludeIdentityFilter, TeamFilter, UnitTypeFilter
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    ChooseCardColorStep,
    CreateEffectStep,
    DirectionalMoveUnitsStep,
    DiscardCardStep,
    ForceDiscardByColorStep,
    GameStep,
    MayRepeatNTimesStep,
    PerformPrimaryActionStep,
    PlaceTokenStep,
    RecordTargetStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


_DIRECTION_LABELS = {
    0: "NE",
    1: "E",
    2: "SE",
    3: "SW",
    4: "W",
    5: "NW",
}


def _place_ice_steps(count: int, radius: int) -> list[GameStep]:
    steps: list[GameStep] = []
    for i in range(count):
        hex_key = f"tali_ice_hex_{i}"
        token_key = f"tali_ice_token_{i}"
        steps.extend(
            [
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt="Select a space for an Ice token",
                    output_key=hex_key,
                    is_mandatory=False,
                    active_if_key=f"tali_ice_hex_{i - 1}" if i > 0 else None,
                    filters=[
                        RangeFilter(max_range=radius),
                        ObstacleFilter(is_obstacle=False),
                    ],
                ),
                PlaceTokenStep(
                    token_type=TokenType.ICE,
                    hex_key=hex_key,
                    output_key=token_key,
                    active_if_key=hex_key,
                ),
                CreateEffectStep(
                    effect_type=EffectType.AREA_STAT_MODIFIER,
                    scope=EffectScope(
                        shape=Shape.ADJACENT,
                        affects=AffectsFilter.ENEMY_HEROES,
                    ),
                    origin_id_key=token_key,
                    is_token_effect=True,
                    duration=DurationType.PASSIVE,
                    stat_type=StatType.INITIATIVE,
                    stat_value=-1,
                    active_if_key=token_key,
                ),
            ]
        )
    return steps


def _totem_steps(
    *,
    range_val: int,
    is_immune_to_enemy_actions: bool,
    protected_minion_types: list[MinionType] | None = None,
) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.HEX,
            prompt="Select a space for the Totem token",
            output_key="tali_totem_hex",
            is_mandatory=True,
            filters=[
                RangeFilter(max_range=range_val),
                ObstacleFilter(is_obstacle=False),
            ],
        ),
        PlaceTokenStep(
            token_type=TokenType.TOTEM,
            hex_key="tali_totem_hex",
            output_key="tali_totem_token",
            is_immune_to_enemy_actions=is_immune_to_enemy_actions,
        ),
        CreateEffectStep(
            effect_type=EffectType.MINION_PROTECTION,
            scope=EffectScope(
                shape=Shape.ADJACENT,
                origin_id="",
                affects=AffectsFilter.FRIENDLY_UNITS,
            ),
            origin_id_key="tali_totem_token",
            is_token_effect=True,
            duration=DurationType.PASSIVE,
            protected_minion_types=protected_minion_types or [],
            sacrifice_origin_token=True,
            active_if_key="tali_totem_token",
        ),
    ]


def _directional_shift_steps(prefix: str, radius: int) -> list[GameStep]:
    direction_key = f"{prefix}_direction"
    return [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Choose a direction",
            output_key=direction_key,
            number_options=[0, 1, 2, 3, 4, 5],
            number_labels=_DIRECTION_LABELS,
        ),
        DirectionalMoveUnitsStep(direction_key=direction_key, radius=radius),
    ]


def _adjacent_weapon_attack_steps(damage: int) -> list[GameStep]:
    return [
        AttackSequenceStep(
            damage=damage,
            range_val=1,
            target_filters=[RangeFilter(max_range=1)],
        )
    ]


def _friendly_retrieve_steps(
    *,
    radius: int,
    ally_key: str,
    card_key: str,
) -> list[GameStep]:
    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select a friendly hero with a discarded card",
            output_key=ally_key,
            is_mandatory=False,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="FRIENDLY"),
                RangeFilter(max_range=radius),
                CardsInContainerFilter(container=CardContainerType.DISCARD, min_cards=1),
            ],
        ),
        SelectStep(
            target_type=TargetType.CARD,
            prompt="Select a card to retrieve",
            output_key=card_key,
            context_hero_id_key=ally_key,
            override_player_id_key=ally_key,
            card_container=CardContainerType.DISCARD,
            is_mandatory=True,
            active_if_key=ally_key,
        ),
        RetrieveCardStep(card_key=card_key, hero_key=ally_key, active_if_key=card_key),
    ]


def _spirit_attack_steps(
    *,
    damage: int,
    range_val: int,
    option: int,
    active_key: str,
    target_key: str,
    targets_key: str,
) -> list[GameStep]:
    if option == 1:
        filters = [
            TeamFilter(relation="ENEMY"),
            RangeFilter(max_range=range_val),
            ExcludeIdentityFilter(exclude_keys=[targets_key]),
        ]
        prompt = "Select a unit in range"
    else:
        filters = [
            UnitTypeFilter(unit_type="HERO"),
            TeamFilter(relation="ENEMY"),
            RangeFilter(max_range=1),
            ExcludeIdentityFilter(exclude_keys=[targets_key]),
        ]
        prompt = "Select an adjacent enemy hero"

    return [
        SelectStep(
            target_type=TargetType.UNIT,
            prompt=prompt,
            output_key=target_key,
            is_mandatory=True,
            active_if_key=active_key,
            filters=filters,
        ),
        AttackSequenceStep(
            damage=damage,
            range_val=range_val if option == 1 else 1,
            is_ranged=option == 1,
            target_id_key=target_key,
            active_if_key=target_key,
        ),
        RecordTargetStep(
            input_key=target_key,
            output_list_key=targets_key,
            active_if_key=target_key,
        ),
    ]


def _spirit_choice_steps(
    *,
    card: Card,
    damage: int,
    range_val: int,
    can_choose_both: bool,
) -> list[GameStep]:
    has_range_option = card.state != CardState.DISCARD
    options = [1, 2] if has_range_option else [2]
    labels = {
        1: "Target a unit in range",
        2: "Target an adjacent enemy hero",
    }

    targets_key = f"{card.id}_targets"
    steps: list[GameStep] = [
        SelectStep(
            target_type=TargetType.NUMBER,
            prompt="Choose Spirit attack mode",
            output_key=f"{card.id}_choice",
            number_options=options,
            number_labels=labels,
        ),
        CheckContextConditionStep(
            input_key=f"{card.id}_choice",
            operator="==",
            threshold=1,
            output_key=f"{card.id}_range_first",
        ),
        CheckContextConditionStep(
            input_key=f"{card.id}_choice",
            operator="==",
            threshold=2,
            output_key=f"{card.id}_adjacent_first",
        ),
        *_spirit_attack_steps(
            damage=damage,
            range_val=range_val,
            option=1,
            active_key=f"{card.id}_range_first",
            target_key=f"{card.id}_range_target",
            targets_key=targets_key,
        ),
        *_spirit_attack_steps(
            damage=damage,
            range_val=range_val,
            option=2,
            active_key=f"{card.id}_adjacent_first",
            target_key=f"{card.id}_adjacent_target",
            targets_key=targets_key,
        ),
    ]

    if can_choose_both and has_range_option:
        steps.extend(
            [
                CheckContextConditionStep(
                    input_key=f"{card.id}_choice",
                    operator="==",
                    threshold=2,
                    output_key=f"{card.id}_range_second",
                ),
                CheckContextConditionStep(
                    input_key=f"{card.id}_choice",
                    operator="==",
                    threshold=1,
                    output_key=f"{card.id}_adjacent_second",
                ),
                MayRepeatNTimesStep(
                    max_repeats=1,
                    prompt="Resolve the other Spirit Bear attack?",
                    steps_template=[
                        *_spirit_attack_steps(
                            damage=damage,
                            range_val=range_val,
                            option=1,
                            active_key=f"{card.id}_range_second",
                            target_key=f"{card.id}_range_second_target",
                            targets_key=targets_key,
                        ),
                        *_spirit_attack_steps(
                            damage=damage,
                            range_val=range_val,
                            option=2,
                            active_key=f"{card.id}_adjacent_second",
                            target_key=f"{card.id}_adjacent_second_target",
                            targets_key=targets_key,
                        ),
                    ],
                ),
            ]
        )

    return steps


class _IceTokenEffect(CardEffect):
    token_count: int = 1

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _place_ice_steps(self.token_count, stats.radius or 0)


@register_effect("glacial_barrier")
class GlacialBarrierEffect(_IceTokenEffect):
    token_count = 1


@register_effect("wall_of_frost")
class WallOfFrostEffect(_IceTokenEffect):
    token_count = 2


@register_effect("pack_ice")
class PackIceEffect(_IceTokenEffect):
    token_count = 3


@register_effect("ancestral_totem")
class AncestralTotemEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _totem_steps(
            range_val=stats.range,
            is_immune_to_enemy_actions=False,
            protected_minion_types=[MinionType.MELEE],
        )


@register_effect("venerated_totem")
class VeneratedTotemEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _totem_steps(
            range_val=stats.range,
            is_immune_to_enemy_actions=True,
        )


class _DirectionalShiftEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps = _directional_shift_steps(card.id, stats.radius or 0)
        if card.id == "blizzard" and card.state == CardState.DISCARD:
            # "End of turn: May repeat once." Defer the optional repeat to a
            # THIS_TURN delayed trigger so the second shift resolves against the
            # end-of-turn board state, not inline during this resolution.
            steps.append(
                CreateEffectStep(
                    effect_type=EffectType.DELAYED_TRIGGER,
                    duration=DurationType.THIS_TURN,
                    scope=EffectScope(shape=Shape.POINT),
                    is_active=True,
                    finishing_steps=[
                        MayRepeatNTimesStep(
                            max_repeats=1,
                            prompt="Repeat Blizzard?",
                            steps_template=_directional_shift_steps(
                                f"{card.id}_repeat", stats.radius or 0
                            ),
                        )
                    ],
                )
            )
        return steps


@register_effect("cold_snap")
class ColdSnapEffect(_DirectionalShiftEffect):
    pass


@register_effect("snowstorm")
class SnowstormEffect(_DirectionalShiftEffect):
    pass


@register_effect("blizzard")
class BlizzardEffect(_DirectionalShiftEffect):
    pass


class _WinterWeaponEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        bonus = 0 if card.state == CardState.DISCARD else 3
        return _adjacent_weapon_attack_steps(stats.primary_value + bonus)


@register_effect("winter_dagger")
class WinterDaggerEffect(_WinterWeaponEffect):
    pass


@register_effect("winter_spear")
class WinterSpearEffect(_WinterWeaponEffect):
    pass


@register_effect("winter_scepter")
class WinterScepterEffect(_WinterWeaponEffect):
    pass


@register_effect("spirit_wolf")
class SpiritWolfEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _spirit_choice_steps(
            card=card,
            damage=stats.primary_value,
            range_val=stats.range,
            can_choose_both=False,
        )


@register_effect("spirit_bear")
class SpiritBearEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return _spirit_choice_steps(
            card=card,
            damage=stats.primary_value,
            range_val=stats.range,
            can_choose_both=True,
        )


@register_effect("guardian_spirit")
class GuardianSpiritEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps = _friendly_retrieve_steps(
            radius=stats.radius or 0,
            ally_key="guardian_spirit_ally",
            card_key="guardian_spirit_ally_card",
        )
        if card.state == CardState.DISCARD:
            steps.extend(
                [
                    SetContextFlagStep(key="guardian_spirit_self_card", value=card.id),
                    RetrieveCardStep(card_key="guardian_spirit_self_card"),
                ]
            )
        return steps


@register_effect("warrior_spirit")
class WarriorSpiritEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        steps = _friendly_retrieve_steps(
            radius=stats.radius or 0,
            ally_key="warrior_spirit_ally",
            card_key="warrior_spirit_ally_card",
        )
        if card.state == CardState.DISCARD:
            steps.extend(
                [
                    SelectStep(
                        target_type=TargetType.CARD,
                        prompt="Select one of your discarded cards to retrieve",
                        output_key="warrior_spirit_self_card",
                        card_container=CardContainerType.DISCARD,
                        is_mandatory=False,
                    ),
                    RetrieveCardStep(
                        card_key="warrior_spirit_self_card",
                        active_if_key="warrior_spirit_self_card",
                    ),
                ]
            )
        return steps


@register_effect("commune_with_spirits")
class CommuneWithSpiritsEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select a friendly hero to name a color",
                output_key="commune_hero",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="FRIENDLY"),
                ],
            ),
            ChooseCardColorStep(
                output_key="commune_color",
                player_id_key="commune_hero",
                prompt="Name a card color",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                prompt="You may discard a card of the named color",
                output_key="commune_discard_card",
                card_container=CardContainerType.HAND,
                card_color_key="commune_color",
                is_mandatory=False,
            ),
            # The discard step intentionally runs only when Tali selected a card;
            # the perform selection below can still use an already-discarded card.
            DiscardCardStep(
                card_key="commune_discard_card",
                hero_id=str(hero.id),
                active_if_key="commune_discard_card",
            ),
            SelectStep(
                target_type=TargetType.CARD,
                prompt="Select a discarded card of the named color to perform",
                output_key="commune_perform_card",
                card_container=CardContainerType.DISCARD,
                card_color_key="commune_color",
            ),
            PerformPrimaryActionStep(
                card_key="commune_perform_card",
                hero_id=str(hero.id),
                active_if_key="commune_perform_card",
            ),
        ]


@register_effect("ice_blast")
class IceBlastEffect(CardEffect):
    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return [
            AttackSequenceStep(
                damage=stats.primary_value,
                range_val=1,
                target_filters=[RangeFilter(max_range=1)],
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select another enemy hero to discard the matching color",
                output_key="ice_blast_discard_hero",
                is_mandatory=False,
                active_if_key="defense_card_color",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=stats.radius or 0),
                    ExcludeIdentityFilter(exclude_keys=["victim_id"]),
                ],
            ),
            ForceDiscardByColorStep(
                victim_key="ice_blast_discard_hero",
                color_key="defense_card_color",
                active_if_key="ice_blast_discard_hero",
            ),
        ]


@register_effect("reign_of_winter")
class ReignOfWinterEffect(CardEffect):
    def get_passive_config(self) -> PassiveConfig | None:
        return PassiveConfig(
            trigger=PassiveTrigger.AFTER_ATTACK,
            uses_per_turn=0,
            is_optional=False,
        )

    def should_offer_passive(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> bool:
        if trigger != PassiveTrigger.AFTER_ATTACK:
            return False
        if context.get("attack_card_id") != "ice_blast":
            return False
        if context.get("block_succeeded") is not False:
            return False

        target_id = context.get("last_combat_target")
        if not target_id:
            return False
        # Only a genuine defeat counts. A totem save does NOT defeat the minion
        # (no signal), but a card-discard save (Brogan) DOES — the minion is
        # "defeated but not removed" — so key off the defeat signal, not whether
        # the minion is still on the board.
        if context.get("last_defeated_minion_id") != target_id:
            return False
        target = state.get_unit(target_id)
        return target is not None and hasattr(target, "value")

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict,
    ) -> list[GameStep]:
        if trigger != PassiveTrigger.AFTER_ATTACK:
            return []
        return [
            ChooseCardColorStep(
                output_key="reign_color",
                prompt="Choose a color for Reign of Winter",
            ),
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select an enemy hero in radius",
                output_key="reign_victim",
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=card.radius_value or 0),
                ],
            ),
            ForceDiscardByColorStep(
                victim_key="reign_victim",
                color_key="reign_color",
                active_if_key="reign_victim",
            ),
        ]
