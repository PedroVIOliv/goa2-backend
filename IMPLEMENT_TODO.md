# Implementation TODO: live player history

Implementation scope on this branch is backend only. Section 5 remains the
future frontend integration plan; no frontend source changes are included.
Checked items describe the implemented backend. Validation evidence and the
remaining deployment latency gate are in `docs/LIVE_HISTORY_VALIDATION.md`.

## Goal and agreed behavior

Allow players and spectators to browse earlier board states during a live game,
including after disconnecting or reconnecting. Keep the complete audit replay,
but exclude abandoned attempts and correction operations from player browsing.

- The client buffers the latest 30 complete historical views and fetches missing
  or older positions from the server.
- Keep sending complete player-scoped live views. Changing live delivery to
  patches is a separate optimization.
- Store server history as periodic snapshots plus JSON Patches. New history
  reads must not require engine re-simulation.
- Capture information visible to each viewer at that historical moment,
  including their own private cards. Never serve omniscient history to players.
- Collapse each planning phase into one replaceable position. After planning,
  capture each accepted decision and its deterministic processing, rather than
  each atomic engine step.
- Browsing is read-only and does not pause the match or its clocks.

## 0. Reuse existing replay infrastructure first

Implement common primitives before adding live-history adapters. Do not create
a parallel replay engine, patch codec, compression stack, or client patch player.

| Existing implementation | Reuse or extraction |
| --- | --- |
| `server/shares.py` | Extract pure keyframe/patch group construction, reconstruction, compressed-size budgeting, and Brotli/gzip encoding into a shared codec used by both shares and live history. |
| `server/replay.py` | Reuse replay loading, decision classification/application, seeded setup, winner calculation, and rewind-prefix helpers. Add capture observation to the existing driving path for backfill. |
| `server/share_bake.py` | Reuse the forward-only render pattern. Shared replays already collapse table rewinds with `effective_decisions()`; preserve that behavior. |
| `server/workers.py` and `server/share_mint.py` | Reuse `run_heavy()` and the existing request-independent producer/single-flight pattern for backfill, with a separate history task registry. |
| `domain/views.py` | Reuse `build_view()` and the public board projection across every seated hero and the spectator, including disconnected seats. This branch has no `server/event_history.py`; do not introduce a dependency on that module. |
| Frontend `api/replay.ts` and `utils/jsonPatch.ts` | Extract cached group reconstruction from `sharedReplaySource()` and reuse `applyPatches()`. |
| Frontend replay components | Reuse transport controls, read-only board rendering, and applicable roster/presentation components. |

- [x] Refactor the group codec out of `shares.py` without changing existing
      share files, URLs, visibility, or response contracts. Keep share-token,
      publication, and retention logic in the share subsystem.
- [x] Give the shared codec an incremental builder API as well as the existing
      sequential batch-render adapter. Keep the codec independent of engine,
      authentication, player-index, and persistence concerns.
- [x] Expose a shared replay iteration/capture seam around existing decision
      application instead of copying `_apply_decision()` or implementing another
      reconstruction loop. Preserve raw-prefix information and rewind callbacks.
- [x] Reuse `effective_indices()` / `effective_decisions()` for table rewind
      semantics where appropriate. They do not collapse action rollback or
      planning takebacks; implement those as additional player-index policy.
- [x] Run existing replay/share tests before and after extraction, then extend
      those fixtures to cover live adapters and codec round trips.

Concrete shared interfaces and migration order:

1. **Group codec:** put `GroupBuilder`, `make_patch()`, `apply_patch()`,
   `reconstruct()` / `reconstruct_many()`, `encode()` / `decode()`, and
   `for_delivery()` in `server/replay_codec.py`. Make `shares._write_groups()`
   a batch adapter over the same incremental builder used by live history.
   Preserve the `{start, keyframe, patches}` envelope and existing share
   defaults. Keep atomic file publication and the active history index outside
   the codec. Test round trips through both adapters, including patch-value
   aliasing: reconstructing one position must not modify later reads.
2. **Decision application:** keep `_apply_decision()` as the single engine
   operation dispatcher. Put raw-record handling, including `ov_rewind`, in
   `apply_replay_record()` and use it from `ReplayCursor`, `replay_game()`,
   replay verification, and `walk_replay()`. Have share baking use
   `ReplayCursor`; have history backfill observe `walk_replay()` boundaries.
   Every consumer must retain its existing decision-index semantics.
