# GoA2 Map Editor — Design

Date: 2026-07-04
Status: Approved

## Goal

A simple, zero-install tool to create and edit GoA2 map JSON files for the
backend (`data/maps/*.json`), prepared for double-lane maps. Plus the small
backend change needed so multi-lane maps actually load.

## Deliverables

1. `tools/map_editor.html` — single self-contained HTML file (vanilla JS +
   SVG), opened directly in a browser.
2. `engine/map_loader.py` — support a top-level `"lanes"` key.
3. Loader tests for the new format (legacy formats must keep passing).

## Map JSON format

Existing format, unchanged:

```json
{
  "zone_definitions": [{"id": "...", "label": "...", "color": "#rrggbb"}],
  "hex_map": [{"q": 0, "r": 0, "s": 0, "zone_id": "...", "tags": []}]
}
```

New top-level key written by the editor (replaces legacy `"lane"`):

```json
{
  "lanes": {
    "lane_1": ["RedBase", "RedBeach", "Mid", "BlueBeach", "BlueBase"],
    "lane_2": ["..."]
  }
}
```

Lane values are ordered zone **labels** (red side → blue side), matching the
existing legacy `"lane"` convention. The loader resolves labels → zone ids.

## Editor

### Rendering

- SVG, pointy-top hexes, axial coordinates (`s = -q - r` computed on export).
- Bounded "ghost" grid (~50×40 ≈ 2,000 hexes) to paint onto; panning past the
  edge extends the ghost field on demand. Pan via drag, zoom via wheel
  (viewBox transform).
- Performance rules: one delegated event listener on the SVG root
  (`data-q`/`data-r` attributes), mutate only the changed hex when painting,
  CSS `:hover` for highlighting.

### Panels / tools

- **Zones**: create / rename / recolor / delete zones. Ids generated as
  `zone_<timestamp>_<rand>` (matches existing maps). Selecting a zone makes
  click/drag paint hexes into it. Eraser removes hexes from the map.
  Deleting a zone removes its hexes from the map.
- **Tags**: pick a tag, click hexes to toggle it. Built-in tags: `Terrain`,
  `RedHeroSpawn`, `BlueHeroSpawn`, and `Red`/`Blue` × `Heavy`/`Melee`/`Ranged`
  spawn tags; free-text custom tag input. Tags render as small badges on the
  hex.
- **Lanes**: starts with `lane_1`; "+ Add lane" adds `lane_2` (and further).
  Each lane is an ordered list of zone labels: add from dropdown, reorder
  up/down, remove. Lanes can be deleted (except the last one).
- **Import**: file picker; accepts current editor format, legacy `"lane"`,
  and maps with neither (lane panel starts empty). Malformed JSON → readable
  error, state untouched.
- **Export**: downloads `<name>.json` with `zone_definitions`, `hex_map`,
  `"lanes"`. Non-blocking warnings before download if: a lane references a
  zone with no hexes or a label that no longer exists, a lane has fewer than
  3 zones, or `RedHeroSpawn`/`BlueHeroSpawn` is missing.
- **Autosave**: editor state mirrored to localStorage on every change;
  restored on load. "New map" button clears it.

## Backend loader change

`load_map()` lane inference becomes, in priority order:

1. `data["lanes"]`: `{lane_id: [labels]}` → resolve each label list to zone
   ids → `board.lanes[lane_id] = [...]`. Unknown labels: warn and skip label;
   a lane resolving to <3 zones: warn (consistent with current behavior).
2. Legacy `data["lane"]`: unchanged behavior (single `board.lane` assignment,
   which the Board model migrates to `lanes[DEFAULT_LANE_ID]`).
3. Fallback hardcoded label list: unchanged.

No changes to zone/hex/tag/spawn parsing.

## Testing

- `tests/engine/test_map_loader.py` (new or extended): loading a synthetic
  two-lane map JSON sets `board.lanes` with both lanes in order; loading
  `test_map.json` (legacy) still works; unknown label in a lane warns and is
  skipped.
- Full suite: `PYTHONPATH=src uv run pytest tests/ -q`.
- Editor: manual round-trip — import `data/maps/test_map.json`, export, load
  the exported file with `load_map()` and compare zones/hexes/tags/lane.

## Out of scope

- Double-lane endgame rules, setup, or any engine behavior beyond loading
  `board.lanes` (tracked in `docs/DOUBLE_LANE_PREP.md`).
- Saving directly into `data/maps/` from the browser (no server; export is a
  download).
