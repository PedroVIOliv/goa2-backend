# Razzle Multi-Piece Hero — Engine Scoping & Design

**Date:** 2026-07-02
**Status:** Draft — awaiting user review
**Scope:** Core engine infrastructure for Razzle's "multiple identical hero pieces" gimmick. Individual card effects that merely *use* the infrastructure (swaps, pushes, extra moves) are out of scope and can be implemented by other contributors afterwards using the helpers this design provides.

## 1. The Gimmick (rules baseline)

Razzle is one player-hero with up to **4 identical pieces** on the board (total supply: 4).

Confirmed rulings (board game forum + user):

- **Pieces are fully separate hero units for all board-level effects.** Enemy targeting, attacks, AoE effects, pushes, auras, and support bonuses treat each piece as an independent enemy hero. If two pieces are in an AoE "each enemy hero discards" radius, Razzle discards **twice**. Effects sourced from Razzle source out of one specific piece.
- **Shared player-level state:** one hand, deck, discard pile, level, gold, item basket, one card played per round-turn, one initiative, one slot in turn order.
- **Acting:** when Razzle performs an action (primary or secondary), she chooses **which piece performs it** at that moment. One piece performs the whole action.
- **Defense:** any piece being attacked → the Razzle player defends normally from the shared hand.
- **Defeat:** if any piece is defeated, Razzle is defeated → *remove all of you*; killer rewarded once; respawn as one piece.
- **Voluntary removal ≠ defeat** (Into Thin Air): removing all pieces does not defeat Razzle; she is off-board and "respawns as normal".
- **Spawn rule (official):** spawned pieces come from the supply only, never relocated from the board. Supply = 4 − pieces on board.

## 2. Engine constraints discovered

| Constraint | Location | Consequence |
|---|---|---|
| The `Hero` object IS the board entity; `entity_locations: dict[BoardEntityID, Hex]` is strictly one-to-one | `domain/state.py:99` | One hero cannot natively occupy multiple hexes |
| Defense window routes via `state.get_hero(target_id)` — target unit ID must literally be the hero ID | `engine/steps/reactions.py:38` | Attacking a non-hero-ID piece would silently skip defense and auto-defeat |
| `SelectStep` UNIT candidates = `entity_locations` keys that resolve via `state.get_unit()`, which only searches team rosters | `engine/steps/selection.py:123`, `domain/state.py:302` | Extra pieces stored elsewhere are invisible to targeting |
| Turn machinery compares `current_actor_id` / `defender_id` against `hero.id` by equality in many places | `handler.py`, `steps/cards.py`, `steps/phases.py` | Threading piece IDs through actor contexts is highly invasive |
| `AnyMiscEntity` union is hand-maintained | `engine/step_types.py` | New board-entity type must be added or persistence breaks |
| ~12 `team.heroes` enumeration sites in engine/domain | `phases.py`, `steps/combat.py`, `steps/cards.py`, `steps/markers.py`, `views.py`, `state.py` | Each must be classified: board-positional (must include pieces) vs player-level (must not) |

## 3. Approaches considered

### A. Proxy pieces + anchor swap (recommended)

`hero_razzle` remains a normal single-hex board entity — the **anchor**. Extra pieces are lightweight `HeroPiece` proxy units referencing the owner hero. Whenever a *specific* piece must behave as the hero (perform an action, defend an attack, be defeated), we **swap the anchor**: exchange the `entity_locations` entries of `hero_razzle` and that proxy.

The load-bearing insight: **pieces are indistinguishable by rule**, so which hex holds the "real" `hero_razzle` ID is unobservable to players. Swapping is semantically free. After a swap, every existing code path — reaction window, defense effects, combat resolution, defeat, movement, adjacency, stats, actor-ID equality — works unchanged because the relevant piece literally *is* `hero_razzle`.

- **Pros:** identity equalities hold everywhere; defense/combat/defeat pipelines untouched in the common path; complexity concentrated in ~4 choke-point hooks + one new entity type.
- **Cons:** the swap is a novel invariant future maintainers must know; a handful of edge paths (non-combat defeats of a proxy) need explicit rerouting.

### B. Resolver indirection (no swap)

Pieces get first-class IDs; `state.get_hero(piece_id)` resolves to the owning `Hero`; `current_actor_id`/`defender_id` carry piece IDs.

- **Pros:** positions always "truthful"; no hidden identity switching.
- **Cons:** breaks every `hero.id == actor_id` equality in turn machinery (`unresolved_hero_ids`, finalize, planning); every context key carrying a hero ID becomes ambiguous (piece or hero?). Blast radius across 20+ files. Rejected.

### C. Clone Hero objects

Register `hero_razzle_2..4` as real `Hero` entries sharing hand/deck lists by reference.

- **Cons:** planning/initiative/turn order would treat them as separate heroes needing suppression everywhere; Pydantic JSON persistence duplicates the shared containers on reload, silently forking the hand. Rejected outright.

