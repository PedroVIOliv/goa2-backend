from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from goa2.domain.models.enums import ActionType, PassiveTrigger, StatType
from goa2.engine.filters_base import FilterCondition

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats
    from goa2.engine.steps import GameStep


class StatAura(BaseModel):
    """Filter-based always-on stat modifier for passive abilities.

    Uses the existing filter system to count matching units,
    then applies multiplier * count as a stat bonus.
    Range is controlled via RangeFilter in count_filters.

    For flat bonuses, set flat_bonus directly (bypasses count logic).
    Use basic_only and/or action_type_only to restrict when the aura applies.
    """

    stat_type: StatType
    count_filters: list[FilterCondition] = []
    multiplier: int = 1
    flat_bonus: int | None = None
    basic_only: bool = False
    action_type_only: ActionType | None = None


class MovementAura(BaseModel):
    """Data-driven movement rule modification for passive abilities."""

    pass_through_obstacles: bool = False


class PassiveConfig(BaseModel):
    """
    Configuration for a card's passive ability.

    Passive abilities are persistent effects that trigger during specific game events
    (e.g., before attacking, before moving). They differ from active effects which
    only trigger once when the card is played.

    Attributes:
        trigger: When the passive activates (BEFORE_ATTACK, BEFORE_MOVEMENT, etc.)
        uses_per_turn: Maximum uses per turn. -1 means unlimited.
        is_optional: If True, player is prompted "you may". If False, auto-executes.
        prompt: Custom UI prompt for optional passives.
    """

    trigger: PassiveTrigger
    uses_per_turn: int = 1
    is_optional: bool = True
    prompt: str = ""


def _nested_steps(value: Any) -> list[GameStep]:
    """Steps reachable from a model field value (steps, or lists of them)."""
    from goa2.engine.steps import GameStep

    if isinstance(value, GameStep):
        return [value]
    if isinstance(value, (list, tuple)):
        return [step for item in value for step in _nested_steps(item)]
    return []


def bind_effect_cards(steps: list[GameStep], card_id: str) -> list[GameStep]:
    """Attribute every effect these steps create to the card that built them.

    Card linkage cannot be inferred from the execution context: a card that
    re-performs another card's action (Bullet Time, Reload, NebKher's Mind Grip)
    resolves that card's text while the turn context still names the granting
    card, so the effects would bind to the wrong card — and repeats would evade
    the one-instance-per-card rule keyed on it. Build time is the only point
    that reliably knows the card, so the CardEffect API stamps it here.

    Any step declaring a ``source_card_id`` field is stamped — ``CreateEffectStep``
    and the steps that create effects directly (Hanu's ``ScheduleJourneyReturnStep``).
    Steps that already name a card are left alone, and token-bound effects stay
    unbound on purpose: their lifecycle follows the token, not a card.

    The walk is generic over ``model_fields`` rather than a fixed list of step
    types, so nested step containers (``steps_template``, ``finishing_steps``,
    ``new_steps``, and any added later) are covered without maintenance.
    """
    for step in steps:
        # Duck-typed: any step declaring source_card_id opts into binding.
        bindable: Any = step
        if (
            "source_card_id" in type(step).model_fields
            and bindable.source_card_id is None
            and not getattr(step, "is_token_effect", False)
        ):
            bindable.source_card_id = card_id
        for field_name in type(step).model_fields:
            bind_effect_cards(_nested_steps(getattr(step, field_name, None)), card_id)
    return steps


def _defense_stats_unit_id(state: GameState, defender: Hero, context: dict[str, Any]):
    """Board unit whose position drives defense stats.

    The attacked piece from the combat context when it belongs to this
    defender (multi-piece heroes defend with the piece that was hit);
    otherwise the defender itself.
    """
    from goa2.domain.types import BoardEntityID

    defender_board_id = context.get("defender_id")
    if defender_board_id is not None:
        owner = state.get_hero(BoardEntityID(str(defender_board_id)))
        if owner is not None and str(owner.id) == str(defender.id):
            return str(defender_board_id)
    return defender.id


