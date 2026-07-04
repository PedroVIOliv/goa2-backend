# GoA2 Map Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-file browser map editor (`tools/map_editor.html`) for GoA2 map JSON, plus `map_loader.py` support for the multi-lane `"lanes"` key.

**Architecture:** The editor is one self-contained HTML file (vanilla JS + SVG, no build, no dependencies) that imports/exports the backend's map JSON format. The backend change is confined to the lane-inference block at the end of `load_map()`.

**Tech Stack:** Vanilla JS + SVG (editor); Python 3.11 / pytest via `uv` (backend).

## Global Constraints

- Backend tests run as `PYTHONPATH=src uv run pytest ...` (see CLAUDE.md).
- Pre-commit runs ruff/black/mypy — code must pass them.
- No git commit co-author trailers.
- Map JSON contract: `zone_definitions` (`id`, `label`, `color`), `hex_map`
  (`q`, `r`, `s`, `zone_id`, `tags`), new top-level
  `lanes: {lane_id: [zone labels red→blue]}`. Legacy `lane: [labels]` must
  keep loading.
- Spec: `docs/superpowers/specs/2026-07-04-map-editor-design.md`.

---

### Task 1: `map_loader.py` support for `"lanes"`

**Files:**
- Modify: `src/goa2/engine/map_loader.py:220-242` (lane-inference block)
- Test: `tests/engine/test_map_loader_lanes.py` (new)

**Interfaces:**
- Produces: `load_map(path)` sets `board.lanes: dict[str, list[str]]` (zone
  **ids**, red→blue order) from `data["lanes"]: dict[str, list[str]]` (zone
  **labels**). Lanes resolving to <3 zones are skipped with a warning, as are
  unknown labels. Legacy `"lane"` and the hardcoded fallback are unchanged.

- [ ] **Step 1: Write the failing tests**

`tests/engine/test_map_loader_lanes.py`:

```python
import json

import pytest

from goa2.engine.map_loader import load_map


def _zone(zid: str, label: str) -> dict:
    return {"id": zid, "label": label, "color": "#cccccc"}


def _hexes(zid: str, coords: list[tuple[int, int]]) -> list[dict]:
    return [{"q": q, "r": r, "s": -q - r, "zone_id": zid, "tags": []} for q, r in coords]


def _write_map(tmp_path, data: dict) -> str:
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data))
    return str(p)


@pytest.fixture
def two_lane_map(tmp_path) -> str:
    """Two disjoint 3-zone lanes; each zone is a single hex."""
    zones = [
        _zone("z_rb1", "RedBase1"),
        _zone("z_mid1", "Mid1"),
        _zone("z_bb1", "BlueBase1"),
        _zone("z_rb2", "RedBase2"),
        _zone("z_mid2", "Mid2"),
        _zone("z_bb2", "BlueBase2"),
    ]
    hex_map = (
        _hexes("z_rb1", [(0, 0)])
        + _hexes("z_mid1", [(1, 0)])
        + _hexes("z_bb1", [(2, 0)])
        + _hexes("z_rb2", [(0, 5)])
        + _hexes("z_mid2", [(1, 5)])
        + _hexes("z_bb2", [(2, 5)])
    )
    data = {
        "zone_definitions": zones,
        "hex_map": hex_map,
        "lanes": {
            "lane_1": ["RedBase1", "Mid1", "BlueBase1"],
            "lane_2": ["RedBase2", "Mid2", "BlueBase2"],
        },
    }
    return _write_map(tmp_path, data)


def test_lanes_key_loads_both_lanes_in_order(two_lane_map):
    board = load_map(two_lane_map)
    assert board.lanes == {
        "lane_1": ["z_rb1", "z_mid1", "z_bb1"],
        "lane_2": ["z_rb2", "z_mid2", "z_bb2"],
    }


def test_legacy_single_lane_map_still_loads():
    board = load_map("data/maps/test_map.json")
    assert len(board.lanes) == 1
    assert len(board.lane) >= 3  # legacy accessor works on single-lane boards


def test_lane_with_unknown_label_is_skipped(tmp_path, caplog):
    data = {
        "zone_definitions": [
            _zone("z_a", "A"),
            _zone("z_b", "B"),
            _zone("z_c", "C"),
        ],
        "hex_map": _hexes("z_a", [(0, 0)]) + _hexes("z_b", [(1, 0)]) + _hexes("z_c", [(2, 0)]),
        "lanes": {
            "lane_1": ["A", "B", "C"],
            "lane_2": ["A", "Nope", "AlsoNope"],  # resolves to 1 zone -> skipped
        },
    }
    board = load_map(_write_map(tmp_path, data))
    assert board.lanes == {"lane_1": ["z_a", "z_b", "z_c"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_map_loader_lanes.py -v`
Expected: `test_lanes_key_loads_both_lanes_in_order` and
`test_lane_with_unknown_label_is_skipped` FAIL (loader ignores `"lanes"`, so
`board.lanes` falls back to the hardcoded labels and is empty/wrong);
`test_legacy_single_lane_map_still_loads` PASSES (guards regression).

- [ ] **Step 3: Implement**

