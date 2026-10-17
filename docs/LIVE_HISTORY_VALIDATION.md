# Live history validation

The backend implementation shares replay decision application and the
keyframe/JSON Patch codec with existing replay and share features. Frontend
integration remains in section 5 of `IMPLEMENT_TODO.md`; this branch changes no
frontend source.

## Automated checks

Run from the repository root in WSL Ubuntu, using the existing Python 3.11
development environment (the isolated worktree used the root checkout's
`.venv-wsl`):

```bash
mkdir -p .agent
COVERAGE_FILE=.agent/history-window.coverage .venv-wsl/bin/python -m pytest tests/ -q --cov=goa2 --cov-report=term --cov-report=json:.agent/history-window-coverage.json --cov-fail-under=80.01
```

The full WSL run collected **3,884 tests**: **3,883 passed**, with one
environment-dependent replay verification failure, in **784.79 seconds**.
WSL Git could not read the Windows Git-directory path in this worktree, so
the existing engine-revision test received `unknown`. Providing WSL absolute
`GIT_DIR` and `GIT_WORK_TREE` paths resolved this without application or test
changes. The entire verification module then passed: **8 passed in 63.92
seconds**, including that test. All collected tests passed across these runs.

The rerun used `tests/server/test_replay_verification.py` with the same coverage
options plus `--cov-append`. Final combined coverage is **88.95%**; the enforced
80.01% gate passed on both runs. Coverage includes branches and the entire
`goa2` package. A normal root checkout does not need the worktree Git-path fix.

| New module | Coverage including branches |
| --- | ---: |
| `replay_codec.py` | 100.00% |
| `live_history.py` | 95.42% |
| `routes_history.py` | 97.37% |
| `history_backfill.py` | 91.50% |
| Combined | 95.93% |

Focused history coverage includes authenticated player/spectator access,
frozen projections and private information, planning replacements, action
rollback anchors across restarts, nested table rewinds, durable group recovery,
failed writes/saves, cache isolation, stale reads, replay repair, cancellation,
concurrent live captures, process-pool serialization, and backfill metadata
broadcasts. Existing replay/share tests exercise the common codec through the
original adapters. Timeout tests verify that automatic commit and
finish-planning each capture their own accepted decision. Replay-window tests
cover all three settings, lobby permissions, spectator exemption, both planning
grace periods, two-card heroes and passes, restart/backfill, cached expired
frames, and cutoffs during reconstruction or response compression.

Ruff passes for all source and tests. Black leaves all 514 Python files
unchanged; mypy passes for all 186 application modules. These checks also ran
in WSL.

## Performance follow-up

The measurements below are historical results from the performance follow-up
at `1300268`, before configurable replay windows. They have not been rerun for
the window setting. The original measurement environment used Windows Python.
Reproduce that historical benchmark with:

```powershell
$env:PYTHONHASHSEED='0'
.venv/Scripts/python.exe tools/benchmark_live_history.py --decisions 700
```

The deterministic ten-player workload uses real accepted decisions with the
existing automatic-play HOLD/pass/upgrade choices. It saves after every decision.
Both paired paths append the replay decision and save the same state; execution
order alternates to balance cache/write ordering. Engine resolution, network
delivery, and client rendering are excluded. Each run reached round 6, with
700 accepted decisions and 503 active positions. No tests ran concurrently with
these timing measurements.

The original report of 47.218 ms p95 used a save-only baseline and ran alongside
tests. An isolated run with that original harness reproduced 45.757 ms. The
corrected harness includes the pre-existing replay-log append in both paths,
and retains `save_only_baseline_comparison` for comparison with the old metric.
For a controlled before/after comparison, the original source at `162b681` was
extracted separately and run with the corrected harness and `PYTHONHASHSEED=0`.

| Code / run | Added p50 (ms) | Added p95 (ms) |
| --- | ---: | ---: |
| Original source, matched baseline | 23.204 | 42.593 |
| Optimized, run 1 | 7.004 | 9.575 |
| Optimized, run 2 | 7.082 | 9.521 |
| Optimized, run 3 | 7.107 | 9.794 |