class CardEffect:
    """
    Base class for custom card logic.
    Primary actions on cards delegate their execution to these effects.

    Public API (called by engine):
        get_steps: Steps for primary action on your turn (ATTACK/SKILL/MOVEMENT).
        get_defense_steps: Steps when used as primary DEFENSE in reaction.
        get_on_block_steps: Steps after successful block ('if you do' effects).

    Override in subclasses (stats pre-computed):
        build_steps: Implement primary action logic with pre-computed stats.
        build_defense_steps: Implement defense logic with pre-computed stats.
        build_on_block_steps: Implement on-block logic with pre-computed stats.
    """

    # Capability flag: an active ultimate whose effect sets this lets its hero
    # commit two cards during Planning (Emmitt's Alternative Timelines). Read
    # by engine/phases.py.
    plays_two_cards: bool = False

    # -------------------------------------------------------------------------
    # Public API - Called by engine. Computes stats and delegates to build_*.
    # -------------------------------------------------------------------------

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> list[GameStep]:
        """
        Returns steps for the card's primary action on your turn.

        Computes card stats and delegates to build_steps().
        Override build_steps() in subclasses, not this method.
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, hero.id, card)
        return self.get_steps_with_stats(state, hero, card, stats)

    def get_steps_with_stats(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        """
        Returns steps for the card's primary action, with stats already computed.

        For engine callers that need to compute or adjust stats themselves
        (re-performances, primary movement). Prefer get_steps() otherwise.
        Never call build_steps() directly — it skips the card binding.
        """
        return bind_effect_cards(self.build_steps(state, hero, card, stats), card.id)

    def get_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        context: dict[str, Any],
    ) -> list[GameStep] | None:
        """
        Returns steps when used as primary DEFENSE in reaction.

        Computes card stats and delegates to build_defense_steps().
        Override build_defense_steps() in subclasses, not this method.

        Returns:
            List of steps to execute, or None to fall back to get_steps().
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, _defense_stats_unit_id(state, defender, context), card)
        steps = self.build_defense_steps(state, defender, card, stats, context)
        return None if steps is None else bind_effect_cards(steps, card.id)

    def get_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        context: dict[str, Any],
    ) -> list[GameStep]:
        """
        Returns steps to run after a successful block ('if you do' effects).

        Computes card stats and delegates to build_on_block_steps().
        Override build_on_block_steps() in subclasses, not this method.
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, _defense_stats_unit_id(state, defender, context), card)
        return bind_effect_cards(
            self.build_on_block_steps(state, defender, card, stats, context), card.id
        )

    # -------------------------------------------------------------------------
    # Override these in subclasses - stats are pre-computed
    # -------------------------------------------------------------------------

    def build_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
    ) -> list[GameStep]:
        """
        Returns steps for the card's primary action on your turn.

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            hero: The hero playing the card.
            card: The card being played.
            stats: Pre-computed card stats (attack, defense, range, radius, etc.)

        Returns:
            List of steps to execute.
        """
        return []

    def build_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: dict[str, Any],
    ) -> list[GameStep] | None:
        """
        Returns steps when used as primary DEFENSE in reaction.

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            defender: The hero defending (being attacked).
            card: The defense card being played.
            stats: Pre-computed card stats.
            context: Contains attack information:
                - attack_is_ranged: bool - True if the attack is ranged
                - attacker_id: str - ID of the attacking unit
                - defender_id: str - ID of the defending hero

        Returns:
            List of steps to execute, or None to fall back to build_steps().
        """
        return None

    def build_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        stats: CardStats,
        context: dict[str, Any],
    ) -> list[GameStep]:
        """
        Returns steps to run after a successful block ('if you do' effects).

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            defender: The hero who successfully blocked.
            card: The defense card that was used.
            stats: Pre-computed card stats.
            context: Contains combat result information including block_succeeded.

        Returns:
            List of steps to execute after the block, or empty list.
        """
        return []

    # -------------------------------------------------------------------------
    # Aura methods (always-on stat/movement modifiers)
    # -------------------------------------------------------------------------

    def get_stat_auras(self) -> list[StatAura]:
        """Return always-on stat auras. Counted via filters. Default: none."""
        return []

    def get_movement_aura(self) -> MovementAura | None:
        """Return movement rule modifications. Default: none."""
        return None

    def get_action_prevention_reason(
        self,
        state: GameState,
        source_hero: Hero,
        source_card: Card,
        actor_id: str,
        action_type: ActionType,
        action_card: Card | None,
    ) -> str | None:
        """Return a reason when this active card effect forbids an action.

        This hook is evaluated while action choices are built, before any
        BEFORE_ACTION/BEFORE_ATTACK passives. Most card effects do not restrict
        action availability and inherit the default ``None`` result.
        """
        return None

    # -------------------------------------------------------------------------
    # Passive ability methods (unchanged)
    # -------------------------------------------------------------------------

    def get_passive_config(self) -> PassiveConfig | None:
        """
        Returns passive configuration if this card has a passive ability.

        Passive abilities are persistent effects that trigger during specific game
        events while the card is active (RESOLVED + face-up for regular cards,
        or hero level >= 8 for ultimates).

        Override in subclasses that have passive abilities.

        Returns:
            PassiveConfig describing the passive, or None if no passive ability.
        """
        return None

    def get_passive_configs(self) -> list[PassiveConfig]:
        """Passive trigger configurations for this card.

        Most cards have one passive and continue to implement
        :meth:`get_passive_config`. Cards that need distinct trigger hooks can
        override this method without changing the single-config API.
        """
        config = self.get_passive_config()
        return [config] if config is not None else []

    def should_offer_passive(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict[str, Any],
    ) -> bool:
        """
        Runtime predicate checked before offering the passive to the player.
        Default: always offer. Override when the trigger fires broadly but
        this passive only cares about a subset (e.g. Battle Fury only cares
        about AFTER_CARD_DISCARD when the source was PLAYED).
        """
        return True

    def get_passive_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        trigger: PassiveTrigger,
        context: dict[str, Any],
    ) -> list[GameStep]:
        """
        Returns steps to execute when this passive ability triggers.

        Only called if get_passive_config() returns a config with a matching trigger.

        Args:
            state: Current game state.
            hero: The hero who owns the passive ability.
            card: The card providing the passive ability.
            trigger: The trigger point (BEFORE_ATTACK, BEFORE_MOVEMENT, etc.)
            context: Execution context with current action information.

        Returns:
            List of steps to execute for the passive effect.
        """
        return []


class CardEffectRegistry:
    """
    Global registry for card effects, indexed by effect_id.
    """

    _effects: ClassVar[dict[str, CardEffect]] = {}
    _spell_effects: ClassVar[dict[str, CardEffect]] = {}

    @classmethod
    def register(cls, effect_id: str, effect: CardEffect):
        cls._effects[effect_id] = effect

    @classmethod
    def get(cls, effect_id: str) -> CardEffect | None:
        return cls._effects.get(effect_id)

    @classmethod
    def register_spell(cls, effect_id: str, effect: CardEffect) -> None:
        """Register spell behavior without colliding with ordinary card IDs."""
        cls._spell_effects[effect_id] = effect

    @classmethod
    def get_for_card(cls, card: Card) -> CardEffect | None:
        """Resolve subtype-specific behavior while preserving public effect IDs."""
        from goa2.domain.models import SpellCard

        effect_id = card.current_effect_id
        if not effect_id:
            return None
        if isinstance(card, SpellCard):
            return cls._spell_effects.get(effect_id) or cls._effects.get(effect_id)
        return cls._effects.get(effect_id)


def register_effect(effect_id: str):
    """Decorator for easy effect registration."""

    def decorator(cls):
        CardEffectRegistry.register(effect_id, cls())
        return cls

    return decorator


def register_spell_effect(effect_id: str):
    """Decorator for spell behavior whose ID may overlap an ordinary card."""

    def decorator(cls):
        CardEffectRegistry.register_spell(effect_id, cls())
        return cls

    return decorator


def get_active_aura_effects(state: GameState, hero: Hero) -> list[tuple[Card, CardEffect]]:
    """Get all CardEffects with active auras for a hero."""
    from goa2.domain.models.enums import CardState

    results: list[tuple[Card, CardEffect]] = []
    # Check ultimate (level >= 8)
    if hero.level >= 8 and hero.ultimate_card and hero.ultimate_card.current_effect_id:
        effect = CardEffectRegistry.get(hero.ultimate_card.current_effect_id)
        if effect:
            results.append((hero.ultimate_card, effect))
    # Check resolved face-up cards (future passive auras)
    for card in hero.played_cards:
        if (
            card
            and card.state == CardState.RESOLVED
            and not card.is_facedown
            and card.current_effect_id
        ):
            effect = CardEffectRegistry.get(card.current_effect_id)
            if effect:
                results.append((card, effect))
    return results


def get_active_shield_cards(state: GameState, hero: Hero) -> list[Card]:
    """Played/resolved cards that carry an active DISCARD_SHIELD effect for `hero`.

    These cards (Mrak's Stone Carapace / Rock Solid) may be discarded this round
    as if they were in hand — to absorb a forced hand-discard or to perform their
    Defense reaction. Returns the matching card objects (from played_cards or the
    current turn card)."""
    from goa2.domain.models.effect import EffectType

    shield_ids = {
        e.source_card_id
        for e in state.active_effects
        if e.effect_type == EffectType.DISCARD_SHIELD
        and str(e.source_id) == str(hero.id)
        and e.is_active
        and e.source_card_id
    }
    if not shield_ids:
        return []

    cards: list[Card] = []
    seen: set[str] = set()
    candidates = list(hero.played_cards)
    if hero.current_turn_card is not None:
        candidates.append(hero.current_turn_card)
    for card in candidates:
        if card is not None and card.id in shield_ids and card.id not in seen:
            cards.append(card)
            seen.add(card.id)
    return cards
