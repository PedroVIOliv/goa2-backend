from __future__ import annotations
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    CountStep,
    CreateEffectStep,
    DiscardCardStep,
    ForceDiscardOrDefeatStep,
    ForceDiscardStep,
    GameStep,
    MoveSequenceStep,
    MoveUnitStep,
    PlaceUnitStep,
    PushUnitStep,
    RetrieveCardStep,
    SelectStep,
    SetContextFlagStep,
)
from goa2.engine.filters import (
    ObstacleFilter,
    OrFilter,
    RangeFilter,
    TeamFilter,
    UnitTypeFilter,
)
from goa2.domain.models import (
    TargetType,
    ActionType,
)
from goa2.domain.models.enums import (
    CardContainerType,
)
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import DisplacementType

if TYPE_CHECKING:
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.engine.effects import PassiveConfig
    from goa2.engine.stats import CardStats


# =============================================================================
# TIER I - BLUE: Brutal Jab
# =============================================================================


@register_effect("brutal_jab")
class BrutalJabEffect(CardEffect):
    """
    Card text: "You may move 1 space. Push an enemy unit or a token
    adjacent to you up to 1 space."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Optional move 1 space
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter()
                ],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),

            # 2. Select adjacent enemy unit or token to push
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="TOKEN"),
                    ]),
                ],
            ),
            # 3. Choose push distance (0 or 1)
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-1)",
                output_key="push_distance",
                number_options=[0, 1],
                active_if_key="push_target_id",
            ),
            # 4. Execute push
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
            ),
        ]


# =============================================================================
# TIER II - BLUE: Mighty Punch
# =============================================================================


@register_effect("mighty_punch")
class MightyPunchEffect(CardEffect):
    """
    Card text: "You may move 1 space. Push an enemy unit or a token
    adjacent to you up to 2 spaces."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[
                    RangeFilter(max_range=1),
                    ObstacleFilter()
                ],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="TOKEN"),
                    ]),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-2)",
                output_key="push_distance",
                number_options=[0, 1, 2],
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# TIER III - BLUE: Savage Kick
# =============================================================================


@register_effect("savage_kick")
class SavageKickEffect(CardEffect):
    """
    Card text: "Move up to 2 spaces. Push an enemy unit or a token
    adjacent to you up to 2 spaces."
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # Move up to 2 
            SelectStep(
                target_type=TargetType.HEX,
                prompt="Select a space to move to",
                filters=[
                    RangeFilter(max_range=2),
                    ObstacleFilter()
                ],
                is_mandatory=False,
                output_key="selected_hex",
            ),
            MoveUnitStep(
                is_mandatory=False,
                unit_id=hero.id,
                destination_key="selected_hex",
            ),
            SelectStep(
                target_type=TargetType.UNIT_OR_TOKEN,
                prompt="Select adjacent enemy unit or token to push",
                output_key="push_target_id",
                is_mandatory=False,
                filters=[
                    RangeFilter(max_range=1),
                    OrFilter(filters=[
                        TeamFilter(relation="ENEMY"),
                        UnitTypeFilter(unit_type="TOKEN"),
                    ]),
                ],
            ),
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose push distance (0-2)",
                output_key="push_distance",
                number_options=[0, 1, 2],
                active_if_key="push_target_id",
            ),
            PushUnitStep(
                target_key="push_target_id",
                distance_key="push_distance",
                active_if_key="push_target_id",
                is_mandatory=False,
            ),
        ]


# =============================================================================
# UNTIERED - GOLD: Onslaught
# =============================================================================


@register_effect("onslaught")
class OnslaughtEffect(CardEffect):
    """
    Card text: "Target a unit adjacent to you. After the attack:
    Move into the space it occupied, if able."

    TODO: Needs a step to record the target's hex position BEFORE the attack
    resolves (since the target may be pushed/defeated), then PlaceUnitStep
    into that recorded hex after the attack. Requires either:
    - A new RecordHexStep(unit_key="victim_id", output_key="victim_hex")
    - Or extending AttackSequenceStep to record target position in context

    For now, implements the attack portion only.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select adjacent target
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="victim_id",
                is_mandatory=True,
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # TODO: RecordHexStep(unit_key="victim_id", output_key="victim_hex")
            # 2. Attack using pre-selected target
            AttackSequenceStep(
                damage=stats.primary_value, target_id_key="victim_id", range_val=1
            ),
            # 3. Move into target's former space (optional, "if able")
            # TODO: PlaceUnitStep(unit_id=hero.id, destination_key="victim_hex")
            #       with active_if_key and obstacle check
        ]


# =============================================================================
# TIER II - BLUE: Shield Bash
# =============================================================================


