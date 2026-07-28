"""Determinization for ISMCTS.

At a planning decision, opponents commit their cards **face-down and
simultaneously** — that committed card is the dominant hidden information. A
naive clone of the live engine state would let the search *peek* at it.

`determinize` fixes one plausible hidden world: it clones the state and, for
each ENEMY hero that has already committed a hidden card this turn, takes it back
and re-commits a uniformly-random card from that hero's hand. Our own team's
commits/passes are kept (we control them and, in the AI, know their hands).

Why hand *composition* is not resampled: verified that opponents' hands are
near-fully determined by public information — hero
identity (full deck known), level, and visible item stat-bonuses (every
color+tier pair has distinct item stats, so the tucked item reveals which pair
member is in hand). So the true state's hands are already a legal sample; the
genuinely uncertain bit is *which* card each opponent plays this turn, which this
function samples.
"""

from __future__ import annotations

import random

from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.phases import commit_card, uncommit_card

from .clone import clone_state


def _enemy_of(team: TeamColor) -> TeamColor:
    return TeamColor.BLUE if team == TeamColor.RED else TeamColor.RED


def determinize(
    state: GameState, perspective_team: TeamColor, rng: random.Random
) -> GameState:
    """Return a cloned state with enemy hidden commitments resampled.

    Only valid during PLANNING (the phase with hidden simultaneous commits).
    Outside PLANNING it is just an independent clone.
    """
    clone = clone_state(state)
    if clone.phase != GamePhase.PLANNING:
        return clone

    enemy = _enemy_of(perspective_team)
    for hero in clone.teams[enemy].heroes:
        hid = HeroID(hero.id)
        committed = clone.pending_inputs.get(hid)
        if committed is None:
            continue  # not committed, or passed (empty hand) — nothing hidden
        # Take back the hidden commit and replace it with a random plausible one.
        try:
            uncommit_card(clone, hid)
        except ValueError:
            continue  # can't take back (e.g. last-commit already revealed)
        if hero.hand:
            commit_card(clone, hid, rng.choice(list(hero.hand)))
    return clone