3. **Corrections:** keep `effective_indices()` / `effective_decisions()` as the
   authority for table-rewind prefixes. A completed share can render the final
   effective sequence. Live-history backfill must walk the raw sequence,
   including corrections, to reconstruct index edits for arbitrary and nested
   rewind targets. Add action-rollback and planning-takeback filtering only in
   the player-history index; leave audit replay records intact.
4. **Capture and projection:** observe accepted decisions through
   `ReplayRecorder` instead of duplicating capture calls in each transport.
   Preserve a save-time fallback for mutations without a decision record.
   Capture after each automatic decision, rather than once per timeout batch.
   Use `build_view()` for visibility and `winner_of()` for the outcome; reuse
   projection helpers without routing players through omniscient `state_body()`.
5. **Recovery workers:** run backfill and its expensive merge through the
   existing `run_heavy()` pool. Follow share minting's single-flight and
   request-independent producer lifecycle, including shielding from request
   cancellation. Keep mutable history installation, revision checks, and
   correction invalidation in the history service.
6. **Client follow-up:** extract replay group loading/reconstruction helpers
   for the 30-view buffer and reuse the existing JSON Patch implementation.
   Keep live history's changing index and epochs separate from `useReplay()`'s
   fixed decision-index contract. Reuse board and transport presentation only
   where their assumptions match. This remains outside this backend branch.

Routine reads of captured history use these stored groups and never replay
engine decisions. Seeded reconstruction is reserved for legacy backfill and
repair; it is not the normal reconnect or cache-miss path. Do not add reverse
events, a second patch interpreter, or another decision dispatcher.

New feature-specific code should be limited to live capture, active-index and
rollback policy, save-consistent incremental storage, authenticated history
delivery, and client live-buffer invalidation/navigation. Do not route player
requests through omniscient admin endpoints or public share-token endpoints.

## 1. History model and corrections

Maintain two separate histories:

- **Audit history:** the existing append-only decision log plus immutable
  captured view records. Preserve corrections and abandoned attempts.
- **Player history:** an ordered index referencing captured states currently
  valid for browsing.

Each captured record has an immutable, monotonically increasing `record_id`.
Each player position references a record and includes its phase, round, turn,
timestamp, and associated raw decision count. Never renumber or reuse IDs.
Use the record ID as the public `position_id`; replacements receive a new ID.

Maintain a monotonic `revision` for index changes and an `epoch` that increases
whenever existing player positions are replaced or removed.

- [x] Capture an initial position for games created through REST and draft.
- [x] During each planning phase, maintain one position representing its latest
      state. Replace it after commitments, passes, second-card choices,
      starting-position changes, and takebacks.
- [x] Preserve the final pre-reveal planning position when resolution begins.
      For the decision that triggers revelation, capture its pre-decision state
      as the final planning position and its post-decision state as the first
      resolution position. Do not manufacture a post-commit, pre-reveal state
      that the engine never exposed.
- [x] After planning, append a position after every accepted decision and its
      deterministic processing, including automatic timeout decisions.
- [x] Capture non-decision `advance` operations only if they change the
      canonical historical view. Do not append duplicates for broadcasts,
      reconnects, readiness changes, pointers, pings, or clock ticks.
- [x] Action rollback: remove positions after the exact engine rollback anchor
      and refresh the restored head. Do not append an undo browsing step.
- [x] Planning takeback: replace the current planning position. This preserves
      other players' commitments without retaining the abandoned commitment.
- [x] Table rewind: restore the player index associated with the targeted raw
      decision prefix and refresh its head. Do not append a rewind browsing step.
- [x] Retain internal index edits by raw decision prefix so nested table rewinds
      reproduce the correct branch, including targets omitted from browsing.
- [x] Preserve existing admin replay, override history, and shared replay
      behavior. No separate event-history module exists on this base branch.

Rollback anchors must follow actual `GameSession` snapshot creation and
invalidation, rather than turn numbers or actor changes. The current engine
re-anchors after foreign responses and hidden-information boundaries.

- [x] Expose an explicit rollback-anchor generation identifier on `GameSession`.
      Change it whenever a snapshot is newly created or invalidated; keep it
      across repeated restores to the same anchor.
- [x] Persist the identifier with the rollback snapshot and map it to a captured
      history position. Clear stale mappings when the engine invalidates them.
- [x] Restoring or re-anchoring must never prune another player's valid response
      or cross a hidden-information boundary that the engine protects.

## 2. Capture and canonical views

Add a shared history service used by REST actions, WebSocket actions, automatic
timeouts, starting-position changes, and applied overrides. Do not use broadcast
or result logging as the sole capture hook: some mutations have no SessionResult,
and a timeout batch can contain multiple decisions before one broadcast.

