# dev21: arcology generator

Procedural Art Deco arcologies, described rather than modelled. A JSON spec is resolved by a plain-Python grammar
into a plan of placed, identified elements; Blender builds each unique element once and assembles the scene from a
placement manifest, which Unreal will later consume the same way. See [`docs/PLAN.md`](docs/PLAN.md).

Blender runs headless as a Python module (`bpy` from PyPI); no Blender install is needed.

## Quick start

```bash
uv sync                                                        # Python 3.13, bpy 5.2.2, Pillow
uv run arcology sheet specs/default.json -o build/review       # contact sheet of 12 golden seeds (L2)
uv run arcology detail specs/default.json -o build/detail      # close-ups of 3 seeds (L0): entrance, cluster, setback, crown
uv run arcology sweep specs/default.json -o build/sweep        # each style setting along a row, one seed (L2)
uv run arcology batch specs/default.json -o build/batch        # 100 seeds as silhouettes (L3), style envelope ranges
uv run arcology elevations specs/default.json -o build/elevations   # layer trees, flat (no Blender)
uv run arcology resolve specs/default.json --seed 7 -o plan.json
uv run arcology build plan.json -o build/seed-7 --lod L2
./scripts/check.sh                                             # lint, format check, tests
```

## Pipeline

```
spec (specs/*.json) → resolve (plain Python) → plan.json
    → build (Blender) → elements/*.glb + manifest.json → assemble → scene → review renders
```

## Status

- **Phase 0 (foundations):** schema v0, per-element seeds, structural metrics, element library and manifest,
  stand-in assembler, contact sheets in CI.
- **Phase 1 (massing and first facade):** a stepped podium and a central tower with setbacks, dressed with stone
  piers on every bay line, L-shaped corners, a Deco glazed-channel window on every bay of every floor (about 13,000
  per building, each with its own identity), and a stepped main entrance centred on the south face. L0 and L2
  representations; facade coverage, symmetry and entrance checks.
- **Phase 2 (arcology composition):** up to 9 secondary towers in mirror twins: sister towers beside the central
  tower, bridged to it on a shared transfer floor marked by stone bands, and squat pavilions on the lower terraces
  bridged into the tier above. Stepped crowns on every tower, a spire on the central one, parapets on every
  terrace. Checks for dominance, bridges, crowns, clearance and facade placement.

- **Phase 3 (facade grammar):** the middle scale. Notched corners on towers and podium tiers; pilasters every few
  bays with recessed piers between; base, shaft and capital zones with their own windows; stepped cornices on every
  mass; doors at the foot of every tower; chevrons, fluted pilasters and stepped merlons gated by an ornament
  density that follows the hierarchy (central tower richest). Window channels at L2 keep the zones legible at a
  distance. Checks for cornices and ornament hierarchy; bridges now also meet walls, not notches.

- **Phase 4 (style and variation):** every style setting changes the building (symmetry, dominant axis with a
  streamline variant of glass ribbons and stone bands, hierarchy, ornament density, setback strength, repetition,
  termination). A style envelope checks every seed for drift (needles, stubs, slabs, missing base, oversized
  spires, ornament noise). Sweep sheets show one setting per row; a 100-seed batch sheet shows the family holds.

Next is Phase 4b, scale layers and contrast ([`docs/LAYERS.md`](docs/LAYERS.md)): step 1, an explicit layer tree on
every facade with an elevation sheet, is built; zones, band rhythm and treatments that skip layers come next. Then
Phase 5: representation levels.