A subsequent confirmation measured 10.394 ms p95. A predefined five-run check
with raw per-decision samples then measured:

| Repeat | Added p95 (ms) |
| --- | ---: |
| 1 | 9.809 |
| 2 | 10.214 |
| 3 | 11.591 |
| 4 | 9.490 |
| 5 | 10.142 |
| Pooled 3,500 decisions | 10.359 |

The pooled p50 was 7.242 ms; 93.74% of decisions added at most 10 ms.
The result is approximately 10 ms p95, an approximately 76% reduction from
the original matched 42.593 ms, but does not establish a consistently sub-10 ms
p95.

Run 1's p95 record-and-save time was 16.265 ms with history, against 7.562 ms
without history. The three conservative save-only comparisons ranged from
9.803 to 10.196 ms p95; the corrected, matched comparisons are in the table.
Paired overhead is calculated per decision before taking the percentile;
subtracting independently calculated p95 values gives a different statistic.

## Bottlenecks and changes

Recorder/save-only profiling identified the following costs. Function-level
timings are inclusive and overlap; profiling timings are not used for the
latency result above.

| Cost in the original implementation | Change |
| --- | --- |
| Rebuilding every viewer projection twice per decision | Successful recorded mutation coordinators pass their starting decision count to persistence to confirm capture already occurred. Direct saves, unrecorded advances, failed mutations, and failed captures retain their fallback. |
| Allocating a complete `GameState` dictionary, then JSON-encoding it again | Use the existing Pydantic native serializer directly, preserving the JSON data, ASCII save encoding, atomic replacement, and serialization-failure cleanup. |
| Rebuilding static card/tile data and repeatedly diffing private deck projections | Reuse frozen hero/card/tile projections and unchanged private subtree patches. Cache inputs include nested card data and planning/reveal context; all seated viewers remain captured. |
| Serializing the open group's keyframe and patch prefix on every save | Encode from cached immutable JSON parts. Keep defensive copies for callers that retain ownership of supplied values. |
| Expensive phase-transition diffs and compressed-size budgeting | Start keyframes at phase boundaries; live groups use a raw-byte budget and maximum 32 positions. Shares retain their compressed-size policy, now evaluated with an incremental compression state. |
| Hashing the full rollback snapshot on each new anchor (about 2.5 ms p95 in stage timing) | Bind the engine's existing anchor generation to its raw replay prefix, persist the binding, and normalize it during backfill. Existing format 2 digest bindings are converted once on restore. |
| Directory scans and redundant immutable-file renames after every decision | Delete known retired tail versions only after commit. Create new hash files exclusively, fsync before publishing the referencing game save, and use atomic replacement for repair. Orphan scanning remains part of restart recovery. |

All captured records remain present. Planning replacements and corrections still
affect only the player index. A nested rewind followed by rollback now also
re-binds to the safe anchor inside the restored prefix rather than a later
refreshed anchor outside it. Missing/truncated replay logs do not reset the
manifest's accepted-decision counter or make captured views unavailable.

## Storage tradeoff and scope

The original matched run stored 684,247 bytes in 13 compressed groups. Optimized
runs stored 1,369,560 bytes in 46 groups. More phase-boundary keyframes trade
approximately twice the disk usage for cheaper capture and shorter read chains.
Brotli quality stays 1 for live writes and 9 for shares. No dependency was added.

The representative optimized save used 672,909 bytes, versus 772,856 before.
The retained Python history graph and read cache used approximately 2.59 MB,
versus 2.17 MB before. This graph estimate excludes native buffers and process
RSS. Read timings use only 20 samples and can include garbage-collection
outliers; they are not the decision-latency acceptance measurement.

These local measurements describe this workload, not a hard latency ceiling
for arbitrary games or deployment hosts. No deployment or frontend rollout is
included. The original 10 ms threshold was an assistant-suggested engineering
target, not an agreed release gate; the follow-up explicitly investigated
reaching it.