## 4. Recommended design (Approach A)

### 4.1 `HeroPiece` entity

- New `HeroPiece(Unit)` in `domain/models/unit.py` (or `base.py`): `entity_kind: Literal["hero_piece"]`, `owner_hero_id: HeroID`, `team` copied from owner, `name` = owner's name.
- Stored in `state.misc_entities`; IDs via `state.create_entity_id("razzle_piece")`.
- **Add to `AnyMiscEntity`** union in `engine/step_types.py` (hand-maintained — known footgun).

### 4.2 Unit-hood plumbing

- Extend `state.get_unit()` to also return `Unit` instances found in `misc_entities`. This single change makes pieces: enumerable by `SelectStep` UNIT targeting, matchable by `TeamFilter`/`RangeFilter`, blocking for pathfinding, and counted by adjacency/support logic — because those all flow through `get_unit`/`get_entity` + `entity_locations`.
- Safety net: extend `state.get_hero()` to resolve a piece ID to its owning `Hero`. Covers hero-state operations (discard steps, gold steps, marker placement) that receive a piece ID from AoE enumerations without needing a swap.

### 4.3 Anchor-swap primitive

`swap_anchor(state, hero_id, piece_id)` in a new `engine/hero_pieces.py`: swap the two `entity_locations` entries (and tile occupancy). No events emitted — the swap is unobservable by design (views render pieces identically).

### 4.4 Choke-point hooks

1. **Acting piece choice** — in `ResolveCardStep` (`steps/cards.py:590`), after the action is chosen and before action steps are built: if the actor owns on-board pieces (>1 total presence), prompt `SELECT_UNIT` among own pieces (anchor + proxies), then `swap_anchor` to the chosen one. Skipped when only one piece is on board. Same hook applies to re-perform machinery (`PerformPrimaryActionStep` — note existing invariants: re-perform searches `current_turn_card`; exclusions propagate).
2. **Enemy target lock** — when a combat target key resolves to a proxy piece, swap and rewrite the context key to the hero ID. Hook at the top of `ReactionWindowStep.resolve()` (single choke point for all attack paths). Emergent correctness: "repeat, targeting a different unit" exclusion lists contain `hero_razzle` after the first attack, while the other pieces keep distinct proxy IDs — so attacking a *second* piece stays legal, exactly per the ruling.
3. **Defeat cascade** — `DefeatUnitStep`: if the victim is a proxy piece (non-combat defeat paths: terrain crash during a push, disruptor defeats), swap first so the hero-defeat path runs normally; after any hero defeat where the hero owns pieces, remove all proxies. Kill rewards granted once (they key off the hero, unchanged).
4. **Piece removal (not defeat)** — new `RemoveHeroPieceStep`: removing the anchor while proxies survive → swap anchor to a survivor first, then remove the proxy. Remove-all (Into Thin Air) → remove anchor + proxies with no defeat; existing off-board handling already covers the aftermath (`ResolveCardStep` skips actions for off-board heroes, `cards.py:615`; `RespawnHeroStep` respawns any off-board hero at round respawn).

### 4.5 Spawn & supply

- New `SpawnHeroPieceStep`: spawn up to N pieces into empty hexes matching filters, capped at `4 − pieces_on_board`. Per the official spawn rule, from supply only.
- Supply is derived (never stored): `4 − (1 anchor + live proxies)`.
- New `StepType` enum values for both new steps (union auto-derives; just set the `type` default).

### 4.6 Effect-author surface (unblocks other contributors)

In `engine/hero_pieces.py` + filters:

- `get_piece_ids(state, hero_id)` → all on-board piece IDs (anchor + proxies).
- `count_pieces_in_radius(state, hero_id, center, radius)` — for Crowd Control / Ransack / Rummage.
- New filter `HeroPieceFilter(owner="SELF", exclude_acting=True)` (unique `FilterType`) — "another one of you" selections for team_spirit, wire_dancers, spectacle, tightrope-line cards.
- Moving/pushing a proxy is just `MoveUnitStep`/`PushUnitStep` on the proxy ID — no new machinery.

### 4.7 Views, events, client contract

- `build_view()` board/units output includes pieces as units with `owner_hero_id` so clients render them as Razzle. Facedown/hand visibility unaffected (pieces carry no cards).
- New `GameEventType` values (or metadata conventions) for piece spawn/removal so clients can animate.
- Update `docs/CLIENT_INTEGRATION_GUIDE.md`: piece entities in views, new events, and the fact that `SELECT_UNIT` options may include piece IDs.

### 4.8 Persistence & rollback

- Pieces live in `misc_entities` + `entity_locations` → round-trip via `AnyMiscEntity`. Add explicit save/load round-trip test with 3 proxies on board.
- Rollback snapshots (`ConfirmResolutionStep` flow) serialize state — anchor swaps are part of state, so rollback restores them for free.