@register_effect("shield_bash")
class ShieldBashEffect(CardEffect):
    """
    Card text: "An enemy hero adjacent to you who has played an attack card
    this turn discards a card, if able."

    TODO: Needs a new filter (PlayedAttackThisTurnFilter) that checks if an
    enemy hero's current_turn_card or played_cards[] has ActionType.ATTACK as primary_action.
    This filter would need to inspect the hero's played_cards or
    current_turn_card for the current turn.

    For now, uses basic adjacent enemy hero selection. The client/engine
    should restrict valid targets to those who played attack cards.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Select adjacent enemy hero (who played attack this turn)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent enemy hero who played an attack card this turn",
                output_key="bash_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                    # TODO: PlayedAttackThisTurnFilter()
                ],
            ),
            # 2. Force discard (if able)
            ForceDiscardStep(victim_key="bash_victim"),
        ]


# =============================================================================
# TIER III - BLUE: Counterattack
# =============================================================================


@register_effect("counterattack")
class CounterattackEffect(CardEffect):
    """
    Card text: "An enemy hero adjacent to you who has played an attack card
    this turn discards a card, or is defeated."

    Same targeting as Shield Bash, but uses ForceDiscardOrDefeatStep.

    TODO: Same PlayedAttackThisTurnFilter needed as Shield Bash.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent enemy hero who played an attack card this turn",
                output_key="counter_victim",
                is_mandatory=False,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=1),
                    # TODO: PlayedAttackThisTurnFilter()
                ],
            ),
            ForceDiscardOrDefeatStep(victim_key="counter_victim"),
        ]


# =============================================================================
# TIER I - RED: Mad Dash
# =============================================================================


@register_effect("mad_dash")
class MadDashEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2 spaces in a straight line to a
    space adjacent to an enemy unit, then target that unit.
    (If you cannot make this move, you cannot attack.)"

    TODO: Needs a StraightLineChargeStep or equivalent that:
    1. Shows valid straight-line destinations exactly N spaces away
    2. Each destination must be adjacent to at least one enemy unit
    3. After moving, auto-selects the adjacent enemy as attack target
       (or lets player choose if multiple adjacent enemies)

    Requires new filters:
    - StraightLineDestinationFilter(distance=N) - hex exactly N in straight line
    - AdjacentToEnemyFilter() - destination must neighbor an enemy unit
    Or a composite StraightLineChargeStep that handles all of this.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement straight-line charge mechanic
        # Placeholder: basic adjacent attack (charge portion not yet implemented)
        return [
            # TODO: StraightLineChargeStep(distance=2, output_target_key="charge_victim")
            AttackSequenceStep(
                damage=stats.primary_value, range_val=1
            ),
        ]


# =============================================================================
# TIER II - RED: Bullrush
# =============================================================================


@register_effect("bullrush")
class BullrushEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2 or 3 spaces in a straight line to a
    space adjacent to an enemy unit, then target that unit."

    TODO: Same StraightLineChargeStep as Mad Dash, but with distance choice (2 or 3).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement straight-line charge with distance choice
        return [
            # TODO: SelectStep(NUMBER, options=[2,3]) → StraightLineChargeStep
            AttackSequenceStep(
                damage=stats.primary_value, range_val=1
            ),
        ]


# =============================================================================
# TIER III - RED: Furious Charge
# =============================================================================


@register_effect("furious_charge")
class FuriousChargeEffect(CardEffect):
    """
    Card text: "Before the attack: Move 2, 3, or 4 spaces in a straight line to
    a space adjacent to an enemy unit, then target that unit."

    TODO: Same StraightLineChargeStep as Mad Dash, but with distance choice (2, 3, or 4).
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement straight-line charge with distance choice
        return [
            # TODO: SelectStep(NUMBER, options=[2,3,4]) → StraightLineChargeStep
            AttackSequenceStep(
                damage=stats.primary_value, range_val=1
            ),
        ]


# =============================================================================
# TIER II - RED: Throwing Axe
# =============================================================================


@register_effect("throwing_axe")
class ThrowingAxeEffect(CardEffect):
    """
    Card text: "Choose one -
    * Target a unit adjacent to you.
    * You may discard a card; if you do, target a unit in range."

    Implementation: Player chooses option 1 (melee) or 2 (ranged).
    Uses CheckContextConditionStep to branch execution.

    TODO: Needs AttackSequenceStep to respect should_skip/active_if_key,
    OR needs two separate SelectSteps writing to the same victim key
    with a single AttackSequenceStep reading the pre-selected target.
    Also for option 2: "you MAY discard" means if they choose option 2
    but skip the discard, they get no attack.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Choose mode
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent, 2 = Discard card to attack in range",
                output_key="attack_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            # 2. Branch flags
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            # 3a. Melee: select adjacent target
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="victim_id",
                is_mandatory=True,
                active_if_key="chose_melee",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 3b. Ranged: discard a card first ("you may" - but choosing option 2 implies intent)
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.HAND,
                prompt="Select a card to discard for ranged attack",
                output_key="discard_for_range",
                is_mandatory=True,
                active_if_key="chose_ranged",
            ),
            DiscardCardStep(
                card_key="discard_for_range",
                hero_id=hero.id,
                active_if_key="chose_ranged",
            ),
            # 3b cont. Ranged: select target in range
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select unit in range to attack",
                output_key="victim_id",
                is_mandatory=True,
                active_if_key="chose_ranged",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # 4. Attack with pre-selected target
            AttackSequenceStep(
                damage=stats.primary_value, target_id_key="victim_id", range_val=stats.range
            ),
        ]


