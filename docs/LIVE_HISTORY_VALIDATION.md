# Live history validation

The backend implementation shares replay decision application and the
keyframe/JSON Patch codec with existing replay and share features. Frontend
integration remains in section 5 of `IMPLEMENT_TODO.md`; this branch changes no
frontend source.

## Automated checks

Run from the repository root, using the existing development environment:

```powershell
New-Item -ItemType Directory -Force .agent | Out-Null
$env:COVERAGE_FILE='.agent/history-release.coverage'
.venv/Scripts/python.exe -m pytest tests/ -q --cov=goa2 --cov-report=term --cov-report=json:.agent/history-release-coverage.json --cov-fail-under=80.01
```

Final run: **3,854 tests passed in 820.63 seconds**, with **88.80% coverage**.
The enforced 80.01% gate passed. Coverage includes branches and the entire
`goa2` package, rather than just the new feature.

| New module | Coverage including branches |
| --- | ---: |
| `replay_codec.py` | 100.00% |
| `live_history.py` | 96.64% |
| `routes_history.py` | 97.94% |
| `history_backfill.py` | 92.15% |
| Combined | 96.58% |

Focused history coverage includes authenticated player/spectator access,
frozen projections and private information, planning replacements, action
rollback anchors across restarts, nested table rewinds, durable group recovery,
failed writes/saves, cache isolation, stale reads, replay repair, cancellation,
concurrent live captures, process-pool serialization, and backfill metadata
broadcasts. Existing replay/share tests exercise the common codec through the
original adapters. Timeout tests verify that automatic commit and
finish-planning each capture their own accepted decision.

Ruff and Black checks pass for all 23 changed Python files. Mypy passes for the ten changed
codec, projection, history, replay, share, model, and registry modules checked
with `--follow-imports=silent`.

## Local performance measurement

Reproduce with:

```powershell
.venv/Scripts/python.exe tools/benchmark_live_history.py --decisions 700
```

The deterministic ten-player workload uses real accepted decisions with the
existing automatic-play HOLD/pass/upgrade choices. It saves after every
decision and compares a paired save of the same state without history. Engine
resolution time is excluded. A local Windows run during other test activity
reached round 6, with 700 decisions, 503 active positions, and 13 stored groups:

| Operation | p50 (ms) | p95 (ms) |
| --- | ---: | ---: |
| Capture | 9.344 | 13.921 |
| Save including history | 28.274 | 39.239 |
| Record and save | 37.871 | 59.214 |
| Paired baseline save | 12.585 | 14.615 |
| Paired additional history cost | 25.391 | 47.218 |
| Cold single-position read | 40.783 | 84.048 |
| Warm single-position read | 5.248 | 10.196 |
| Materialize up to 30 views | 240.729 | 293.693 |

Compressed history used 682,237 bytes; the final game save used 772,829 bytes.
The retained Python history object graph was approximately 2,169,604 bytes.
That graph estimate excludes native buffers and process RSS. It is not a
deployment capacity estimate. Group materialization timings exclude HTTP
delivery and are separate from decision latency.

The provisional target of less than 10 ms additional p95 decision latency is
**not met by this local measurement**. Before enabling this feature in
production, benchmark on the deployment host and tune capture/save work or
compression as required. No deployment or frontend rollout is included here.
Private overlays reduce duplication in stored groups; they do not eliminate
the cost of generating and durably saving each historical view.
