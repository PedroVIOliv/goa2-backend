# Maintainability Roadmap

> **Status:** active plan · **Created:** 2026-06-30 · **Owner:** backend
>
> **What this is:** a self-contained execution plan for making the GoA2 backend
> easier to maintain long-term. It was produced by an 8-dimension audit in which
> every finding's `file:line` evidence was independently re-verified against the
> code by a separate skeptical pass (43 of 44 findings confirmed; 1 rejected as
> overstated). You can trust the citations, but **always re-open the cited file
> before editing** — line numbers drift as the code changes.
>
> **How to use this doc (new agent, start here):**
> 1. Read **§0 Orientation** first — some of the repo's own docs (CLAUDE.md,
>    CODEBASE_MAP.md) are factually wrong and will misdirect you. §0 is the
>    corrected ground truth.
> 2. Read **§1 The Vision** to understand *why* these fixes cluster the way they do.
> 3. Use **§2 Priority Matrix** to pick what to do. **Default: execute Column ①
>    (Quick Wins) first** — top to bottom. It's ~1 day and removes the most risk.
> 4. **§3 Findings Catalog** is the detail for every item (problem / evidence / fix / effort).
> 5. **§4 Execution Playbook** has copy-pasteable starting steps for Column ①.
> 6. Update this doc as you go: check items off, add a `DONE (date, commit)` note.

---

## §0 Orientation — corrected ground truth

This repo is **Guards of Atlantis II (GoA2) backend**: a deterministic, stack-based
hex game engine + a FastAPI server. Python 3.11, Pydantic v2. ~135 source files,
~194 test files. Dependency/build via `uv`. Tests: `PYTHONPATH=src uv run pytest tests/ -q`.

**⚠️ The repo's own onboarding docs contain false statements. Believe this section
over CLAUDE.md / AGENTS.md / GEMINI.md / CODEBASE_MAP.md where they conflict:**

| Claim in repo docs | Reality |
|---|---|
| "Hero card logic lives in `src/goa2/data/heroes/` and `engine/effects.py`" (CLAUDE.md:95) | **FALSE.** Hero effect logic (`@register_effect` classes) lives in **`src/goa2/scripts/*_effects.py`** (23 files). `data/heroes/*.py` holds only static Card/Hero **data**; `engine/effects.py` is just the `CardEffect` base + registry. |
| "Add each new step to the `AnyStep` union in `step_types.py` — the #1 pitfall" (CLAUDE.md:155,233,264) | **STALE.** Since commit `7c46eee` (~2026-05-05) the union is **auto-derived** by reflection (`step_types.py:_registered_union` + `_all_subclasses`, lines 36–93). Two CI tests guard it (`test_persistence.py:235`, `:329`). You do **not** hand-edit a `Union[...]`. |
| "`engine/steps.py` — 50+ GameStep subclasses (~3700 lines)" (CODEBASE_MAP.md:86; CLAUDE.md:63) | **GONE.** `engine/steps/` is now an **11-file package** (`base/cards/combat/movement/selection/utility/markers/reactions/phases/effects/__init__`). |
| CODEBASE_MAP lists 5 heroes, omits `server/` | **STALE.** 25 hero data files, 23 effect scripts; `server/` (15 files) is the primary deliverable. |

**How effects load:** `server/app.py:register_all_effects()` (lines ~38–49) **globs**
`scripts/*_effects.py` and `importlib.import_module`s each inside
`except Exception: logger.warning(...)`. A broken hero module is therefore silently
skipped, and a missing effect is treated downstream as a no-op
(`cards.py:1189` → `is_finished=True`). This "silent failure" is a recurring theme below.

**The two real residual footguns when adding a step** (not the obsolete union edit):
1. Forgetting to override `type` → defaults to `StepType.GENERIC` → silently dropped from the serialization union.
2. Adding a nested `list[GameStep]` / `list[FilterCondition]` field → must be hand-added to
   `rebuild_serialization_models()` (`step_types.py:165–202`), which has **no completeness test**.

---

## §1 The Vision — what we're actually optimizing for

Every fix serves one of **two goals**. The 44 findings stop being a chore list once you see them:

1. **Shrink the distance between a mistake and its discovery.** Today many bugs surface
   three playtests later (or in a frontend dev's report) instead of at your keyboard.
   Target: the codebase tells you *immediately* — at import, type-check, or test time.
2. **Shrink the distance between intent and location.** Today "change Garrus" or "where does
   the engine decide what action fires?" is a scavenger hunt across 5 files / 3 packages.
   Target: you know where to go on the first try, and the map you read is true.

These express as **five themes**. Each finding in §3 is tagged with its theme.

- **T1 — The map matches the territory.** Docs are this repo's *agent system prompt*; wrong
  docs misdirect every human and AI session. Fixing them is the cheapest high-leverage work here.
- **T2 — Fail loud, never silent.** Convert every silent degradation (swallowed import,
  `GENERIC` default, mistyped context key, drifted contract) into an early, loud crash.
  The system should never run quietly-broken.
- **T3 — Machine checks replace human discipline.** Rules that live in CLAUDE.md as
  "remember to…" should live as failing tests (contract snapshots, coverage floor, real mypy,
  context-key producer/consumer check). You shouldn't be *able* to merge the mistake.
- **T4 — One concept, one home, dependencies one way.** Effect logic belongs in a first-class
  package, not `scripts/`. The engine must not import from hero scripts. A hero should be one place.
- **T5 — Make the common change cheap.** Shared effect recipes, a branching primitive, and a
  de-monstered `ResolveCardStep` so new mechanics are *additive*, not surgery.

**The encouraging part:** the core engine design ("logic as data" stack) is sound, the big hero
files are cohesive (not grab-bags), and the serialization burden was already auto-fixed. Most of
this work is removing silent-failure modes and doc rot that sit *on top of* a good architecture.

---

## §2 Priority Matrix — time vs. importance

Override rule: **anything bleeding right now jumps the queue.** Otherwise sequence by quadrant.

```
              LOW EFFORT (S, hours)          HIGH EFFORT (M/L, days–weeks)
            ┌──────────────────────────────┬──────────────────────────────┐
   HIGH     │  ① QUICK WINS — do first     │  ② BIG BETS — one per cycle   │
 IMPORTANCE │  (best value/effort)         │  (foundational, plan them)    │
            ├──────────────────────────────┼──────────────────────────────┤
   LOWER    │  ③ FILL-INS — opportunistic  │  ④ DEFER — only when adjacent │
 IMPORTANCE │  (cheap, do while nearby)     │  (real, not worth a sprint)   │
            └──────────────────────────────┴──────────────────────────────┘
```

**The one-line rule:** Ship **Column ①** this week (≈1 day; kills the live bug + worst silent
failures + doc rot). Then **one ② per cycle**, starting with contract tests, then API versioning.
Sprinkle **③** as you pass through those files. Ignore **④** until you're already there.

### ① Quick Wins — do this week (all effort **S**)
| # | Item | Theme | Status |
|---|---|---|---|
| QW1 | Fix `"SKIP"` vs `null` skip-contract bug | T2/T3 | ✅ DONE (2026-07-02, 2d5655b) |
| QW2 | Declare `python-dotenv` dependency | T2 | ✅ DONE (2026-07-02, e40f089) |
| QW3 | Add `__all__` to `engine/steps/__init__.py` | T3 | ⏸ DEFERRED to DF3 — pure prep for full `--strict` (deferred); adds per-step upkeep with no active CI benefit today. Revisit with DF3. |
| QW4 | Fix CLAUDE.md (effect location + stale union pitfall) | T1 | ✅ DONE (2026-07-02, 5243556) |
| QW5 | Fix/banner CODEBASE_MAP.md; collapse CLAUDE/AGENTS/GEMINI triplication | T1 | ✅ DONE (2026-07-02, 3daa91b) — AGENTS.md/GEMINI.md now symlink CLAUDE.md |
| QW6 | Add `--cov-fail-under` to CI | T3 | ✅ DONE (2026-07-02, 8d2bf25) — floor 80 (current 84%) |
| QW7 | `__init_subclass__` guard against forgotten `type` (GENERIC) | T2 | ✅ DONE (2026-07-02, 4b9c8a7) — via `__pydantic_init_subclass__` |
| QW8 | Add CI `concurrency` block + branch filter | — | ✅ DONE (2026-07-02, 134fce8) |

### ② Big Bets — schedule one per cycle (effort **M/L**)
| # | Item | Theme | Effort |
|---|---|---|---|
| BB1 | Contract snapshot tests + OpenAPI export in CI | T3 | M |
| BB2 | API versioning (`/v1` or `contract_version` field) | T3 | M |
| BB3 | Typed `ExecutionContext` (start with `TypedDict`) | T2 | M→L |
| BB4 | Promote `scripts/` → first-class fail-loud package | T2/T4 | L |
| BB5 | Invert engine→scripts dependency + import-lint guard | T4 | M |
| BB6 | Refactor `ResolveCardStep.resolve` into dispatch table | T5 | L |
| BB7 | Shared effect recipes + `ChooseOneStep`/`IfStep` primitives | T5 | L |

### ③ Fill-ins — opportunistic (effort **S**)
| # | Item | Theme |
|---|---|---|
| FI1 | Archive ~12 stale `plan_*.md` docs into `docs/archive/` | T1 |
| FI2 | Document missing event/input types in client guide | T1/T3 |
| FI3 | Fix skill's filter-import path (facade vs split modules) | T1 |
| FI4 | Rename PR-numbered test files (`test_silverarrow_pr3.py`) | T1 |
| FI5 | Type `pending_input` as `dict[str, Any]` | T2 |
| FI6 | Add completeness test for `rebuild_serialization_models` patch list | T2/T3 |

### ④ Defer — only when already in that area (effort **M/L**)
| # | Item | Theme |
|---|---|---|
| DF1 | Independent `UnitID`/`HeroID` NewTypes + `get_entity` overloads | T2 |
| DF2 | Split economy/upgrade subsystem out of `cards.py` | T4 |
| DF3 | Full mypy `--strict` ratchet (QW3 already gets the big drop) | T3 |
| DF4 | Consolidate the three test layouts into `tests/engine/effects/cases/` | T4 |
| DF5 | Backfill under-tested heroes (garrus has NO test file; whisper 70%) | T3 |

---

## §3 Findings Catalog (detail)

Each entry: **Problem · Evidence (verified file:line) · Fix · Effort**. Re-open files before editing.

### Column ① — Quick Wins

#### QW1 · `"SKIP"` vs `null` skip-contract bug  🔴 LIVE · T2/T3 · S
- **Problem:** The client guide tells clients to skip optional selections by submitting `null`,
  but the engine only skips on the string `"SKIP"`. A `null` selection fails the skip check,
  then fails candidate validation, so the step **re-requests input forever** — any client
  following the guide hangs.
- **Evidence:**
  - `docs/CLIENT_INTEGRATION_GUIDE.md:883–885` — "skip by submitting null as the selection"
  - `src/goa2/engine/steps/selection.py:220` — `if selection == "SKIP" and not self.is_mandatory:` (only skip path)
  - `selection.py:218,232` — `None` falls through (≠ "SKIP", not in candidates) → re-request
  - `selection.py:377` — `if selection in ("DONE", "SKIP")` confirms the string-sentinel convention
  - CLAUDE.md itself says clients submit `"SKIP"` (string), not null — the two docs disagree.
- **Fix:** Correct the guide to state the skip sentinel is the literal string `"SKIP"` (and
  `"DONE"` for multi-select completion). Add a test driving `SelectStep` with `selection="SKIP"`
  and with `selection=None`, asserting only the former skips. Optionally define a `SKIP` constant
  in `domain/input.py` referenced by both engine and the guide so it can't drift.

#### QW2 · `python-dotenv` is imported but not declared · T2 · S
- **Problem:** `server/app.py` imports `dotenv` at module top, but `pyproject.toml` doesn't list
  it. It resolves only transitively via `uvicorn[standard]`. If that extra ever trims it, or
  uvicorn is installed without `[standard]`, the server fails to import with `ModuleNotFoundError`.
- **Evidence:**
  - `src/goa2/server/app.py:12` — `from dotenv import load_dotenv` (unconditional)
  - `src/goa2/server/app.py:35` — `load_dotenv()` at module scope
  - `pyproject.toml:7–11` — deps are only fastapi, pydantic, uvicorn[standard]
  - `uv.lock` — python-dotenv appears only under uvicorn's `standard` extra
- **Fix:** Add `python-dotenv>=1.0` to `[project].dependencies`; run `uv lock`. Direct imports get direct declarations.

#### QW3 · `engine/steps/__init__.py` has no `__all__` · T3 · S
- **Problem:** The package re-exports ~60 step classes but defines no `__all__` (the sibling
  `engine/filters.py` does). Under strict mypy this alone produces 402 `attr-defined` +
  most of 418 `no-untyped-call` errors — ~800 of the 1,000 strict errors — masking the real ones.
- **Evidence:**
  - `src/goa2/engine/steps/__init__.py` — re-export block with `# noqa: F401`, `grep -c __all__` = 0
  - `src/goa2/engine/filters.py` — has `__all__` (inconsistent)
  - `mypy src --strict` → 402 attr-defined, all referencing `goa2.engine.steps`
- **Fix:** Add an explicit `__all__` listing the re-exported names (mirror `filters.py`). This single change makes the remaining strict errors actionable (prerequisite for DF3).

#### QW4 · CLAUDE.md misstates effect location and teaches an obsolete pitfall · T1 · S
- **Problem:** See §0. CLAUDE.md sends readers/agents to the wrong package for the most common
  change (editing a hero) and teaches a manual union-edit that was automated 8 weeks ago.
- **Evidence:**
  - `CLAUDE.md:95` — wrong effect location · `CLAUDE.md:306` — garbled `scripts/` label
  - `CLAUDE.md:155,233,264` — obsolete "add to AnyStep union" pitfall
  - `src/goa2/engine/step_types.py:49–93` — auto-derivation (`_registered_union`)
  - `docs/CODEBASE_MAP.md:108` — correctly says scripts/ = "Card effect implementations" (contradicts CLAUDE.md)
- **Fix:** Point CLAUDE.md to `scripts/*_effects.py` as the home of effect logic. Replace the
  stale union pitfall with the two real footguns (§0). Reconcile with CODEBASE_MAP.

#### QW5 · CODEBASE_MAP stale; CLAUDE/AGENTS/GEMINI triplicated · T1 · S
- **Problem:** README points to CODEBASE_MAP as the architecture reference, but it describes a
  `steps.py` file that's now a package, single `filters.py`/`validation.py` (now split 6/8 ways),
  5 heroes, and omits `server/`. Separately, CLAUDE/AGENTS/GEMINI.md are near-verbatim hand-synced
  copies (so guidance must be updated 3×) and all carry the same stale `engine/steps.py` references.
- **Evidence:**
  - `docs/CODEBASE_MAP.md:2–3` — `last_mapped: 2026-02-05` · `:86` steps.py · `:92–93` single filters/validation · `:99–112` 5 heroes
  - `wc -l` CLAUDE.md 323 / AGENTS.md 324 / GEMINI.md 323; diffs are header + ~1 line
- **Fix:** Regenerate CODEBASE_MAP (Cartographer skill) or add a stale banner + corrected
  package layout. Make one canonical agent file (e.g. AGENTS.md) and turn the other two into
  thin pointers/symlinks. Fix the stale `engine/steps.py` references in all of them.

#### QW6 · Coverage configured but never gated · T3 · S
- **Problem:** `pytest-cov` + `[tool.coverage.run] branch=true` are configured, but CI runs bare
  `pytest -q` with no `--cov-fail-under`. Coverage can silently regress (e.g. 83%→60%) green.
- **Evidence:**
  - `pyproject.toml:45–47` coverage config · `:56` pytest-cov dev dep
  - `.github/workflows/ci.yml:36` — `uv run pytest tests/ -q` (no `--cov`)
  - `.pre-commit-config.yaml` pytest hook — also no `--cov`
- **Fix:** Measure current %, then add `--cov=goa2 --cov-branch --cov-fail-under=<baseline>` to the
  **CI** step (keep pre-push fast). Ratchet up over time.

#### QW7 · `StepType.GENERIC` default → forgotten `type` silently drops a step · T2 · S
- **Problem:** `GameStep.type` defaults to `StepType.GENERIC`, which `_registered_union` excludes.
  A new subclass that forgets `type = StepType.X` runs and passes most tests but is absent from the
  serialization union → round-trip breaks. The collision test only catches *duplicate* GENERICs.
- **Evidence:**
  - `src/goa2/engine/steps/base.py:33` — `type: StepType = StepType.GENERIC`
  - `src/goa2/engine/step_types.py:118` — `ignored_tags={StepType.GENERIC.value}`
  - `tests/engine/test_persistence.py:216–232` — collision-only check
  - *(Note: `test_step_registry_covers_concrete_step_classes` at :235 WOULD catch a direct concrete subclass; the guard is incidental.)*
- **Fix:** Add `__init_subclass__` on `GameStep` that raises if a concrete subclass leaves
  `type == GENERIC` — turns a silent persistence bug into a loud import-time error.

#### QW8 · CI runs on every push, no concurrency cancel · — · S
- **Problem:** `ci.yml` triggers on bare `push:`+`pull_request:` with no branch filter and no
  `concurrency` block; rapid pushes pile up and PR branches double-run.
- **Evidence:** `.github/workflows/ci.yml:3–5` (triggers), `:7–9` (no concurrency)
- **Fix:** Add `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`; scope
  push to `branches: [main]` so feature branches run once via the PR.

### Column ② — Big Bets

#### BB1 · Client contract defended only by a hand-edited doc · T3 · M
- **Problem:** Frontend depends on `server/models.py`, `domain/input.py` (`InputRequest.to_dict()`),
  `domain/events.py`, `domain/views.py` (`build_view()`). None are pinned by a contract/snapshot
  test or generated schema; the only source of truth is the 1,291-line CLIENT_INTEGRATION_GUIDE.md.
  The richest payloads are `dict[str, Any]`, so even FastAPI's OpenAPI can't describe them. A
  renamed/removed field ships green. (This is the root cause that produced QW1 and the missing-enum drift.)
- **Evidence:**
  - `.github/workflows/ci.yml:26–36` — only ruff/black/mypy/pytest; no schema check
  - `src/goa2/server/models.py:53–66` — `view: dict[str, Any]`, `events: list[dict[str, Any]]`
  - `src/goa2/domain/views.py:70–86` — 13-key dict literal = de-facto schema, untyped/untested as a whole
  - `src/goa2/domain/input.py:168–288` — hand-rolled `to_dict()` serializer, per-type key sets + context merge
  - `tests/domain/test_views.py:558` — "all top-level fields" test omits tokens/board_entities/etc. (membership, not exact set)
- **Fix:** Snapshot-test `build_view()` and `InputRequest.to_dict()` (per request type) against
  committed JSON (e.g. syrupy). Dump `app.openapi()` to a checked-in `openapi.json` and fail CI on
  unacknowledged change. Tighten the top-level-fields test to assert the exact key set.

#### BB2 · No API versioning · T3 · M
- **Problem:** Routes mount at bare `/games`, `/heroes`, `/drafts`; no `version`/`contract_version`
  in any response or WS message (only internal `SAVE_VERSION` in persistence). Clients can't detect
  which contract they're on → only migration path is a hard synchronized cutover.
- **Evidence:** `routes_games.py:35` (`prefix="/games"`), `app.py:88` (version is docs metadata
  only), `ws.py:33–41` (STATE_UPDATE has no version), `persistence.py:25` (internal only)
- **Fix:** Add a version point before more clients exist — URL prefix `/v1/...` or a top-level
  `contract_version` on responses + the WS STATE_UPDATE message. Bump on breaking change.

#### BB3 · `execution_context: dict[str, Any]` — untyped engine data bus · T2 · M→L
- **Problem:** Every step communicates through this dict — 27 string keys, ~60 read sites. mypy
  can't verify a key exists, was produced upstream, or has the right type. Authors compensate with
  manual `int(...)`/`cast(...)`. Key typos and producer/consumer ordering bugs are invisible until
  playtest. The team's own `effect_authoring_improvements.md` (A2) calls this "the scariest property."
- **Evidence:**
  - `src/goa2/domain/state.py:71` — `execution_context: dict[str, Any]`
  - `src/goa2/engine/steps/base.py:53` — `resolve(..., context: dict[str, Any])`
  - `src/goa2/engine/steps/combat.py:67,72` — defensive `int(context.get(...))`
  - `src/goa2/engine/steps/cards.py:631–632` — `cast(...)` with misleading "Type safe access" comment
- **Fix:** Start with a `TypedDict(total=False)` enumerating known keys + named key constants
  (annotation-only, no runtime change — catches typos and type mismatches). Optionally evolve to a
  typed `ExecutionContext` object later. Pairs with FI6 and the A2 producer/consumer test.

#### BB4 · Core logic in `scripts/`, loaded by glob with swallowed exceptions · T2/T4 · L
- **Problem:** The largest, most-changed body of domain logic (~600KB across 23 files) lives in a
  package named `scripts/` and is discovered by filesystem glob with `except Exception: warning`.
  A syntax/import error in one hero silently de-registers all its effects; a missing effect is a
  no-op downstream. Correctness of game content rides on fragile implicit discovery with no fail-fast.
- **Evidence:**
  - `src/goa2/server/app.py:40–46` — glob + import each in `except Exception` → warning
  - `src/goa2/server/app.py:49` — registration is an import side effect
  - `src/goa2/engine/effects.py:303–310` — `@register_effect` registers on import
  - `src/goa2/engine/steps/cards.py:1189–1192` — missing effect → `logger.debug` + `is_finished=True`
- **Fix:** Promote effects to a first-class package (e.g. `goa2/effects/<hero>.py` or co-located
  `data/heroes/<hero>/effects.py`) with an explicit `__init__` import list (like `data/heroes/__init__.py`
  already does) so import failures crash at startup. Add a startup assertion that every card's
  `effect_id` resolves to a registered `CardEffect`. (Do BB5 alongside — same area.)

#### BB5 · Engine imports from a hero script (layering inversion + cycle) · T4 · M
- **Problem:** `engine/filters_hex.py` lazy-imports `_has_tide_of_darkness` from
  `scripts.dodger_effects` in three filters; `dodger_effects.py` imports `filters_hex` back — a real
  circular dependency hidden behind function-local imports. One hero's ultimate is baked into three
  generic, reusable targeting filters.
- **Evidence:**
  - `src/goa2/engine/filters_hex.py:229,266,297` — `from goa2.scripts.dodger_effects import _has_tide_of_darkness`
  - `src/goa2/scripts/dodger_effects.py:19` — imports `filters_hex` (the other half of the cycle)
  - `whisper_effects.py:702` — also imports a private helper from `dodger_effects` (cross-hero coupling)
- **Fix:** Move the predicate into the engine — model "all spaces are battle-zone / friendly-spawn"
  as a generic flag on `GameState`/`active_modifiers` (or an `engine/aura_queries.py` helper) that
  filters read. Dodger sets the flag; filters read it. Add a ruff `flake8-tidy-imports` ban (or
  import-linter contract) on `goa2.scripts` inside `goa2.engine` so it can't recur.

#### BB6 · `ResolveCardStep.resolve` — 317-line, 11-level method on the hot path · T5 · L
- **Problem:** The single most complex method in the engine (`cards.py:503`) fuses six jobs:
  guards, option-menu building (+ two closures), input-request return, BEFORE_* passive fan-out,
  per-action dispatch (`if/elif act_type`), and AFTER_* passive fan-out. Every new action type or
  passive hook performs surgery here, and you must understand all six jobs to touch one. The `CLEAR`
  action has a ~30-line implementation inlined into the switch; attack-range logic is duplicated.
- **Evidence:**
  - `src/goa2/engine/steps/cards.py:503` resolve start → ~809 input return
  - `:530,:561` two closures (`is_action_available`, `compute_option`) defined inside resolve
  - `:660–668` BEFORE_* derivation · `:670–731` action dispatch · `:733–807` AFTER_* fan-out
  - `:685–692` and `:774–786` — duplicated attack-range computation
  - `:804` comment "Must be last" — implicit ordering that a refactor must preserve
- **Fix:** Extract guards, option-building, and choice-request into helpers. Replace the action
  `if/elif` with an `ActionType → handler` **dispatch table** (registry of small per-action functions),
  and turn the BEFORE/AFTER trigger fan-out into **data tables** (`{ActionType: PassiveTrigger}`).
  `resolve()` becomes ~30 lines of orchestration: `before → action → after → resolve-card`. New
  actions become a new handler function (additive); they never re-open `resolve`. **Must be done
  behind the existing test suite with characterization tests pinning current behavior + ordering first.**

#### BB7 · No shared recipes; no branching primitive · T5 · L
- **Problem:** 327 of 398 effects subclass `CardEffect` directly; only 94 reuse via inheritance.
  Recurring idioms ("move minion up to N", "count-adjacent → retrieve from discard", backstab attack)
  are re-derived in 10–16 files — a rules fix means N edits. There's no branching composite, so
  "choose one — A/B" cards cost ~90 flat lines of manual `active_if_key` threading (one typo silently
  disables a branch). The team's own backlog specs both fixes (A5 recipes, A1 ChooseOne/If); neither built.
- **Evidence:**
  - `docs/effect_authoring_improvements.md:101–121` (A1 branching), `:125–158` (A2/A3 keys), `:177–188` (A5 recipes)
  - `src/goa2/scripts/xargatha_effects.py:268–510` — charm/control/dominate differ only by a filter list + one flag
  - `src/goa2/scripts/mortimer_effects.py` — 7 near-parallel local `_*_choice_steps` helpers to manage branching
  - `.claude/skills/goa2-card-effects/SKILL.md:722–774` — documents the manual branching idiom as the supported pattern
- **Fix:** Implement A5 — `scripts/recipes.py` (or `engine/effect_recipes.py`) with tested step-list
  builders for the 3–4 idioms used by 3+ heroes; collapse charm/control/dominate to one parameterized
  base. Implement A1 — additive `ChooseOneStep(options=[(label,[steps])...])` and
  `IfStep(condition_key, then, else)`. Update SKILL.md section 13.

### Column ③ — Fill-ins (do when you're already in that file)
- **FI1** Archive ~12 completed/abandoned plan docs (`plan_*.md`, `refactor_plan_*.md`,
  `*_IMPLEMENTATION_PLAN.md`, `CLIENT_READINESS_ROADMAP.md`, `effect-system-implementation-checklist.md`,
  `state_synchronization_issue.md`) into `docs/archive/` with a "superseded" header; add `docs/README.md`
  index distinguishing current vs archived. (`CLIENT_READINESS_ROADMAP.md:5,25` still frames shipped work as open.)
- **FI2** Document undocumented enum values in the guide: events `CARD_RETRIEVED`/
  `ITEM_GAINED`/`MINION_PROTECTED` (`events.py:44–47`), inputs `SELECT_NUMBER`/`SELECT_UNIT_OR_TOKEN`
  (`input.py:36,39`), the `team:COLOR` player_id format, and the `"SKIP"` sentinel. Better: generate the
  guide's enum tables from the `StrEnum`s and fail CI on a missing value.
- **FI3** Skill + EFFECT_AUTHOR_REFERENCE tell authors to import filters from the `goa2.engine.filters`
  facade, but 0 of 27 scripts do (all import from split `filters_*` modules). Pick one convention and
  align docs+code. (`SKILL.md:32–36,1409`; `engine/filters.py` is a 142-line hand-curated facade.)
- **FI4** Rename PR-numbered test files (`test_silverarrow_pr2..pr5.py`) to feature-descriptive names.
- **FI5** Type `GameStep.pending_input` as `dict[str, Any] | None` (`base.py:36`; it's always dict-shaped per `handler.py:32,34`).
- **FI6** Add a guard test that introspects every concrete step/filter/relevant model for nested
  `list[GameStep]`/`list[FilterCondition]`/`list[Any]` fields and asserts each is patched in
  `rebuild_serialization_models` (`step_types.py:165–202`) — the one hand-maintained list with no completeness check.

### Column ④ — Defer (real, low ROI; only when adjacent)
- **DF1** `UnitID = HeroID = BoardEntityID` are the same `NewType` (`domain/types.py:3–5`), so cross-kind
  misuse is unflagged; `get_entity -> Any | None` (`state.py:287`, 45 call sites) erases attribute checking.
  Make independent NewTypes or collapse to one name; add `@overload`s to `get_entity`.
- **DF2** `cards.py` mixes economy (`GainCoins/GainItem/StealCoins`, lines ~1018–1084) and progression
  (`ResolveUpgrades/RoundReset`, ~1292–1378) into the card-lifecycle file. Split into `economy.py`/`progression.py` (keep `__init__` re-exports).
- **DF3** Full mypy `--strict` ratchet. After QW3 drops ~800 errors, enable `warn_return_any` (15 fixes),
  then `disallow_untyped_defs` (~85, mostly trivial `-> None`), gated per-module via `[[tool.mypy.overrides]]`. `strict=false` today (`pyproject.toml:39–43`) means mypy passes vacuously.
- **DF4** Three parallel effect-test layouts; two duplicate basenames (`test_wasp_effects.py`,
  `test_tigerclaw_effects.py` exist in both `tests/engine/` and `tests/engine/effects/cases/`, covering
  different cards) — violates the skill's own "unique basenames, no `__init__.py`" rule. Make
  `tests/engine/effects/cases/` canonical; migrate + delete duplicates; rewrite white-box `get_steps()`
  assertions (52 in tigerclaw alone) as behavioral `run_card` tests.
- **DF5** Under-tested heroes: **garrus has no dedicated test file** (`garrus_effects.py` 657 LOC, 61%);
  whisper (largest, 1418 LOC) 70%; ursafar 53%, dodger 56%, min 59%. Backfill with the
  `EffectScenarioBuilder + run_card` pattern that gets other heroes to ~100%. Pair with QW6 floor.

---

## §4 Execution Playbook — start Column ① now

Work on a branch (not `main`). Run the full suite before and after:
`PYTHONPATH=src uv run pytest tests/ -q`. Commit each item separately.

1. **QW1 (live bug).** Read `engine/steps/selection.py` around 210–240 and 370–380 to confirm the
   `"SKIP"`/`"DONE"` sentinels. Edit `docs/CLIENT_INTEGRATION_GUIDE.md:883–885` to say skip = string
   `"SKIP"`. Add `tests/.../test_select_skip_sentinel.py`: build a non-mandatory `SelectStep`, drive
   it with `selection="SKIP"` (asserts skip) and `selection=None` (asserts re-request).
2. **QW2.** Add `python-dotenv>=1.0` to `[project].dependencies` in `pyproject.toml`; run `uv lock`; `uv sync`.
3. **QW3.** Add `__all__` to `engine/steps/__init__.py` listing every re-exported name (mirror
   `engine/filters.py`). Confirm `uv run mypy src` still clean; optionally check the strict-error drop.
4. **QW4 + QW5 (docs).** Apply §0 corrections to `CLAUDE.md` (effect location at :95/:306; union
   pitfall at :155/:233/:264). Decide canonical agent file; make the other two pointers. Add a stale
   banner to `CODEBASE_MAP.md` (or regenerate via the Cartographer skill) with the corrected package
   layout + `server/`. Verify against this doc's §0.
5. **QW6.** Run `PYTHONPATH=src uv run pytest --cov=goa2 --cov-branch tests/` to read the current %.
   Add `--cov=goa2 --cov-branch --cov-fail-under=<that number, rounded down>` to the CI test step in
   `.github/workflows/ci.yml`. Leave pre-push fast.
6. **QW7.** Add `__init_subclass__` to `GameStep` (`engine/steps/base.py`) that raises if a concrete
   subclass has `type == StepType.GENERIC`. Run the suite — fix any class that trips it (that's a real latent bug).
7. **QW8.** Add the `concurrency` block + `push: branches: [main]` to `ci.yml`.

Then pause and pick **one** Big Bet for the next cycle — **BB1 (contract tests)** is the recommended
first because it makes QW1's class of bug impossible going forward.

---

## §5 Provenance & maintenance

- Produced 2026-06-30 by an 8-dimension audit (module structure, complexity, serialization,
  effect authoring, type safety, testing, client contract, tooling/CI/docs). Each finding's
  citations were re-verified against the code by an independent skeptical pass; 1 finding
  (a movement.py method-length claim) was rejected as overstated and is not listed here.
- **This is a living document.** As you complete an item, mark it `DONE (YYYY-MM-DD, <commit>)`
  and move on. When you change top-level `src/goa2` structure, update §0 and CODEBASE_MAP together.
- Two related project memories exist for fresh agents: effect-logic-location and
  serialization-auto-registration (both correct the misleading CLAUDE.md statements).
```