# =============================================================================
# TIER III - RED: Throwing Spear
# =============================================================================


@register_effect("throwing_spear")
class ThrowingSpearEffect(CardEffect):
    """
    Card text: "Choose one -
    * Target a unit adjacent to you.
    * You may discard a card. If you have a card in the discard,
      target a unit in range."

    Similar to Throwing Axe but the discard condition is different:
    Option 2 checks if there's already a card in discard OR you discard one.

    TODO: The "If you have a card in the discard" condition needs a check
    against the hero's discard pile count. The "you may discard" is optional
    but having a discard pile card is required for ranged targeting.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Choose: 1 = Attack adjacent, 2 = Discard a card to attack in range",
                output_key="attack_choice",
                number_options=[1, 2],
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=1,
                output_key="chose_melee",
            ),
            CheckContextConditionStep(
                input_key="attack_choice",
                operator="==",
                threshold=2,
                output_key="chose_ranged",
            ),
            # Melee branch
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select adjacent unit to attack",
                output_key="victim_id",
                is_mandatory=True,
                active_if_key="chose_melee",
                filters=[
                    RangeFilter(max_range=1),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            # Ranged branch: optionally discard, then must have card in discard
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.HAND,
                prompt="You may discard a card (for ranged attack)",
                output_key="discard_for_range",
                is_mandatory=False,
                active_if_key="chose_ranged",
            ),
            DiscardCardStep(
                card_key="discard_for_range",
                hero_id=hero.id,
                active_if_key="discard_for_range",
            ),
            # TODO: Check if hero has at least 1 card in discard pile
            # (may already have one from a previous turn, or just discarded one)
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select unit in range to attack",
                output_key="victim_id",
                is_mandatory=True,
                active_if_key="chose_ranged",
                filters=[
                    RangeFilter(max_range=stats.range),
                    TeamFilter(relation="ENEMY"),
                ],
            ),
            AttackSequenceStep(
                damage=stats.primary_value, target_id_key="victim_id", range_val=stats.range
            ),
        ]


# =============================================================================
# TIER I - GREEN: Shield
# =============================================================================


@register_effect("shield")
class ShieldEffect(CardEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a silver card. If you do, the minion is not removed.
    (The enemy hero still gains the coins for defeating the minion.)"

    TODO: Needs a new MINION_PROTECTION EffectType that:
    1. Creates a round-long triggered effect scoped to friendly minions in radius
    2. When a friendly minion in scope would be defeated, interrupts to ask
       if Brogan wants to discard a silver card
    3. If discarded, cancels the minion removal (but NOT the gold reward)

    This requires deep integration with DefeatUnitStep to check for
    active MINION_PROTECTION effects before removing the minion.
    Requires: new EffectType, new handling in DefeatUnitStep, card color
    filter for the discard choice.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement minion protection effect
        return [
            # Placeholder: creates a delayed trigger as marker
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                is_active=True,
            ),
        ]


# =============================================================================
# TIER II - GREEN: Bolster
# =============================================================================


@register_effect("bolster")
class BolsterEffect(ShieldEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a silver card. If you do, the minion is not removed."

    Same as Shield but at Tier II (stats differ via card definition).
    TODO: Same MINION_PROTECTION infrastructure as Shield.
    """

    pass


# =============================================================================
# TIER III - GREEN: Fortify
# =============================================================================