- [x] Capture after each successful individual decision under `game.lock`, after
      deterministic processing and before persistence or broadcast.
- [x] Capture each intermediate result in a multi-decision timeout batch,
      including automatic commit followed by automatic finish-planning.
- [x] Associate captures with raw decision counts, excluding clock telemetry,
      so existing replay and rewind indices retain their meaning.
- [x] Build frozen projections for every seated hero and one spectator,
      including disconnected seats, using `build_view()`. Enumerate the seats
      from the game state, rather than connected sockets. Reuse the prebuilt
      public board during projection; do not rebuild views from event logs.
- [x] Apply visibility before calculating patches. Never call the omniscient
      replay `state_body()` to serve player history.
- [x] Retain historical `view` and `winner`. Omit actionable input requests,
      tokens, connection metadata, and client timing fields.
- [x] Reuse `winner_of()` for historical winner calculation. Keep canonical
      player projection separate from the existing omniscient `state_body()`;
      share neutral envelope construction only if it removes actual duplication.
- [x] Set historical `view.clock` to `null`; retain `time_control`. Historical
      clock playback is outside v1 and must not display a ticking live clock.
- [x] Deep-copy/freeze canonical values so later live mutations cannot modify
      cached or stored historical projections.
- [x] Share projection helpers and board construction with live views. Reuse
      captured bodies only where practical; live clocks and inputs must remain
      current and must not be taken from historical snapshots.

## 3. Storage, durability, and recovery

Use the shared codec extracted from `shares.py`, backed by the existing
`jsonpatch` and Brotli dependencies. Live storage is a new incremental adapter
beneath the game persistence directory; completed shares remain immutable batch
artifacts. Keep the committed history manifest in the existing atomically
replaced game save. Do not rewrite closed groups on every move.

- [x] Use the existing `{start, keyframe, patches}` group representation. Retain
      stable record/base IDs in accompanying metadata so codec offsets are not
      mistaken for raw decision indices or sparse public position IDs.
- [x] Start with a keyframe and use the existing compressed-size budget and
      maximum group length to choose later boundaries. Preserve the share
      defaults: budget multiple 2, size check every 8 patches, and hard maximum
      512 patches. The client's 30-view buffer is independent of keyframe spacing.
- [x] Reuse forward RFC 6902 patch creation and group reconstruction. Store
      canonical viewer projections together inside the server-private payload
      so group compression can exploit common content.
- [x] Deduplicate that payload as one public view and per-seat private overlays
      generated only after applying `build_view()` visibility. Reconstruct the
      public stream and only the authenticated seat's overlay on reads. Keep
      the existing full scoped view / scoped patch-group API response shapes.
- [x] Store groups with the existing Brotli codec and reuse gzip fallback when
      serving encoded groups. Keep compression settings configurable by caller:
      use quality 1 for live tail writes and the existing share quality 9 for
      batch baking. Do not add an unrelated per-record gzip storage format.
- [x] Keep closed groups immutable. Publish each changed active tail as a new
      immutable file version, referenced by the next atomic game save. Delete
      obsolete tail versions only after the replacing manifest commits. This
      bounds rewrites to the open group and preserves old-save recoverability.
- [x] Reconstruct from the nearest group keyframe with the shared codec and
      its bounded patch chain. Keep only the latest projections, open builder,
      and a bounded reconstructed-view read cache in RAM.
- [x] Do not persist reverse patches in v1: clients cache complete views, and
      server reads reconstruct forward from bounded keyframe chains.
- [x] Extend saves with the committed record index, active player index,
      revision, epoch, raw-prefix index edit metadata, and rollback-anchor map.
- [x] Write new immutable files through temporary files and atomic replacement,
      then atomically save game state and the manifest referencing those files.
      Ensure files are flushed before publishing the referencing save.
- [x] On restart, accept only records referenced by the saved manifest; remove
      orphan files left by interrupted operations. Restore history before timers.
- [x] If a record write fails, publish no reference to that record. Mark a
      history gap, log the failure, and continue live gameplay. Start a fresh
      keyframe on the next successful capture.
- [x] If the game save fails, retain pending records in memory for the next save;
      restart remains anchored to the last successful game save, matching the
      restored game state. Do not infer committed history from directory contents.
- [x] Validate missing/corrupt files and patch bases on read. Report unavailable
      ranges rather than returning a wrong board. Attempt replay repair off-loop
      when compatibility permits.
- [x] With persistence disabled, retain equivalent in-memory history for tests
      and ephemeral games; do not promise recovery across server restart.
