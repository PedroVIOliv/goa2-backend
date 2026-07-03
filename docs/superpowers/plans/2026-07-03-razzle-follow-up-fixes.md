# Razzle Multipiece Follow-up Fixes

**Date:** 2026-07-03
**Status:** Follow-up checklist after implementation audit

## Goal

Finish the finite integration gaps in the stable `HeroPiece` architecture.
Keep the current model: `hero_razzle` is player-level only, while board
presence is represented by stable `hero_razzle_piece_1..4` entities.

Do not migrate to anchor swap. Anchor swap would mask some compatibility bugs,
but it reintroduces hidden identity movement and persistent-binding risk. The
remaining work is to centralize the player-vs-board identity boundary.

## Boundary Rules

1. Board-level hero checks must treat `HeroPiece` as a hero unit.
   This includes targeting, auras, action prevention, terrain rules, adjacency,
   support, and "each enemy hero" style effects.

2. Player-level ownership must normalize `HeroPiece` IDs to their owner hero.
   This includes hand, deck, discard, gold, markers, auth, and `player_id`
   routing for input prompts.

3. Razzle card resolution must use the bound acting piece for authoritative
   positional stats and origins. Preview values may remain approximate, but
   actual resolution must not compute area-sensitive stats from `hero_razzle`
   when that ID has no board position.

4. Persistent positional bindings created by Razzle must store stable piece IDs,
   not the owner hero ID, whenever the binding refers to a board location.

## Known Fixes

### 1. Hero-like board checks

Add or reuse a small helper such as `is_hero_unit(entity)` and replace scattered
`isinstance(entity, Hero)` checks in board-positional logic.

Known files:

- `src/goa2/engine/validation_effects.py`
- `src/goa2/engine/validation_terrain.py`
- `src/goa2/engine/filters_units.py`
- `src/goa2/engine/filters_hex.py`

Guard tests:

- `AffectsFilter.ENEMY_HEROES` matches an enemy Razzle piece.
- Static Barrier applies when the acting board unit is a Razzle piece.
- A filter asking for adjacency to a hero counts adjacent Razzle pieces.
- Brynn-style hero obstacle logic counts enemy Razzle pieces.

### 2. Player/input normalization

Normalize any context-derived piece ID before using it as an input `player_id`.
The player who answers a prompt must be `hero_razzle`, not
`hero_razzle_piece_N`.

Known file:

- `src/goa2/engine/steps/selection.py`

Guard tests:

- A forced discard targeting `hero_razzle_piece_N` displays cards from Razzle's
  hand and routes the prompt to `hero_razzle`.
- The server accepts the Razzle player's token for that prompt.

### 3. Acting-piece stats and origins

When resolving a primary card, compute authoritative stats using
`state.resolve_board_actor(hero.id)` after `ChooseActingPieceStep` has bound a
piece. When resolving defense or on-block text, use the attacked piece from the
combat context when available.

Known files:

- `src/goa2/engine/effects.py`
- `src/goa2/engine/stats.py`

Guard tests:

- An area stat modifier near only the acting piece changes Razzle's resolved
  card value.
- The same modifier near another piece does not affect the action.
- Defense stats/radius calculations use `context["defender_id"]` when the
  defender is a Razzle piece.

### 4. Stable persistent bindings

Any step that creates a persistent positional effect or delayed by-ID binding
from Razzle should store the acting piece ID for board location semantics.

Known files to audit:

- `src/goa2/engine/steps/effects.py`
- Any future Razzle card effects that create `ActiveEffect`, delayed return, or
  by-ID follow-up steps.

Guard tests:

- A persistent point/radius effect created by Razzle remains anchored to the
  piece that created it after Razzle acts with a different piece.
- A delayed return/swap effect targeting a Razzle piece returns the same physical
  piece, not whichever piece acted later.

## Stop Condition

This is complete when the guard tests above pass and the full suite passes:

```bash
PYTHONPATH=src uv run pytest tests/ -q
```

After that, remaining Razzle issues should be treated as normal card-specific
bugs, not open-ended multipiece infrastructure uncertainty.