@register_effect("fortify")
class FortifyEffect(CardEffect):
    """
    Card text: "This round: When any friendly minion in radius is defeated
    you may discard a basic card. If you do, the minion is not removed."

    Same mechanic as Shield/Bolster but allows discarding ANY basic card
    (Gold or Silver) instead of only Silver.
    TODO: Same MINION_PROTECTION infrastructure, with basic card filter.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement with basic card (gold/silver) discard condition
        return [
            CreateEffectStep(
                effect_type=EffectType.DELAYED_TRIGGER,
                duration=DurationType.THIS_ROUND,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                is_active=True,
            ),
        ]


# =============================================================================
# TIER II - GREEN: War Drummer
# =============================================================================


@register_effect("war_drummer")
class WarDrummerEffect(CardEffect):
    """
    Card text: "A friendly hero in range gains 1 coin; if any hero was
    defeated this round, that friendly hero gains 3 coins instead."

    TODO: Needs:
    1. GainCoinsStep(hero_key="target_hero", amount=N) - new step to grant gold
    2. A way to check "any hero was defeated this round" - either a state flag
       or count defeated heroes in the current round
    3. Conditional coin amount (1 vs 3)

    Could be modeled as:
    - CheckHeroDefeatedThisRoundStep(output_key="hero_defeated_this_round")
    - CheckContextConditionStep to set coin amount
    - GainCoinsStep with amount_key from context
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement coin granting
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select friendly hero in range to gain coins",
                output_key="coin_target",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.range),
                ],
                skip_immunity_filter=True,
            ),
            # TODO: CheckHeroDefeatedThisRoundStep(output_key="hero_died")
            # TODO: GainCoinsStep(hero_key="coin_target", amount=1, amount_if_key="hero_died", amount_if=3)
        ]


# =============================================================================
# TIER III - GREEN: Master Skald
# =============================================================================


@register_effect("master_skald")
class MasterSkaldEffect(CardEffect):
    """
    Card text: "A friendly hero in range gains 2 coins; if any hero was
    defeated this round, that friendly hero gains 4 coins instead."

    Same pattern as War Drummer with higher coin amounts.
    TODO: Same GainCoinsStep infrastructure as War Drummer.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        # TODO: Implement coin granting (2 or 4)
        return [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select friendly hero in range to gain coins",
                output_key="coin_target",
                is_mandatory=True,
                filters=[
                    UnitTypeFilter(unit_type="HERO"),
                    TeamFilter(relation="FRIENDLY"),
                    RangeFilter(max_range=stats.range),
                ],
                skip_immunity_filter=True,
            ),
            # TODO: GainCoinsStep(hero_key="coin_target", amount=2, amount_if_key="hero_died", amount_if=4)
        ]


# =============================================================================
# UNTIERED - SILVER: Bulwark
# =============================================================================


@register_effect("bulwark")
class BulwarkEffect(CardEffect):
    """
    Card text: "You may retrieve a discarded card.
    This turn: You and friendly units in radius cannot be moved, pushed,
    swapped or placed by enemy heroes."

    The displacement immunity uses PLACEMENT_PREVENTION with all displacement
    types blocked, targeting self + friendly units in radius.
    """

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return [
            # 1. Optionally retrieve a discarded card
            SelectStep(
                target_type=TargetType.CARD,
                card_container=CardContainerType.DISCARD,
                prompt="Select a discarded card to retrieve (optional)",
                output_key="retrieved_card",
                is_mandatory=False,
            ),
            RetrieveCardStep(
                card_key="retrieved_card",
                active_if_key="retrieved_card",
            ),
            # 2. Create displacement immunity for self + friendlies in radius
            CreateEffectStep(
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(
                    shape=Shape.RADIUS,
                    range=stats.radius or 0,
                    origin_id=hero.id,
                    affects=AffectsFilter.FRIENDLY_UNITS,
                ),
                duration=DurationType.THIS_TURN,
                displacement_blocks=[
                    DisplacementType.MOVE,
                    DisplacementType.PUSH,
                    DisplacementType.SWAP,
                    DisplacementType.PLACE,
                ],
                blocks_enemy_actors=True,
                blocks_friendly_actors=False,
                blocks_self=False,
            ),
        ]


# =============================================================================
# ULTIMATE (Purple/Tier IV) - Passive Ability
# =============================================================================


@register_effect("one_man_army")
class OneManArmyEffect(CardEffect):
    """
    Ultimate (Purple) - Brogan

    Card text: "During minion battle you count as a heavy minion;
    if you would be removed, lose the push instead."

    TODO: This is the most complex effect. Requires deep integration with
    MinionBattleStep to:
    1. Include Brogan as a "heavy minion" when calculating minion battle
    2. When minion battle would remove Brogan (as a minion proxy),
       instead of removing him, the team loses the lane push
    3. Needs a new passive trigger (DURING_MINION_BATTLE) or a special
       flag on the hero that MinionBattleStep checks

    This is an always-active passive (no trigger, no uses_per_turn).
    It modifies the minion battle resolution rules themselves.
    """

    def get_passive_config(self) -> Optional["PassiveConfig"]:
        # TODO: Needs a new PassiveTrigger for minion battle integration
        # or a completely different mechanism (hero flag checked by MinionBattleStep)
        return None

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> List[GameStep]:
        return []