### 4.9 Enumeration audit

Classify each `team.heroes` iteration site:

| Site | Class | Action |
|---|---|---|
| Planning / initiative / turn order (`phases.py`) | player-level | exclude pieces (no change needed — they iterate `Hero` objects) |
| Minion battle & lane push hero counting (`steps/combat.py`) | board-positional | **include pieces** (each piece counts — "separate heroes always") |
| Respawn sweep (`phases.py:185`) | player-level | no change (anchor off-board ⇒ respawn) |
| Marker sites (`steps/markers.py`) | player-level | normalize piece→hero in `place_marker` (see §5.1) |
| Views (`domain/views.py`) | both | hero cards player-level; board units include pieces |
| `state.get_card_by_id`, `get_hero` | player-level | no change |

The implementation plan must grep-audit all 12 sites individually.

## 5. Rules rulings and remaining assumptions

1. **Markers (RULED, user-confirmed):** markers apply to the **hero**, never to a piece — a marker placed via any piece affects all Razzles. Implementation: normalize inside `state.place_marker()` — a piece ID passed as `target_id` resolves to the owning hero ID. `get_markers_on_hero(hero_id)` then works unchanged, and hero-level penalties (initiative, skip-turn) naturally hit Razzle's single card/turn. Effects that read the marked hero's *position* enumerate all pieces via `get_piece_ids()` (consistent with "separate heroes always").
2. **Zone control / lane push / minion-battle presence:** design assumes each piece counts as a hero presence (consistent with "separate heroes always").
3. **Support / minion-defense modifiers:** multiple adjacent pieces each grant their bonus independently (separate units).
4. **Twin Strike (ultimate):** "another one of you may repeat it" requires a *different* piece to perform the repeat, targeting a different unit. Needs ≥2 pieces on board.
5. **Movement actions:** one chosen piece performs the entire movement action (no splitting spaces across pieces).

## 6. In-scope vs out-of-scope cards

**In gimmick scope (they ARE the gimmick, used as validation):**

- `stunt_doubles` (gold basic) — exercises `SpawnHeroPieceStep`, supply cap, defeat-cascade clause.
- `crowd_control` (silver basic) — exercises defense-side radius counting *at the attacked piece* and remove-all-others.
- `phantom_strike` (Tier I red) — simplest voluntary piece removal incl. anchor-promotion.

**Out of scope (normal card work using §4.6 helpers):** alleyoop/group_performance/team_spirit (hero swap + move another piece), tightrope/high_wire/wire_dancers (post-move piece move), theatrics/spectacle (minion swap ± repeat), magic_trick/aaaand_its_gone (push + counter-move), hit_and_gone/into_thin_air (removal family — into_thin_air's remove-all needs §4.4.4 verified), rummage/ransack (radius count + retrieve), `twin_strike` ultimate (repeat machinery + piece swap between repeats — depends on existing `PerformPrimaryActionStep` re-perform invariants).

## 7. Testing strategy

TDD throughout (`tests/engine/effects/` helpers, `effect_contract`/`effect_flow` marks). Core invariant tests, roughly in build order:

1. `HeroPiece` unit-hood: enumerable by enemy `SelectStep`, filterable by team/range, blocks pathfinding, persists through JSON round-trip.
2. Anchor swap: unobservable (views byte-identical modulo IDs), positions exchanged, tile occupancy consistent.
3. Attack a proxy → defense prompt appears for the Razzle player; defense-effect radius computed at the attacked piece.
4. Defeat via any piece → all pieces removed, killer rewarded once, respawn as one piece.
5. Attack piece A (blocked), repeat "different unit" → piece B still targetable.
6. Non-combat proxy defeat (push into terrain) → full hero defeat.
7. Voluntary remove-all → not defeated, turn actions skipped, respawns at round respawn.
8. Supply cap: spawn clamps at 4 total; removal frees supply.
9. Acting-piece prompt appears only with ≥2 pieces; chosen piece performs the action (adjacency checks from its hex).
10. Minion battle / support counting includes pieces.
11. Marker placed via a proxy piece attaches to the hero (`get_markers_on_hero` finds it; penalty applies to Razzle's turn).

## 8. Estimated footprint

- **New:** `engine/hero_pieces.py`, `HeroPiece` model, 2–3 new steps + StepTypes, 1 new filter + FilterType, `scripts/razzle_effects.py` (3 validation cards), tests.
- **Modified:** `state.py` (`get_unit`/`get_hero`/`place_marker`), `steps/reactions.py` (target-lock hook), `steps/combat.py` (defeat cascade + battle counting), `steps/cards.py` (acting-piece hook), `domain/views.py`, `engine/step_types.py` (AnyMiscEntity), `docs/CLIENT_INTEGRATION_GUIDE.md`.
