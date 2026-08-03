/**
 * Unit tests for map_editor.html's pure-logic block, focused on the map-image
 * calibration solver.
 *
 * Run: node --test tools/map_editor.test.mjs
 *
 * The pure block is extracted and evaluated as CommonJS, the way
 * docs/superpowers/plans/2026-07-04-map-editor.md documents for `node --check`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import vm from "node:vm";

const HERE = path.dirname(new URL(import.meta.url).pathname);

function loadPureBlock() {
  const html = readFileSync(path.join(HERE, "map_editor.html"), "utf8");
  const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  const pure = blocks.find((b) => b.includes("module.exports"));
  assert.ok(pure, "could not find the pure-logic script block");
  const module = { exports: {} };
  vm.runInNewContext(pure, { module, require: createRequire(import.meta.url), console });
  return module.exports;
}

const E = loadPureBlock();
const hex = (q, r) => ({ q, r });

/** Smallest absolute difference between two angles in degrees. */
const angleDiff = (a, b) => Math.abs((((a - b) % 360) + 540) % 360 - 180);

/* ---------- the frontend's side of the contract, duplicated on purpose ----------
 * These mirror goa2-frontend/src/components/board3d/maps/geometry.ts. Restating
 * them here rather than importing is the point: the two repos must agree, and a
 * test that shares an implementation with the thing it checks proves nothing. */

/** Flat-top axial hex -> frontend grid-local (x, z). */
function zu(h, hexSize) {
  return [
    hexSize * 1.5 * h.q,
    hexSize * (Math.sqrt(3) / 2 * h.q + Math.sqrt(3) * h.r),
  ];
}

/** Hex -> frontend world (x, z), applying rotation-y then the origin offset. */
function hexToWorld(h, cfg) {
  const [lx, lz] = zu(h, cfg.hexSize);
  const t = (cfg.rotationDeg * Math.PI) / 180;
  const cos = Math.cos(t);
  const sin = Math.sin(t);
  return [cfg.origin.x + lx * cos + lz * sin, cfg.origin.z - lx * sin + lz * cos];
}

/** Frontend world (x, z) -> image pixel, for an imageSize-wide aspect-true plane. */
function worldToPixel(x, z, cfg, imageW, imageH) {
  const g = imageW / cfg.imageSize;
  return [x * g + imageW / 2, z * g + imageH / 2];
}

/** The three shipped, hand-tuned map configs. */
const SHIPPED = [
  { name: "forgotten_island", imageSize: 10, hexSize: 0.295, origin: { x: -0.99, z: 1.24 }, rotationDeg: 345, w: 1270, h: 1270 },
  { name: "narrow_passages", imageSize: 10, hexSize: 0.275, origin: { x: 0.54, z: 0.87 }, rotationDeg: 103, w: 3040, h: 3040 },
  { name: "across_the_river", imageSize: 10, hexSize: 0.295, origin: { x: -0.26, z: 0.36 }, rotationDeg: 0, w: 3012, h: 3012 },
];

/**
 * The placement that a perfect align would produce for `cfg`: it maps every image
 * pixel to the SVG point where the hex on that pixel is drawn.
 */
function placementFor(cfg, imageW, imageH) {
  // Two hexes are enough to pin it down, so build it with the solver itself
  // driven by exact synthetic clicks.
  const a = hex(0, 0);
  const b = hex(4, -9);
  const clicks = [a, b].map((h) => {
    const [wx, wz] = hexToWorld(h, cfg);
    const [px, py] = worldToPixel(wx, wz, cfg, imageW, imageH);
    return E.placePixel(E.identityPlacement(), px, py);
  });
  return E.solvePlacement(E.identityPlacement(), clicks, [a, b]);
}

