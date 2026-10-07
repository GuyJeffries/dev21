# CLAUDE.md

Procedural game assets generated headlessly with Blender's Python module (`bpy`) and exported as `.glb`.
Development happens in Claude Code cloud sessions; the user reviews pull requests rather than running code locally,
so every change needs evidence they can check without reading the diff (see "Verifying changes").

**Project direction: read `docs/PLAN.md` before starting work.** It is a procedural Art Deco arcology generator
(spec → plain-Python resolver → Blender builder → manifest-driven assembly; Unreal later). The current `assetgen`
rocks-and-trees package is a placeholder that proves the harness; Phase 0 of the plan replaces it.
The user has limited bandwidth: keep work cloud-verifiable and review evidence small (contact sheets, metric tables).

## Commands

- Setup: `uv sync` (the SessionStart hook in `.claude/hooks/session-start.sh` does this in cloud sessions)
- Check before every push: `./scripts/check.sh` (ruff lint, ruff format check, pytest; CI runs the same script)
- Generate: `uv run assetgen --seed 42 --out build/assets --preview build/preview.png`
- One test: `uv run pytest -q tests/test_generators.py::test_same_seed_gives_identical_geometry`

## Conventions

- Assets are built at the origin: centred in X/Y, base on z=0 (rocks sink `ROCK_SINK` of their height below it).
  Engines place props by setting position, so baked offsets are bugs. Tests enforce this.
- Output depends only on the seed. Generators take a `random.Random`; never use global `random` or time.
  `test_export_is_byte_for_byte_reproducible` checks the `.glb` bytes.
- Triangle budgets live in `TRI_BUDGET` (`src/assetgen/generators.py`). Raise them deliberately, not to make a test pass.
- `build_set()` resets the whole Blender scene. Test fixtures return paths and manifests, never live `bpy` objects.
- `manifest.json` has no timestamps or absolute paths, so its diff shows what a generator change did.

## Verifying changes

- Visual changes: regenerate the preview and look at the PNG (Read it) before pushing. Tests cannot judge looks;
  the first preview of this project showed a cropped camera, overlapping props and a wrong sky colour.
- Put in the PR: what changed, `./scripts/check.sh` result, manifest differences, and what the preview showed.
- CI uploads `build/` (assets + preview) as the `assets-seed-42` artifact and writes a manifest table to the job summary.

## Environment notes

- `bpy` wheels support exactly one Python minor: bpy 5.2.x needs Python 3.13. Bump them together.
- Cloud sessions block download.blender.org; `bpy` comes from PyPI (about 400 MB, about 12 s cold install).
- Render previews with Cycles on the CPU only. EEVEE needs a GPU/libEGL and kills the process (no exception) here.
- "Draco is not available" / "MeshOptimizer is not available" ERROR lines on export are harmless: optional
  glTF compression libraries missing from the PyPI wheel. We don't use them.
- Blender 5 worlds already have a node tree; set the Background node's colour (`world.color` is ignored and
  `World.use_nodes` is deprecated).
- CI (GitHub Actions) apt-installs the X11/GL libraries `bpy` links against; see `.github/workflows/check.yml`.

## Not yet in the repo

Godot is planned to consume these `.glb` files. It was proven to work in a cloud session (Godot 4.7.2 built from
source in about 22 min, since Godot's downloads and GitHub release assets are blocked by the session network
policy; headless import, GDScript tests and Xvfb + Mesa llvmpipe screenshots all worked). Allowing `github.com`,
`objects.githubusercontent.com` and `release-assets.githubusercontent.com` in the environment would let a setup
script download official binaries instead.
