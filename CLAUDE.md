# CLAUDE.md

Procedural Art Deco arcology generator. **Read `docs/PLAN.md` before starting work**: it sets the architecture,
conventions and phases. Phase 0 (foundations) is done; Phase 1 (massing and first facade) is next.

Development happens in Claude Code cloud sessions. The user reviews pull requests rather than running code, and has
limited bandwidth: keep everything verifiable in the cloud and review evidence small (contact sheets, metric tables).

## Commands

- Setup: `uv sync` (the SessionStart hook in `.claude/hooks/session-start.sh` does this in cloud sessions)
- Check before every push: `./scripts/check.sh` (ruff lint, ruff format check, pytest; CI runs the same script)
- Contact sheet of the golden seeds: `uv run arcology sheet specs/default.json -o build/review`
  (writes `contact_sheet.jpg`, `metrics.md`, `metrics.json`, and per-seed plan, library and tile)
- Spec to plan, no Blender: `uv run arcology resolve specs/default.json --seed 7 -o plan.json`
- Plan to element library + manifest: `uv run arcology build plan.json -o build/seed-7 --lod L2`

## Layout (`src/arcology/`)

| Module | Role | Blender? |
|---|---|---|
| `spec.py` | Schema v0: dataclasses, strict loading, ranges | No |
| `seeds.py` | Per-element seeds from ID paths (blake2b) | No |
| `plan.py` | Resolved plan: `Element`, `Plan`, JSON, bounds | No |
| `resolve.py` | The grammar: spec → plan | No |
| `metrics.py` | Structural checks on a plan | No |
| `build.py` | Recipes; plan → element library (.glb) + placement manifest | Yes |
| `assemble.py` | Stand-in assembler: manifest → instanced scene | Yes |
| `review.py` | Contact sheets (Cycles CPU + Pillow), golden seeds | Yes |

## Conventions

- **The grammar stays plain Python.** `spec`, `seeds`, `plan`, `resolve` and `metrics` must never import `bpy`;
  `test_pure_python.py` enforces it. Import Blender modules lazily from the CLI.
- **Units:** metres, Z up. Heights are whole floors (`floor_height`); widths and depths are whole bays
  (`facade.bay_width`). An element's translation is its base centre; library meshes are built centred at the origin.
- **Seeds:** every random decision uses `rng(element_seed, "decision-name")`, with element seeds from
  `path_seed`/`derive_seed`. Never use global `random`, `hash()`, or a stream shared between elements.
  `test_changing_the_podium_does_not_reshuffle_the_tower` guards this.
- **IDs:** stable role/position paths (`arcology/tower.central/section.2`), not generation order.
- **Schema changes:** unknown fields are errors. A breaking change bumps `arcology-spec/N` and comes with a migration.
  `test_seed_values_are_pinned` must never be edited to make it pass: changing seeds changes every building.
- **Instancing:** a library entry per unique (recipe, params, LOD), and manifest rows per placement. Don't rely on
  exporters for instancing.

## Verifying changes

- Grammar or visual changes: run the contact sheet and look at it (Read the JPEG) before pushing. Tests cannot judge
  whether it looks designed.
- Put in the pull request: what changed, the `./scripts/check.sh` result, metric changes, and what the sheet showed.
  Send the sheet to the user in the session too. CI uploads it as the small `contact-sheet` artifact (full outputs
  in `review-full`) and posts `metrics.md` to the job summary.

## Environment notes

- `bpy` wheels support exactly one Python minor: bpy 5.2.x needs Python 3.13. Bump them together.
- Cloud sessions block download.blender.org; `bpy` comes from PyPI (about 400 MB, about 12 s cold install).
- `import bpy` before `mathutils`; `mathutils` only exists once bpy is loaded.
- Render with Cycles on the CPU only. EEVEE needs a GPU/libEGL and kills the process (no exception) here.
- Cameras: set `clip_end` explicitly (the 100 m default cuts off buildings), and set the render resolution before
  `camera_fit_coords`.
- "Draco is not available" / "MeshOptimizer is not available" ERROR lines on glTF export are harmless.
- Blender 5 worlds and materials already have node trees; set the node inputs (`World.use_nodes` is deprecated).
- CI (GitHub Actions) apt-installs the X11/GL libraries `bpy` links against; see `.github/workflows/check.yml`.
- Unreal and Houdini can't run in the cloud. Godot can, built from source (about 22 min); see `docs/PLAN.md` App. A.