- [x] Remove sidecars when their game save is removed. Keep existing independent
      replay-log retention unchanged. Use only server-generated, validated paths.

## 4. Authenticated API and live protocol

Use the existing game-scoped bearer authentication. Players receive only their
projection; spectators receive the public projection. Never accept a requested
viewer identity or `reveal_all` flag from the client.

| Endpoint | Behavior |
| --- | --- |
| `GET /games/{game_id}/history` | Page of active position metadata, revision, epoch, total, and availability. Default latest 30; support `before_position_id`; maximum 100. Return entries chronologically. |
| `GET /games/{game_id}/history/state?position_id=...` | Complete historical view, winner, and position metadata. |
| `GET /games/{game_id}/history/frames?from_position_id=...&limit=30` | Keyframe at the requested active position plus forward patches for up to 30 consecutive active positions, with each position's metadata. |

- [x] Accept an expected revision for index and grouped reads; return `409` if
      the index changed and the request must restart.
- [x] Return `410` for superseded positions and `404` for unknown positions.
      Describe unavailable ranges explicitly in the history metadata.
- [x] Build client-facing patch groups exclusively from active positions.
      Internal audit reconstruction may cross abandoned records, but never send
      those records or intermediate patches to the player.
- [x] Use the shared codec to build these scoped groups, reusing the replay
      keyframe/patch envelope and HTTP content-encoding support. Keep active
      position metadata as a history-specific addition; do not expose raw share
      decision metadata, card selections, or other viewers' projections.
- [x] Snapshot read metadata under `game.lock`, read and reconstruct outside the
      lock, then verify the requested positions and epoch remain valid before
      returning. Grouped reads must also validate their expected revision.
- [x] Use private, non-shared caching headers. Key reconstructed-view caches by
      game, viewer, and immutable record ID; bound them to 128 views process-wide.
- [x] Add optional `history` metadata to REST game views and WebSocket
      `STATE_UPDATE`: revision, epoch, latest position ID, its active predecessor,
      active count, and availability. Return a position ID only when the supplied
      live view corresponds to that position after historical normalization.
- [x] Distinguish updates with no new history position from new captured states,
      so readiness and timer updates do not generate duplicate client history.
- [x] Update response models and `docs/CLIENT_INTEGRATION_GUIDE.md` together,
      including pagination, correction invalidation, gaps, and example payloads.

## 5. Client buffer and browsing UI

Implement frontend integration in the companion frontend repository. Its live
socket handler currently replaces `view` from each full `STATE_UPDATE`; events
drive animations and logging, rather than reconstructing the game.

- [ ] Add history API types and a `useGameHistory` hook. Cache at most 30 complete
      historical views by immutable position ID.
- [ ] Extract the keyframe clone, `applyPatches()`, group lookup, and cached
      reconstruction logic from `sharedReplaySource()` into common helpers used
      by both shared replay and live history. Preserve existing share behavior
      and patch aliasing protections; do not write another patch interpreter.
- [ ] Keep `useGameHistory` dedicated to mutable live history. `useReplay()`
      currently assumes fixed metadata and numeric decision indices, so reuse
      compatible navigation/loading primitives without forcing live history
      into that unchanged contract. Do not expose raw replay decisions through
      the new player-history source.
- [ ] Buffer eligible live views with history IDs, normalizing them using the
      same historical rules, including a null clock. Never mutate the live view.
- [ ] If a position's predecessor is missing, fetch that group when browsing
      reaches the gap. One received message need not equal one backend decision.
- [ ] On epoch change, clear history caches and refresh the active index.
      Append-only revisions preserve existing cached positions.
- [ ] Fetch older groups on demand. Retain the displayed position and closest
      neighbors while evicting distant entries to maintain the 30-view bound.
- [ ] Cancel or ignore responses for old epochs, games, or viewers; clear caches
      on seat changes. A `409` refreshes the index; a `410` drops the stale entry.
- [ ] Keep the newest live state separate from the displayed historical state.
      Continue receiving live updates while browsing.
- [ ] Add a History entry point, previous/next controls, position details, and
      Return to live. Adapt `ReplayControls` transport presentation so the same
      controls can navigate either immutable replay indices or active history
      positions; keep raw-decision inputs confined to replay mode. Reuse the
      existing read-only board and applicable roster components.
- [ ] Disable gameplay submissions, selections, pings, and live interaction
      controls while browsing. Keep connection and live-turn notifications.
- [ ] If the displayed position is superseded, return to live with a brief
      explanation. Do not automatically play incoming live animations on the
      historical board.
- [ ] Scope caches to the authenticated viewer and do not persist private view
      data in shared browser storage.

