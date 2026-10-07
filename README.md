# dev21

Seeded procedural game assets generated with Blender, exported as glTF (`.glb`) for use in a game engine.

Blender runs headless as a Python module (`bpy` from PyPI), so no Blender install is needed.

## Quick start

```bash
uv sync                                   # Python 3.13 + bpy 5.2.2 (~400 MB wheel)
uv run assetgen --seed 42 --out build/assets --preview build/preview.png
./scripts/check.sh                        # lint, format check, tests
```

`build/assets/` gets one `.glb` per prop plus `manifest.json` (vertex/triangle counts and bounds per asset).
`build/preview.png` is a Cycles render of the whole set.

## Layout

- `src/assetgen/generators.py`: seeded rock and tree generators, prop scattering
- `src/assetgen/export.py`: glTF export and the manifest
- `src/assetgen/preview.py`: preview render (Cycles, CPU)
- `tests/`: pytest suite (determinism, budgets, origin convention, glTF validity, preview)
