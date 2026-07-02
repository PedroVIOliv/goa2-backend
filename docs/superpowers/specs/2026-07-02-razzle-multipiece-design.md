# Razzle Multi-Piece Hero — Engine Scoping & Design

**Date:** 2026-07-02 (rev 2 — architecture decision changed by user)
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
- **Markers (RULED):** markers apply to the **hero**, never to a piece — a marker placed via any piece affects all Razzles.
- **Spawn rule (official):** spawned pieces come from the supply only, never relocated from the board. Supply = 4 − pieces on board.

## 2. Architecture decision (user-made)

**Chosen: hero/piece abstraction — all pieces are proxies, no "real one" on the board.**

The `Hero` object becomes a purely player-level entity for Razzle: hand, deck, discard, level, gold, items, markers, turn slot. It **never appears in `entity_locations`**. Board presence is exclusively via 1–4 `HeroPiece` entities with **stable IDs** (`razzle_piece_1..4`).

Rationale (vs the previously drafted "anchor swap", kept in §10 for the record):

- **Stable identity everywhere.** Persistent by-ID bindings (Hanu's journey bakes unit-ID literals into end-of-turn steps, POINT-scope `ActiveEffect`s) attach to piece IDs that never change referent. The anchor-swap design's entire residual-risk class — and its "stable-binding rule" maintenance tax on every future effect — disappears.
- **Truthful state.** No hidden identity-swap invariant for future maintainers; API clients never observe ID/position exchanges; "repeat targeting a different unit" and any future same-target trackers compare real unit IDs.
- **Right long-term model.** Hero-as-player vs piece-as-board-presence is the honest decomposition; Razzle is just the first hero with piece count ≠ 1. The design keeps a path to migrating all heroes onto it later (§9).

### 2.1 The cost-control insight: two-tier identity, one interception point

The expensive version of this refactor would put piece IDs into actor contexts, breaking ~132 `current_actor_id` usages, ~81 `get_hero` call sites, and ~103 `player_id` routing sites. We avoid nearly all of it by making identity explicitly two-tier and **only intercepting position resolution**:

- **Player-level identity (unchanged):** `current_actor_id`, `player_id` in input requests, `unresolved_hero_ids`, planning/initiative/finalize equality all keep holding `hero_razzle`. Turn machinery, auth, and WebSocket routing are untouched.
- **Board-level identity (new, truthful):** selection outputs, `victim_id`/`defender_id`, push/move targets carry **piece IDs**. Pieces are real `Unit`s in `entity_locations`, so all *existing* positional code that receives a target ID already works on them.
- **The one gap:** positional queries about the *hero* ID (`entity_locations.get(hero_id)` for the actor's own position, adjacency "to you", off-board checks). These migrate to a resolver (§3.2).

## 3. Design

### 3.1 `HeroPiece` entity

- `HeroPiece(Unit)` in `domain/models/unit.py`: `entity_kind: Literal["hero_piece"]`, `owner_hero_id: HeroID`, `team` copied from owner, `name` = owner's name.
- Stored in `state.misc_entities`; stable IDs `razzle_piece_1..4` allocated once per game (supply slots), reused across respawns.
- **Add to `AnyMiscEntity`** union in `engine/step_types.py` (hand-maintained — known footgun).
- Unit-hood plumbing: extend `state.get_unit()` to also return `Unit` instances from `misc_entities`. This single change makes pieces enumerable by `SelectStep` UNIT targeting, matchable by `TeamFilter`/`RangeFilter`, blocking for pathfinding, and counted by adjacency/support logic.
- Hero-resolution safety net: extend `state.get_hero()` to resolve a piece ID to its owning `Hero`. Covers hero-state operations (discards, gold, stats, markers) that receive a piece ID.

### 3.2 Position resolver — the load-bearing new API

New methods on `GameState` (or `engine/hero_pieces.py`):

- `get_position(entity_id) -> Hex | None` — piece/normal-unit ID → its `entity_locations` entry; multi-piece hero ID → **the acting piece's hex** if an action is in progress, else `None`.
- `has_board_presence(hero_id) -> bool` — normal hero: in `entity_locations`; multi-piece hero: any piece on board. Replaces raw `hero_id in state.entity_locations` off-board checks (e.g. `ResolveCardStep`, `cards.py:616`; combat guards in `reactions.py:230`, `combat.py:177`).
- `get_piece_ids(state, hero_id) -> list[str]` — on-board pieces (returns `[hero_id]` itself for normal heroes, making effect helpers uniform).

**Migration:** grep-audit direct `entity_locations` reads in shared engine code (filters, rules, validation, steps — ~20 files) and route hero-positional ones through `get_position`. Reads keyed by *target/victim* IDs already work (those are piece IDs). Writes (`place_entity`/`move_unit`/`remove_entity`) are untouched.

### 3.3 Acting piece

- `state` gains `acting_piece_id: BoardEntityID | None` (serialized; cleared at `FinalizeHeroTurnStep` alongside context).
- Hook in `ResolveCardStep` after the action is chosen: if the actor is a multi-piece hero with ≥2 pieces, prompt `SELECT_UNIT` among own pieces; with exactly 1, auto-bind it. `get_position(hero_razzle)` then resolves through it, so effect code, range/adjacency filters, and movement steps relative to "you" work unchanged.
- Movement/attack steps that move "the hero" must operate on the acting piece ID — `MoveSequenceStep`/`AttackSequenceStep` resolve `current_actor_id` → acting piece via the resolver at the point they touch the board.
- Effect texts "another one of you" select among `get_piece_ids()` minus the acting piece (new `HeroPieceFilter`, unique `FilterType`).
- Interplay with Hanu's `CONTROL_NEXT_ACTION` (player_id remap): the acting-piece prompt is addressed via the same remap path, so a controlled Razzle turn has the controller choose the piece. No special-casing.

### 3.4 Defense & combat path

- Enemy attacks target a **piece ID** truthfully (`victim_id = razzle_piece_2`).
- `ReactionWindowStep`: `get_hero(piece_id)` resolves the owner → defense prompt built from the shared hand; **`player_id` on the input request is normalized to the owner hero ID** so bearer-token auth and `validate_input_turn` work unchanged. `defender_id` in context stays the **piece ID** (positional truth — Crowd Control's "per other one of you in radius" counts from the attacked piece), while steps needing the player resolve via `get_hero`.
- `get_computed_stat(state, piece_id, ...)` resolves items/modifiers via the owner.
- `ResolveDefenseTextStep`/`ResolveOnBlockEffectStep`: already call `get_hero(defender_id)` — work via resolution; their off-board guards migrate to `has_board_presence`/piece-ID checks.
- "Repeat targeting a different unit": exclusion lists hold real piece IDs — attacking a second piece is naturally legal, attacking the same piece naturally excluded. No emergent-behavior test needed; it's direct.

### 3.5 Defeat, removal, respawn, supply

- `DefeatUnitStep` victim = piece → resolve owner → hero-defeat path (rewards once, `heroes_defeated_this_round` gets the hero ID) + **remove all owner pieces**.
- `RemoveHeroPieceStep` (voluntary, not defeat): remove chosen piece(s); no anchor promotion needed — pieces are symmetric. Remove-all → hero off-board, not defeated; existing off-board handling covers turn skip; `RespawnHeroStep` migrates its "on board?" check to `has_board_presence` and spawns **one piece** at the chosen spawn hex.
- `SpawnHeroPieceStep`: spawn up to N pieces into empty hexes matching filters, capped at `4 − pieces_on_board` (supply derived, never stored).
- Markers: `state.place_marker()` normalizes a piece ID target to the owner hero ID (per ruling §1).

### 3.6 Enumeration audit

Classify each `team.heroes` iteration site (~12 in engine/domain):

| Site | Class | Action |
|---|---|---|
| Planning / initiative / turn order (`phases.py`) | player-level | no change |
| Minion battle & lane push hero counting (`steps/combat.py`) | board-positional | count **pieces** (each counts — "separate heroes always") |
| Respawn sweep (`phases.py:185`) | player-level | uses `has_board_presence` |
| Spawn-blocking displacement (`combat.py:1077` area) | board-positional | displace pieces |
| Views (`domain/views.py`) | both | hero cards player-level; board units include pieces |
| `get_card_by_id`, `get_hero` | player-level | no change |

### 3.7 Views, events, client contract

- `build_view()`: pieces appear in the board/units output with `owner_hero_id`; the hero's player-level block (hand, discard, gold) renders as today. Razzle's hero entry has no single board position — clients derive presence from pieces. **This is a client-contract change**: update `docs/CLIENT_INTEGRATION_GUIDE.md` (piece entities, piece IDs in `SELECT_UNIT` options, defense prompts arriving with `player_id = hero_razzle` while the attacked unit is a piece).
- New `GameEventType` values (or metadata conventions) for piece spawn/removal; movement/push events already carry entity IDs and work for pieces.

### 3.8 Persistence & rollback

- Pieces live in `misc_entities` + `entity_locations`; `acting_piece_id` serializes on state. Round-trip test with 3 pieces + mid-action save.
- Rollback snapshots capture everything; stable IDs mean replays/diffs stay truthful.

## 4. Rules rulings and remaining assumptions

1. **Markers (RULED):** hero-level, normalize in `place_marker` (§3.5).
2. **Zone control / lane push / minion-battle presence:** each piece counts (consistent with "separate heroes always").
3. **Support / minion-defense modifiers:** multiple adjacent pieces each grant their bonus independently.
4. **Twin Strike (ultimate):** the repeat is performed by a *different* piece, targeting a different unit; needs ≥2 pieces.
5. **Movement actions:** one chosen piece performs the entire movement action (no splitting).

## 5. In-scope vs out-of-scope cards

**In gimmick scope (validation cards):** `stunt_doubles` (spawn + supply cap + defeat clause), `crowd_control` (defense-side radius at attacked piece + remove-all-others), `phantom_strike` (voluntary removal).

**Out of scope (normal card work via §3 helpers):** alleyoop/group_performance/team_spirit, tightrope/high_wire/wire_dancers, theatrics/spectacle, magic_trick/aaaand_its_gone, hit_and_gone/into_thin_air, rummage/ransack, `twin_strike` ultimate (depends on `PerformPrimaryActionStep` re-perform invariants + acting-piece rebind between repeats).

## 6. Testing strategy

TDD throughout (`tests/engine/effects/` helpers, `effect_contract`/`effect_flow` marks). Core invariant tests, roughly in build order:

1. `HeroPiece` unit-hood: enumerable by enemy `SelectStep`, team/range filterable, blocks pathfinding, JSON round-trip (incl. `acting_piece_id`).
2. Position resolver: `get_position(hero)` = acting piece mid-action / `None` otherwise; `has_board_presence` across 0/1/4 pieces.
3. Attack a piece → defense prompt reaches the Razzle player (`player_id = hero_razzle`), defense value from shared hand, radius effects computed at the attacked piece.
4. Defeat via any piece → all pieces removed, killer rewarded once, respawn as one piece.
5. Attack piece 1 (blocked), repeat "different unit" → piece 2 targetable, piece 1 excluded (direct ID comparison).
6. Non-combat piece defeat (push into terrain) → full hero defeat.
7. Voluntary remove-all → not defeated, turn actions skipped, respawns at round respawn.
8. Supply cap: spawn clamps at 4 total; removal frees supply; stable IDs reused.
9. Acting-piece prompt only with ≥2 pieces; adjacency/range computed from the chosen piece; auto-bind with 1 piece (no prompt regression for the common case).
10. Minion battle / support counting includes pieces.
11. Marker placed via a piece attaches to the hero.
12. Persistent-binding truthfulness: Hanu journeys a Razzle piece → Razzle acts with a different piece → end-of-turn swap-back returns the correct physical piece (passes by construction; guards regressions).
13. Off-board-check migration guard: no remaining raw `hero_id in entity_locations` checks against multi-piece heroes (grep-based test or targeted flows).

## 7. Estimated effort & footprint

~1.5–2× the anchor-swap estimate: **3–5 focused sessions** for infrastructure, then validation cards.

- **New:** `engine/hero_pieces.py` (resolver + helpers), `HeroPiece` model, `SpawnHeroPieceStep`/`RemoveHeroPieceStep` + StepTypes, `HeroPieceFilter` + FilterType, `acting_piece_id` on state, `scripts/razzle_effects.py` (3 validation cards), tests.
- **Modified:** `state.py` (`get_unit`/`get_hero`/`place_marker`/resolver), `steps/reactions.py` (owner routing), `steps/combat.py` (defeat cascade, battle counting, respawn check), `steps/cards.py` (acting-piece hook, off-board checks), `steps/movement.py`/`AttackSequenceStep` (actor→piece resolution at board contact), positional `entity_locations` reads across filters/rules/validation (~20 files, mechanical), `domain/views.py`, `engine/step_types.py`, `docs/CLIENT_INTEGRATION_GUIDE.md`.
- **Untouched by design:** turn machinery equality, planning/initiative, server auth/WS routing, the 26 existing hero effect scripts, existing tests (normal heroes keep hero-ID-as-board-entity).

Main risk: an unmigrated hero-positional read treats Razzle as off-board → a *visible* failure (action skipped, effect fizzles), not a silent wrong-piece bug. Mitigation: the grep-audit is finite and test 13 guards it.

## 8. Future direction (not in scope): universal hero pieces

Migrating **all** heroes to piece-based presence (hero objects never in `entity_locations`) would eliminate the two-model split. The resolver API is designed so this is a mechanical follow-up: `get_position`/`has_board_presence`/`get_piece_ids` already behave uniformly for single-piece heroes. Defer until Razzle proves the model.

## 9. Rejected alternatives (for the record)

- **Anchor swap** (rev 1 of this spec): `hero_razzle` always one of the pieces; swap `entity_locations` entries when a specific piece must be the hero. Cheapest option (~10 files, zero regression surface) and workable, but rejected by user decision: it relies on a hidden identity-swap invariant, leaks ID-teleports to API clients, and carries a permanent "stable-binding rule" maintenance tax — every future effect baking a unit ID into a delayed trigger (e.g. Hanu's journey literals, `steps/effects.py:181`) must check it never attaches to the anchor. The piece abstraction eliminates that class by construction.
- **Piece IDs in actor contexts** (full "truthful" refactor): `current_actor_id`/`player_id` carry piece IDs — breaks ~132 actor-ID usages, ~103 input-routing sites, and hero-ID equality across turn machinery. The two-tier identity model (§2.1) achieves the same truthfulness where it matters (board state, bindings) without this cost.
- **Clone Hero objects:** share hand/deck by reference across 4 `Hero` entries — planning/turn order would need suppression everywhere, and Pydantic JSON persistence forks the shared containers on reload. Rejected outright.