test("frame identity: zE == HEX_SIZE * e^(-i*pi/6) * zu", () => {
  const c = Math.cos(-Math.PI / 6);
  const s = Math.sin(-Math.PI / 6);
  for (const h of [hex(0, 0), hex(1, 0), hex(0, 1), hex(-3, 5), hex(7, -2), hex(9, 9)]) {
    const [ux, uz] = zu(h, 1);
    assert.ok(Math.abs(E.HEX_SIZE * (ux * c - uz * s) - E.hexX(h.q, h.r)) < 1e-9);
    assert.ok(Math.abs(E.HEX_SIZE * (ux * s + uz * c) - E.hexY(h.q, h.r)) < 1e-9);
  }
});

test("solvePlacement recovers every shipped map config from two clicks", () => {
  for (const shipped of SHIPPED) {
    const cfg = { ...shipped };
    const pl = placementFor(cfg, shipped.w, shipped.h);
    const out = E.placementToConfig(pl, shipped.w, shipped.h, cfg.imageSize, null);

    assert.ok(Math.abs(out.hexSize - cfg.hexSize) < 1e-9, `${cfg.name} hexSize ${out.hexSize}`);
    assert.ok(Math.abs(out.origin.x - cfg.origin.x) < 1e-9, `${cfg.name} origin.x ${out.origin.x}`);
    assert.ok(Math.abs(out.origin.z - cfg.origin.z) < 1e-9, `${cfg.name} origin.z ${out.origin.z}`);
    assert.ok(
      angleDiff(out.rotationDeg, cfg.rotationDeg) < 1e-7,
      `${cfg.name} rotationDeg ${out.rotationDeg} != ${cfg.rotationDeg}`,
    );
  }
});

test("solve is resolution-independent: same framing, half the pixels", () => {
  const cfg = { ...SHIPPED[1] };
  const full = E.placementToConfig(placementFor(cfg, 3040, 3040), 3040, 3040, cfg.imageSize, null);
  const half = E.placementToConfig(placementFor(cfg, 1520, 1520), 1520, 1520, cfg.imageSize, null);
  assert.ok(Math.abs(full.hexSize - half.hexSize) < 1e-9);
  assert.ok(Math.abs(full.origin.x - half.origin.x) < 1e-9);
  assert.ok(Math.abs(full.origin.z - half.origin.z) < 1e-9);
});

test("solve handles a non-square image (the magma_and_ice case)", () => {
  const cfg = { imageSize: 10, hexSize: 0.31, origin: { x: 0.2, z: -0.4 }, rotationDeg: 17 };
  const pl = placementFor(cfg, 3172, 3200);
  const out = E.placementToConfig(pl, 3172, 3200, cfg.imageSize, null);
  assert.ok(Math.abs(out.hexSize - cfg.hexSize) < 1e-9);
  assert.ok(Math.abs(out.origin.x - cfg.origin.x) < 1e-9);
  assert.ok(Math.abs(out.origin.z - cfg.origin.z) < 1e-9);
  assert.ok(angleDiff(out.rotationDeg, cfg.rotationDeg) < 1e-7);

  // The placement is a similarity, so it scales both image axes equally: a
  // horizontal and a vertical pixel span of the same length stay the same length.
  const o = E.placePixel(pl, 0, 0);
  const across = E.placePixel(pl, 1000, 0);
  const down = E.placePixel(pl, 0, 1000);
  const lenAcross = Math.hypot(across[0] - o[0], across[1] - o[1]);
  const lenDown = Math.hypot(down[0] - o[0], down[1] - o[1]);
  assert.ok(Math.abs(lenAcross - lenDown) < 1e-9, `${lenAcross} != ${lenDown}`);
});

test("solving an already-aligned image is idempotent", () => {
  const cfg = { ...SHIPPED[2] };
  const pl = placementFor(cfg, 3012, 3012);
  const a = hex(2, 3);
  const b = hex(-5, 1);
  // Click exactly where the placed image already puts those hex centres.
  const clicks = [a, b].map((h) => {
    const [wx, wz] = hexToWorld(h, cfg);
    const [px, py] = worldToPixel(wx, wz, cfg, 3012, 3012);
    return E.placePixel(pl, px, py);
  });
  const again = E.solvePlacement(pl, clicks, [a, b]);
  assert.ok(Math.abs(again.m[0] - pl.m[0]) < 1e-9);
  assert.ok(Math.abs(again.m[1] - pl.m[1]) < 1e-9);
  assert.ok(Math.abs(again.c[0] - pl.c[0]) < 1e-6);
  assert.ok(Math.abs(again.c[1] - pl.c[1]) < 1e-6);
});