Replace the lane-inference block at the end of `load_map()`
(`# Lane inference` through the final `logger.warning`) with:

```python
    # Lane inference
    # Priority: 1. "lanes" dict, 2. legacy "lane" list, 3. hardcoded fallback
    label_to_id = {z.label: z.id for z in zones.values() if z.label}

    def _resolve_labels(labels: list[str]) -> list[str]:
        resolved = []
        for label in labels:
            if label in label_to_id:
                resolved.append(label_to_id[label])
            else:
                logger.warning("Lane label %r not found in zones.", label)
        return resolved

    lanes_data = data.get("lanes")
    if lanes_data:
        lanes: dict[str, list[str]] = {}
        for lane_id, lane_labels in lanes_data.items():
            lane_ids = _resolve_labels(lane_labels)
            if len(lane_ids) >= 3:
                lanes[lane_id] = lane_ids
            else:
                logger.warning(
                    "Skipping lane %r: needs at least 3 resolvable zones, got %s.",
                    lane_id,
                    lane_ids,
                )
        board.lanes = lanes
        logger.info("Loaded lanes: %s", list(lanes))
    else:
        lane_labels = data.get("lane") or ["RedBase", "RedBeach", "Mid", "BlueBeach", "BlueBase"]
        lane_ids = _resolve_labels(lane_labels)
        if len(lane_ids) >= 3:
            board.lane = lane_ids
            logger.info("Inferred lane: %s", lane_labels)
        else:
            logger.warning(
                "Could not infer minimal lane (RedBase->Mid->BlueBase). Found: %s",
                list(label_to_id.keys()),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src uv run pytest tests/engine/test_map_loader_lanes.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Run the full suite**

Run: `PYTHONPATH=src uv run pytest tests/ -q`
Expected: all pass (no behavior change for legacy maps).

- [ ] **Step 6: Commit**

```bash
git add src/goa2/engine/map_loader.py tests/engine/test_map_loader_lanes.py
git commit -m "feat: load multi-lane maps via top-level 'lanes' key"
```

---

### Task 2: Map editor `tools/map_editor.html`

**Files:**
- Create: `tools/map_editor.html` (single self-contained file)

**Interfaces:**
- Consumes: map JSON contract from Global Constraints; must import
  `data/maps/test_map.json` (legacy `"lane"`-less file with
  `zone_definitions` + `hex_map`).
- Produces: exported JSON loadable by Task 1's `load_map()`.

The file has three parts: `<style>`, static layout markup, one `<script>`.
No external resources.

- [ ] **Step 1: State model + layout skeleton**

Editor state (single mutable object, mirrored to localStorage):

```js
const state = {
  mapName: "new_map",
  zones: [],            // [{id, label, color}]
  hexes: new Map(),     // "q,r" -> {zoneId, tags: []}
  lanes: { lane_1: [] } // laneId -> [zone label, ...] red -> blue
};
// serialize: hexes Map <-> array of [key, value] for JSON/localStorage
```

Layout: left sidebar (map name input, tool sections: Zones / Tags / Lanes /
Import-Export), main area = one full-height `<svg>` with a `<g id="world">`
group (pan/zoom target). Tool mode is a single variable:
`mode = {kind: "paint"} | {kind: "erase"} | {kind: "tag", tag: "Terrain"}`.

- [ ] **Step 2: Hex grid rendering + pan/zoom**

Pointy-top axial math (hex size `S = 22`):

```js
const hexX = (q, r) => S * Math.sqrt(3) * (q + r / 2);
const hexY = (q, r) => S * 1.5 * r;
function hexPoints(cx, cy) { // 6 corners, pointy-top
  return Array.from({length: 6}, (_, i) => {
    const a = Math.PI / 180 * (60 * i - 30);
    return `${cx + S * Math.cos(a)},${cy + S * Math.sin(a)}`;
  }).join(" ");
}
```

Ghost grid: q in [-25, 25), r in [-20, 20) (~2,000 polygons) rendered once at
startup; each polygon carries `data-q`/`data-r` and class `ghost`. Painted
hexes are the same polygons restyled (fill = zone color, class `painted`) —
never re-rendered wholesale. Tag badges are small `<text>` elements in an
overlay group, keyed by "q,r", added/removed per hex on change. If a loaded
map has hexes outside the ghost bounds, extend the bounds to fit and render
the extra ghosts.

Interaction (all listeners on the `<svg>` root — event delegation):
- wheel → zoom (scale viewBox around cursor, clamp 0.25×–4×)
- middle-drag or space+drag → pan (translate viewBox)
- left click / left-drag over polygons → apply current tool per hex
  (dedupe by "q,r" within one drag)
- CSS `.ghost:hover` / `.painted:hover` for hover highlight, no JS handlers

- [ ] **Step 3: Zones panel + paint/erase tools**

- "Add zone" → `{id: `zone_${Date.now()}_${Math.random().toString(36).slice(2,7)}`, label: "Zone N", color: <next of 10-color palette>}`.
- Each zone row: color swatch (native `<input type="color">`), label text
  input, hex count, delete button (×). Clicking a row selects it as the
  active zone and sets `mode = {kind: "paint"}`.
- Renaming a zone rewrites that label in all lanes (lanes store labels).
- Deleting a zone removes its hexes from `state.hexes`, restyles their
  polygons to ghosts, and removes its label from all lanes.
- Paint applies `{zoneId: activeZone.id, tags: existing tags or []}` to the
  hex; erase deletes the key and clears tags/badges.

- [ ] **Step 4: Tags tool**

Built-in tag list: `Terrain`, `RedHeroSpawn`, `BlueHeroSpawn`,
`RedHeavySpawn`, `RedMeleeSpawn`, `RedRangedSpawn`, `BlueHeavySpawn`,
`BlueMeleeSpawn`, `BlueRangedSpawn`, plus a free-text input ("custom tag" +
apply button adds it to the clickable list for this session). Selecting a tag
sets `mode = {kind: "tag", tag}`; clicking a **painted** hex toggles the tag
in its `tags` array (clicks on ghosts do nothing). Badges: `Terrain` → "▲";
spawn tags → first letter of team + first letter of type (e.g. "RH" for
RedHeroSpawn, "BHv" for BlueHeavySpawn), colored red/blue; custom → first 3
chars. Multiple badges stack vertically within the hex.

- [ ] **Step 5: Lanes panel**

- Lanes render as cards: lane id header, delete button (disabled when only
  one lane remains), ordered zone-label list with ↑ / ↓ / ✕ per entry, and an
  "add zone" `<select>` listing zone labels not yet in that lane.
- "+ Add lane" appends `lane_${n}` where n = smallest positive integer not
  already used.
- Empty state hint: "Order zones red side → blue side."

- [ ] **Step 6: Import / export / autosave**

Import (file `<input>`): parse JSON in try/catch — on failure show the error
in a status bar and leave state untouched. On success build fresh state:
`zone_definitions` → zones; `hex_map` → hexes keyed "q,r" (ignore stored `s`);
`lanes` → as-is, else legacy `lane` → `{lane_1: [...]}`, else `{lane_1: []}`.
Then re-render everything and autosave.

Export ("Export JSON" button):

```js
function buildExport() {
  return {
    zone_definitions: state.zones,
    hex_map: [...state.hexes.entries()].map(([key, h]) => {
      const [q, r] = key.split(",").map(Number);
      return { q, r, s: -q - r, zone_id: h.zoneId, tags: h.tags };
    }),
    lanes: Object.fromEntries(
      Object.entries(state.lanes).map(([id, labels]) => [id, [...labels]])
    ),
  };
}
```

Pre-export validation → list of warning strings shown in the status bar
(non-blocking; export proceeds): lane label not matching any zone; lane
referencing a zone with 0 hexes; lane with <3 zones; no hex tagged
`RedHeroSpawn`; none tagged `BlueHeroSpawn`. Download via
`URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)]))` +
temporary `<a download="${mapName}.json">`.

Autosave: every mutation goes through `commit()` which re-renders affected
UI and writes serialized state to
`localStorage["goa2_map_editor"]`; on page load restore if present.
"New map" button: confirm(), then reset state + clear localStorage.

- [ ] **Step 7: Syntax check**

Extract the script and check it parses:

Run: `python3 -c "import re,sys; h=open('tools/map_editor.html').read(); open('/tmp/me.js','w').write(re.findall(r'<script>(.*)</script>', h, re.S)[0])" && node --check /tmp/me.js`
Expected: no output (exit 0).

- [ ] **Step 8: Round-trip verification**

Simulate the editor's export of an imported `test_map.json` (same transform
as `buildExport`: identity on zones/hexes, legacy map with no `lane` key →
`lanes: {lane_1: []}` — a warning case, still loadable) and feed it to
`load_map()`:

```bash
PYTHONPATH=src uv run python - <<'EOF'
import json, tempfile, os
from goa2.engine.map_loader import load_map

data = json.load(open("data/maps/test_map.json"))
exported = {
    "zone_definitions": data["zone_definitions"],
    "hex_map": data["hex_map"],
    "lanes": {"lane_1": ["RedBase", "RedBeach", "Mid", "BlueBeach", "BlueBase"]},
}
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
    json.dump(exported, f)
orig, new = load_map("data/maps/test_map.json"), load_map(f.name)
assert new.lanes == {"lane_1": orig.lane if orig.lane else None} or new.lanes["lane_1"] == orig.lane
assert set(new.tiles) == set(orig.tiles)
os.unlink(f.name)
print("round-trip OK")
EOF
```

Expected: `round-trip OK`. (Full in-browser round trip — import, paint,
export — is the user's manual acceptance check.)

- [ ] **Step 9: Commit**

```bash
git add tools/map_editor.html
git commit -m "feat: add single-file browser map editor"
```

---

### Task 3: Plan/spec bookkeeping

- [ ] **Step 1: Commit the plan** (if not yet committed) and tick checkboxes
  as tasks complete.

```bash
git add docs/superpowers/plans/2026-07-04-map-editor.md
git commit -m "docs: map editor implementation plan"
```
