# dev21: arcology generator

Procedural Art Deco arcologies, described rather than modelled. A JSON spec is resolved by a plain-Python grammar
into a plan of placed, identified elements; Blender builds each unique element once and assembles the scene from a
placement manifest, which Unreal will later consume the same way. See [`docs/PLAN.md`](docs/PLAN.md).

Blender runs headless as a Python module (`bpy` from PyPI); no Blender install is needed.

## Quick start

```bash
uv sync                                                        # Python 3.13, bpy 5.2.2, Pillow
uv run arcology sheet specs/default.json -o build/review       # contact sheet of 12 golden seeds
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

Phase 0 (foundations) is complete: schema v0, per-element seeds, a resolver for a stepped podium and a central tower
with setbacks, structural metrics, element library and manifest, stand-in assembler, and contact sheets in CI.
Next is Phase 1: massing primitives and the first facade (bays, one window recipe, one door recipe).
