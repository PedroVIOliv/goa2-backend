# Shared decision facts: existing frontend compatibility

The new fields are additive. Existing clients can keep using their current
request fields and submitting the same selections; no frontend rollout is
required before deploying this backend change.

## Scope and revisions

Windows verification on 2026-10-20 used:

- Unchanged frontend default branch (`master`, referred to as main in migration
  discussions): `a3c5e0a46b35a42cd6e054512ce3dbc6a61a579c`.
- Control backend upstream `main`: `a18c66e005ce30dd29a800702d888e8f275209b8`.
- Candidate backend implementation: `26a959b41ea0c44b07d807be7702234c0db9c39f`.

The candidate is based directly on upstream main. It does not include the
separate batch-upgrade/rune-selection PR. The original working checkout's
uncommitted WebSocket reconnect fix and Windows test-path fix were also excluded.

The frontend's existing socket handler stores the server view and input request
without requiring an exact-key schema. Its existing controls read the legacy
fields, ignoring `decision_context` and `battle_zone_minion_counts`. Backend
request IDs, option order, labels, computed values and accepted input shapes are
unchanged. New metadata is not echoed in submissions. Old saved requests without
metadata still deserialize. Counts are derived in views rather than persisted.

## Browser comparison

The layout lab ran the same unmodified frontend commit against each clean
backend checkout in turn. Chromium ran on Windows; services ran in WSL. React
used production semantics (`NODE_ENV=production`), with desktop presentation and
no userscript. All checks used the shared situation library from lab commit
`3275328` and 1440 x 900 viewports. Three-dimensional scenes ran one at a time.

| Situation | Shared situation ID | Renderer |
| --- | --- | --- |
| Arien chooses an action | `e6cf117c8910` | 2D and 3D |
| Brogan chooses a defense | `2b928b7b0ab4` | 2D and 3D |
| Brogan discards a card | `30735050fbde` | 2D and 3D |
| Arien chooses one tier II upgrade | `7596eb876af3` | 2D |
| Snorri chooses an inscription rune | `0601f17bbdab` | 2D |
| Gydion chooses a spell | `dbd50506df47` | 2D |

For each case, compare the complete scoped view and input request after removing
only the two new fields and per-run `request_id`. Compare visible button text,
accessible labels and disabled states as well. For action, defense and discard,
click an existing frontend control in each renderer: require exactly one
`SUBMIT_INPUT`, the original request ID, an accepted server reply, and an updated
request. Compare the selected value across the control and candidate runs.
Record runtime/asset/restore diagnostics and inspect screenshots.

All nine comparisons passed with identical legacy views, requests and controls.
The six action/defense/discard submissions (three situations in two renderers)
were accepted in each backend run with matching values and request correlation.
All checked views had zero runtime errors and zero restore warnings. The new
action, defense, rune and spell metadata was present in candidate responses while
the old frontend continued to use its legacy fields. Representative 2D and 3D
screenshots were inspected.

Use the layout lab's comparison skill and `GOA2_LAB_BACKEND` to point each run at
its clean backend checkout. Pin both frontend refs to the frontend SHA above,
use the correct owning hero from each saved situation, and use Synchronize None.
With the Windows WSL adapter, export `NODE_ENV` through `WSLENV` as well. Keep
the two backend runs sequential and use isolated service ports. This production
React setting avoids the pre-existing development StrictMode reconnect race;
it does not change frontend source or apply the local server fix.

The diagnostic JSON and screenshots remain local under the frontend's ignored
`node_modules/.cache/shared-facts-pr/`. They contain runtime snapshots rather than
portable curated situations and are not committed as fixtures.

## Automated checks and limits

- Windows domain/engine suite: **3,266 passed**.
- Server suite plus focused serialization, counts and emitter checks:
  **525 passed, 1 failed**. The failure is
  `tests/server/test_map_paths.py::test_valid_map_name_resolves`, whose hard-coded
  forward-slash suffix also fails on unchanged upstream main on Windows. It is
  unrelated to these fields; the existing local fix was deliberately excluded.
- Ruff passed for all changed Python files; the PR diff passed whitespace checks.
- Existing tests cover additive serialization, old saved requests, recipient
  filtering, hidden source identities, simultaneous requests, real emitter facts,
  and physical minion membership/counting.

The development StrictMode reconnect race was reproduced on control backend
main before switching the browser comparison to production React semantics.
This change does not fix that race. No Linux test suites ran. Representative
desktop compatibility does not establish exhaustive gameplay, mobile device
acceptance, or simultaneous multi-scene 3D performance.