test("anchor order matters, so the 180 degree hex symmetry cannot pass silently", () => {
  const cfg = { ...SHIPPED[2] };
  const a = hex(0, 0);
  const b = hex(4, -9);
  const clicks = [a, b].map((h) => {
    const [wx, wz] = hexToWorld(h, cfg);
    const [px, py] = worldToPixel(wx, wz, cfg, 3012, 3012);
    return E.placePixel(E.identityPlacement(), px, py);
  });
  const right = E.placementToConfig(
    E.solvePlacement(E.identityPlacement(), clicks, [a, b]), 3012, 3012, 10, null);
  const swapped = E.placementToConfig(
    E.solvePlacement(E.identityPlacement(), [clicks[1], clicks[0]], [a, b]), 3012, 3012, 10, null);
  const apart = angleDiff(swapped.rotationDeg, right.rotationDeg);
  assert.ok(Math.abs(apart - 180) < 1e-6, `expected a 180 degree difference, got ${apart}`);
});

test("placePixel and unplacePoint are inverses", () => {
  const pl = placementFor({ ...SHIPPED[0] }, 1270, 1270);
  for (const [px, py] of [[0, 0], [1270, 1270], [431, 902], [12.5, 3.25]]) {
    const [x, y] = E.placePixel(pl, px, py);
    const [bx, by] = E.unplacePoint(pl, x, y);
    assert.ok(Math.abs(bx - px) < 1e-6 && Math.abs(by - py) < 1e-6);
  }
});

test("the exported check point round-trips to its hex", () => {
  const cfg = { ...SHIPPED[1] };
  const checkHex = hex(6, -11);
  const pl = placementFor(cfg, 3040, 3040);
  const out = E.placementToConfig(pl, 3040, 3040, cfg.imageSize, checkHex);
  // Reproduce what the frontend's dev assertion does.
  const aspect = 3040 / 3040;
  const wx = (out.check.u - 0.5) * cfg.imageSize;
  const wz = (out.check.v - 0.5) * cfg.imageSize * aspect;
  const [hx, hz] = hexToWorld(checkHex, out);
  assert.ok(Math.hypot(wx - hx, wz - hz) < 1e-9);
});

test("placementTransform emits a similarity matrix", () => {
  const t = E.placementTransform({ m: [2, 3], c: [10, -4] });
  assert.equal(t, "matrix(2 3 -3 2 10 -4)");
});

test("farthestHexPair picks the two most separated hexes, top-most first", () => {
  const keys = ["0,0", "1,0", "0,1", "8,-4", "-6,5"];
  const [a, b] = E.farthestHexPair(keys);
  const spans = new Set([`${a.q},${a.r}`, `${b.q},${b.r}`]);
  assert.deepEqual(spans, new Set(["8,-4", "-6,5"]));
  assert.ok(E.hexY(a.q, a.r) <= E.hexY(b.q, b.r));
  assert.equal(E.farthestHexPair(["0,0"]), null);
  assert.equal(E.farthestHexPair([]), null);
});

test("degenerate anchors are rejected rather than producing garbage", () => {
  const a = hex(0, 0);
  assert.throws(() => E.solvePlacement(E.identityPlacement(), [[10, 10], [10, 10]], [a, hex(3, 3)]));
  assert.throws(() => E.solvePlacement(E.identityPlacement(), [[0, 0], [50, 50]], [a, a]));
  assert.throws(() => E.placementToConfig(E.identityPlacement(), 0, 0, 10, null));
});

