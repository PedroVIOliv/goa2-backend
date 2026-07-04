"""Ignatia card effects — the coin-branch chaos hero.

Almost every card branches on the Tie Breaker coin face (see
``GameState.coin_face``): the blue face runs the :tiebreaker_blue: text, the
orange face runs the :tiebreaker_orange: text. Interpretations are locked in
the project memory (project-ignatia-design-decisions).

Three shared mechanics live on ``_IgnatiaBranchEffect`` so every card inherits
them without engine changes:

* **Coin read** — ``build_steps`` picks the branch from ``state.coin_face`` at
  resolve time (the moment the action is performed).
* **Equilibrium** (Silver) — while a THIS_ROUND ``EffectType.EQUILIBRIUM`` effect
  is active she may pick either branch, so the coin read is replaced by a
  blue/orange prompt with both branches gated.
* **Chaos Incarnate** (ultimate) — after performing, ``_maybe_ultimate`` appends
  a ``MayRepeatOnceStep`` whose template flips the coin and performs the action
  again with different targets. Off Equilibrium the re-perform is the opposite
  face (the flip is deterministic, so it is known at build time); on Equilibrium
  it is another free choice. Prior targets are excluded via
  ``ExcludeIdentityFilter`` reading the first performance's (distinct) keys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import TargetType
from goa2.domain.models.effect import EffectType
from goa2.engine.effects import CardEffect, register_effect
from goa2.engine.filters_geometry import InStraightLineFilter, NotInStraightLineFilter
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.filters_units import ExcludeIdentityFilter, TeamFilter, UnitTypeFilter
from goa2.engine.steps import (
    AttackSequenceStep,
    CheckContextConditionStep,
    FlipTieBreakerCoinStep,
    GameStep,
    MayRepeatOnceStep,
    SelectStep,
)

if TYPE_CHECKING:
    from goa2.domain.models import Card, Hero
    from goa2.domain.state import GameState
    from goa2.engine.stats import CardStats


_CHAOS_INCARNATE = "chaos_incarnate"


def _ultimate_active(hero: Hero) -> bool:
    """Chaos Incarnate is unlocked (mirrors the level-8 ultimate convention)."""
    return (
        getattr(hero, "level", 0) >= 8
        and hero.ultimate_card is not None
        and hero.ultimate_card.id == _CHAOS_INCARNATE
    )


def _equilibrium_active(state: GameState, hero: Hero) -> bool:
    """A THIS_ROUND Equilibrium effect this hero created is still in play."""
    hid = str(hero.id)
    return any(
        e.effect_type == EffectType.EQUILIBRIUM and e.source_id == hid for e in state.active_effects
    )


def _excl(exclude: list[str]) -> list[ExcludeIdentityFilter]:
    if not exclude:
        return []
    return [ExcludeIdentityFilter(exclude_self=False, exclude_keys=list(exclude))]


class _IgnatiaBranchEffect(CardEffect):
    """Base for coin-branch cards. Subclasses implement ``_blue_steps`` /
    ``_orange_steps`` (parameterised by a ``slot`` key namespace and a list of
    context keys to ``exclude``) and declare ``_first_target_keys``."""

    # -- subclass hooks ----------------------------------------------------
    def _blue_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
        slot: str,
        exclude: list[str],
    ) -> list[GameStep]:
        raise NotImplementedError

    def _orange_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
        stats: CardStats,
        slot: str,
        exclude: list[str],
    ) -> list[GameStep]:
        raise NotImplementedError

    def _first_target_keys(self, slot: str) -> list[str]:
        """Every context key a branch may store a target under, for this slot
        (union across branches; unused ones are None and harmless to exclude)."""
        raise NotImplementedError

    # -- branch assembly ---------------------------------------------------
    def _branch_for_face(
        self, state, hero, card, stats, face: str, slot: str, exclude: list[str]
    ) -> list[GameStep]:
        if face == "BLUE":
            return self._blue_steps(state, hero, card, stats, slot, exclude)
        return self._orange_steps(state, hero, card, stats, slot, exclude)

    def _equilibrium_branch(
        self, state, hero, card, stats, slot: str, exclude: list[str]
    ) -> list[GameStep]:
        blue = self._blue_steps(state, hero, card, stats, slot, exclude)
        orange = self._orange_steps(state, hero, card, stats, slot, exclude)
        for s in blue:
            s.active_if_key = f"ign_{slot}_is_blue"
        for s in orange:
            s.active_if_key = f"ign_{slot}_is_orange"
        return [
            SelectStep(
                target_type=TargetType.NUMBER,
                prompt="Equilibrium: apply blue or orange text?",
                number_options=[1, 2],
                number_labels={1: "Blue", 2: "Orange"},
                output_key=f"ign_{slot}_choice",
                is_mandatory=True,
            ),
            CheckContextConditionStep(
                input_key=f"ign_{slot}_choice",
                operator="==",
                threshold=1,
                output_key=f"ign_{slot}_is_blue",
            ),
            CheckContextConditionStep(
                input_key=f"ign_{slot}_choice",
                operator="==",
                threshold=2,
                output_key=f"ign_{slot}_is_orange",
            ),
            *blue,
            *orange,
        ]

    def _first_branch(self, state, hero, card, stats) -> list[GameStep]:
        if _equilibrium_active(state, hero):
            return self._equilibrium_branch(state, hero, card, stats, "a", [])
        return self._branch_for_face(state, hero, card, stats, state.coin_face, "a", [])

    def _maybe_ultimate(self, state, hero, card, stats) -> list[GameStep]:
        if not _ultimate_active(hero):
            return []
        exclude = self._first_target_keys("a")
        if _equilibrium_active(state, hero):
            repeat = self._equilibrium_branch(state, hero, card, stats, "b", exclude)
        else:
            opposite = "ORANGE" if state.coin_face == "BLUE" else "BLUE"
            repeat = self._branch_for_face(state, hero, card, stats, opposite, "b", exclude)
        return [
            MayRepeatOnceStep(
                prompt=(
                    "Chaos Incarnate: flip the coin and perform this action again "
                    "with different targets?"
                ),
                steps_template=[FlipTieBreakerCoinStep(), *repeat],
            )
        ]

    def build_steps(
        self, state: GameState, hero: Hero, card: Card, stats: CardStats
    ) -> list[GameStep]:
        return self._first_branch(state, hero, card, stats) + self._maybe_ultimate(
            state, hero, card, stats
        )


# =============================================================================
# F1 — Fire attacks (playing_with_fire / erratic_fireblast / loosely_aimed_firebolts)
#   blue  : "Target a unit in range not in a straight line."
#   orange: "Target a unit in range in a straight line."
# =============================================================================


class _FireAttackEffect(_IgnatiaBranchEffect):
    """Ranged attack whose branch difference is the target's alignment with
    Ignatia: blue targets off the straight line, orange targets on it."""

    def _attack(self, stats, slot: str, line_filter, exclude: list[str]) -> AttackSequenceStep:
        return AttackSequenceStep(
            damage=stats.primary_value,
            range_val=stats.range,
            is_ranged=True,
            target_id_key=f"ign_{slot}_v1",
            target_filters=[line_filter, *_excl(exclude)],
        )

    def _blue_steps(self, state, hero, card, stats, slot, exclude):
        return [self._attack(stats, slot, NotInStraightLineFilter(), exclude)]

    def _orange_steps(self, state, hero, card, stats, slot, exclude):
        return [self._attack(stats, slot, InStraightLineFilter(), exclude)]

    def _first_target_keys(self, slot):
        return [f"ign_{slot}_v1"]


@register_effect("playing_with_fire")
class PlayingWithFireEffect(_FireAttackEffect):
    pass


@register_effect("erratic_fireblast")
class ErraticFireblastEffect(_FireAttackEffect):
    pass


@register_effect("loosely_aimed_firebolts")
class LooselyAimedFireboltsEffect(_FireAttackEffect):
    """Tier III fire attack. Orange additionally "may repeat once on a different
    hero" (the repeat fires even when the first target was not a hero)."""

    def _orange_steps(self, state, hero, card, stats, slot, exclude):
        first = self._attack(stats, slot, InStraightLineFilter(), exclude)
        repeat = MayRepeatOnceStep(
            prompt="Repeat once on a different enemy hero in a straight line?",
            steps_template=[
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Target a different enemy hero in range and in a straight line",
                    output_key=f"ign_{slot}_v2",
                    is_mandatory=True,
                    filters=[
                        UnitTypeFilter(unit_type="HERO"),
                        TeamFilter(relation="ENEMY"),
                        RangeFilter(max_range=stats.range),
                        InStraightLineFilter(),
                        ExcludeIdentityFilter(exclude_keys=[f"ign_{slot}_v1", *exclude]),
                    ],
                ),
                AttackSequenceStep(
                    damage=stats.primary_value,
                    range_val=stats.range,
                    is_ranged=True,
                    target_id_key=f"ign_{slot}_v2",
                ),
            ],
        )
        return [first, repeat]

    def _first_target_keys(self, slot):
        return [f"ign_{slot}_v1", f"ign_{slot}_v2"]
