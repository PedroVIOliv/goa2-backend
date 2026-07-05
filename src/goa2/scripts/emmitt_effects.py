"""
Emmitt - Time-manipulation hero card effects.

Design rulings locked with the user are documented in
docs/superpowers/plans/2026-07-05-emmitt-tdd-paths.md.
"""

from __future__ import annotations

from goa2.engine.effects import CardEffect, register_effect

# =============================================================================
# ALTERNATIVE TIMELINES (Ultimate — Tier IV Passive)
# "You may play two cards each turn; if you do, after the cards are revealed,
#  retrieve one of your unresolved cards."
# =============================================================================


@register_effect("alternative_timelines")
class AlternativeTimelinesEffect(CardEffect):
    """Planning-phase passive: enables the two-card commit flow.

    The mechanic lives in the planning/revelation machinery
    (engine/phases.py), which checks this capability flag on the ultimate's
    effect class. The effect itself produces no steps.
    """

    plays_two_cards = True