test("hexCentreError reports a third click's miss in hex radii", () => {
  const h = hex(3, -1);
  const centre = [E.hexX(h.q, h.r), E.hexY(h.q, h.r)];
  assert.ok(E.hexCentreError(h, centre) < 1e-12);
  assert.ok(Math.abs(E.hexCentreError(h, [centre[0] + E.HEX_SIZE / 2, centre[1]]) - 0.5) < 1e-12);
});

test("configToTs emits a pasteable MapConfig", () => {
  const ts = E.configToTs("magma_and_ice", {
    imageSize: 10, hexSize: 0.2951234, rotationDeg: 17.129,
    origin: { x: -0.2612, z: 0.3599 },
    check: { hex: hex(6, -11), u: 0.841234, v: 0.193777 },
  });
  assert.match(ts, /export const magmaAndIce: MapConfig = \{/);
  assert.match(ts, /name: "magma_and_ice",/);
  assert.match(ts, /imagePath: "\/map\/magma_and_ice\.png",/);
  assert.match(ts, /hexSize: 0\.29512,/);
  assert.match(ts, /origin: \{ x: -0\.2612, z: 0\.3599 \},/);
  assert.match(ts, /rotationDeg: 17\.13,/);
  assert.match(ts, /check: \{ hex: \{ q: 6, r: -11, s: 5 \}, u: 0\.841234, v: 0\.193777 \},/);
});

test("export uses zone labels as ids and rewrites painted hex references", () => {
  const imported = E.parseImport({
    zone_definitions: [
      { id: "zone_random_a", label: "RedBase", color: "#ff0000" },
      { id: "zone_random_b", label: "Mid", color: "#ff9800" },
      { id: "zone_random_c", label: "BlueBase", color: "#0000ff" },
    ],
    hex_map: [
      { q: 0, r: 0, s: 0, zone_id: "zone_random_a", tags: [] },
      { q: 1, r: 0, s: -1, zone_id: "zone_random_b", tags: ["Terrain"] },
      { q: 2, r: 0, s: -2, zone_id: "zone_random_c", tags: [] },
    ],
    lanes: { lane_1: ["RedBase", "Mid", "BlueBase"] },
    battle_zones: { lane_1: "Mid" },
  }).state;

  const out = E.buildExport(imported);
  assert.deepEqual([...out.zone_definitions.map((z) => z.id)], ["RedBase", "Mid", "BlueBase"]);
  assert.deepEqual([...out.zone_definitions.map((z) => z.id === z.label)], [true, true, true]);
  assert.deepEqual([...out.hex_map.map((h) => h.zone_id)], ["RedBase", "Mid", "BlueBase"]);
  assert.equal(JSON.stringify(out.lanes), JSON.stringify({ lane_1: ["RedBase", "Mid", "BlueBase"] }));
  assert.equal(JSON.stringify(out.battle_zones), JSON.stringify({ lane_1: "Mid" }));
});

test("export rejects duplicate zone labels", () => {
  const st = E.makeState();
  st.zones = [
    { id: "a", label: "Mid", color: "#000000" },
    { id: "b", label: "Mid", color: "#ffffff" },
  ];
  assert.throws(() => E.buildExport(st), /Zone labels must be unique/);
});

test("rounding the emitted literals stays well inside the frontend's tolerance", () => {
  const cfg = { ...SHIPPED[2] };
  const checkHex = hex(1, -10);
  const out = E.placementToConfig(placementFor(cfg, 3012, 3012), 3012, 3012, 10, checkHex);
  const rounded = {
    imageSize: 10,
    hexSize: Number(out.hexSize.toFixed(5)),
    rotationDeg: Number(out.rotationDeg.toFixed(2)),
    origin: { x: Number(out.origin.x.toFixed(4)), z: Number(out.origin.z.toFixed(4)) },
  };
  const wx = (out.check.u - 0.5) * 10;
  const wz = (out.check.v - 0.5) * 10;
  const [hx, hz] = hexToWorld(checkHex, rounded);
  const error = Math.hypot(wx - hx, wz - hz) / rounded.hexSize;
  assert.ok(error < 0.05, `rounding error ${error} hex radii is not under the 0.05 limit`);
});