## 6. Existing games and backfill

- [x] When restoring an older save, capture its current state immediately as a
      baseline, then capture new decisions normally.
- [x] Backfill earlier states from a consistent replay prefix in a worker process.
      Reuse `load_replay()`, seeded setup, existing decision application and
      replay iteration/capture hooks, and `run_heavy()`. Reuse the forward render
      pattern from `share_bake.py`; never run expensive reconstruction under the
      live game lock or build an independent reconstruction engine.
- [x] Use a single in-flight producer per game, retained independently of HTTP
      requests and shielded from disconnect cancellation, following the existing
      share-mint orchestration. Reuse live capture and correction/index policy
      while observing the raw replay chronology; filtering to effective decisions
      alone would lose metadata needed for arbitrary rewind-prefix targets.
- [x] Tag baseline/new captures with their raw decision counts. Merge the
      backfilled prefix with live capture metadata atomically; retry the merge
      if a correction changed the epoch while reconstruction was running.
- [x] Build anchor and prefix metadata during backfill so later table rewinds
      into the reconstructed range use the correct effective player history.
- [x] Mark reconstructed ranges as such. Recorded rules and current engine
      compatibility limit backfill fidelity; historical clocks remain absent.
- [x] If reconstruction fails, keep the current baseline and subsequent captures,
      expose the available range, and log the failure. Do not block live play.
- [x] Preserve captured history across engine updates; only backfill/repair uses
      engine simulation. Include a history storage format version for future
      migrations independent of game rules versions.

## 7. Validation and acceptance

- [x] Preserve existing baked-share formats and API behavior through codec
      extraction and run existing share/replay fixtures.
- [ ] During frontend follow-up, extend the existing `sharedReplaySource` /
      JSON Patch tests rather than duplicating those test harnesses.
- [x] Test shared codec batch and incremental builders on the same positions,
      including size-triggered boundaries, the hard patch-chain limit, Brotli
      responses, gzip fallback, and reopen/recovery of the live tail.
- [x] Disconnect and reconnect a player, including a server restart; fetch earlier
      states without relying on any browser-retained history.
- [x] Verify every keyframe/patch chain equals the canonical captured view for
      all viewers; test keyframe boundaries, empty patches, removals, and arrays.
- [x] Test scoped hands/commitments and spectators, including after revelation,
      and compare captured projections with the standard live projections.
      Retain existing view tests for guesses, reveals, tokens, and upgrades.
- [x] Test interleaved planning commitments, takebacks, repeated takebacks, and
      two-card heroes; only one current planning position survives.
- [x] Test rollbacks at real segment anchors, including foreign responses,
      hidden reveals, repeated rollback, and restart with an active anchor.
- [x] Test table rewinds and nested rewinds, including targets in planning,
      previously superseded segments, and reconstructed history.
- [x] Exercise the common accepted-decision capture hook through REST,
      WebSocket, and automatic commit plus finish-planning in one timeout batch.
      Retain existing starting-position and override route tests; those routes
      use the same recorder hook, including operations without a SessionResult.
- [x] Verify client-facing groups do not expose abandoned states via their
      keyframes, patches, labels, or metadata.
- [x] Exercise stale revisions, superseded/unknown IDs, read/correction races,
      interrupted writes, failed saves, orphan files, missing records, and repair.
- [ ] Test client cache misses, eviction, epoch changes, late responses, viewer
      switches, and receiving live updates while browsing.
- [x] Run the complete backend suite with greater than 80% coverage, focused
      engine anchor-lifecycle tests, and Python lint/format/type checks.
      Final run: 3,854 passed; overall branch-inclusive coverage 88.80%, new
      history/codec modules combined 96.58%.
- [ ] During frontend follow-up, run frontend tests, type checks, and production
      build. No frontend source or frontend test changes belong to this branch.
- [x] Benchmark a long ten-player game: record p50/p95 capture latency, cold and
      warm reads, save growth, retained Python memory, and compressed disk usage.
      See `docs/LIVE_HISTORY_VALIDATION.md` for the 700-decision local results.
- [ ] Before production enablement, benchmark on the deployment host against
      the target of less than 10 ms additional p95 decision latency. The local
      run exceeds that target. Reuse projection work and tune capture/save or
      compression/cache costs as required; do not treat the local result as a
      passed deployment gate.

Acceptance: a fresh client can browse all available active history; captured
ranges require no engine replay; browsing never changes or pauses live play;
abandoned attempts stay out of player browsing; audit history remains intact;
and private information remains scoped to the viewer at the historical moment.
