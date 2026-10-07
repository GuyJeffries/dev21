# CLAUDE.md

Procedural Art Deco arcology generator. **Read `docs/PLAN.md` before starting work**: it sets the architecture,
conventions and phases. Phases 0 (foundations), 1 (massing and first facade), 2 (arcology composition), 3
(facade grammar: notched shapes, pilasters, zones, cornices, doors, ornament) and 4 (style and variation: every
style setting wired, style envelope, sweep and batch sheets) are done; Phase 5 (representation levels) is next.

Development happens in Claude Code cloud sessions. The user reviews pull requests rather than running code, and has
limited bandwidth: keep everything verifiable in the cloud and review evidence small (contact sheets, metric tables).

## Commands

- Setup: `uv sync` (the SessionStart hook in `.claude/hooks/session-start.sh` does this in cloud sessions)
- Check before every push: `./scripts/check.sh` (ruff lint, ruff format check, pytest; CI runs the same script)
- Contact sheet of the golden seeds at L2: `uv run arcology sheet specs/default.json -o build/review`
  (writes `contact_sheet.jpg`, `metrics.md`, `metrics.json`, and per-seed plan, library and tile)
- Close-ups at L0 (entrance, sister-tower cluster at its transfer floor, the central tower's first setback, its
  crown): `uv run arcology detail specs/default.json -o build/detail` (`detail_sheet.jpg`; about 3 minutes, since
  each building is ~25,000 placed copies at L0)
- Sweep sheet, one parameter per row on one seed (default: every style setting):
  `uv run arcology sweep specs/default.json -o build/sweep` (`sweep_sheet.jpg`, `sweep.md`; about 90 s); any
  parameter with `--set style.hierarchy=strong,weak --set secondary_towers.count=0,3,6`
- Batch of 100 seeds as L3 silhouettes, with the style envelope's ranges:
  `uv run arcology batch specs/default.json -o build/batch` (`batch_sheet.jpg`, `batch.md`; about 60 s)
- Spec to plan, no Blender: `uv run arcology resolve specs/default.json --seed 7 -o plan.json`
- Plan to element library + manifest: `uv run arcology build plan.json -o build/seed-7 --lod L2`

## Layout (`src/arcology/`)

| Module | Role | Blender? |
|---|---|---|
| `spec.py` | Schema v0: dataclasses, strict loading, ranges | No |
| `seeds.py` | Per-element seeds from ID paths (blake2b) | No |
| `plan.py` | Resolved plan: `Element`, `Plan`, arrays and `instances()`, element keys, bounds | No |
| `rules.py` | Shared primitives: sampling, grid snapping, mass elements, outlines (`outline`, notches), LOD sets | No |
| `resolve.py` | The grammar's order: podium, central tower, secondary towers, facades, composition | No |
| `compose.py` | Composition: secondary towers in rings, bridges, transfer bands, crowns, parapets | No |
| `facade.py` | Facades: corners, pilasters and piers, windows by zone, portals, cornices, merlons, ornament density | No |
| `metrics.py` | Structural checks (massing, facades, symmetry, dominance, bridges, crowns, clearance), style envelope | No |
| `build.py` | Box-built recipes; plan → element library (.glb) + placement manifest | Yes |
| `assemble.py` | Stand-in assembler: manifest → instanced scene (expands arrays) | Yes |
| `review.py` | Contact (L2), detail (L0), sweep (L2) and batch (L3) sheets; Cycles CPU + Pillow, golden seeds | Yes |

## Conventions

- **The grammar stays plain Python.** `spec`, `seeds`, `plan`, `rules`, `resolve`, `compose`, `facade` and
  `metrics` must never import `bpy`;
  `test_pure_python.py` enforces it. Import Blender modules lazily from the CLI.
- **Units:** metres, Z up. Heights are whole floors (`floor_height`); widths and depths are whole bays
  (`facade.bay_width`).
- **Frames:** a mass's translation is its base centre. A facade element's origin is on the envelope plane at
  the base centre of its bay, local -Y outward, +X left-to-right seen from outside; `rotation_z_deg` turns it to
  its facade (south 0, east 90, north 180, west 270). Every element carries its local `extent`, and each recipe's
  mesh must match it exactly (`test_every_recipe_mesh_matches_its_element_extent`).
- **Outlines:** a mass's footprint is `rules.outline()`: a rectangle, or one with every corner notched. Facades,
  corners, rings (bands, cornices, parapets) and checks all walk its edges; never assume four faces.
- **Repetition:** windows, piers and merlons are array elements; an axis may have a `stride` (pilasters every k
  bay lines). A copy's id comes from the array's `prefix` plus its facade-wide grid position
  (`.../facade.south/bay.007/floor.012`, `.../facade.south/pier.012`), never from how the grid was split into
  blocks or zones. Window identity must survive layout changes (`test_window_identity_survives_a_different_entrance`,
  `test_window_identity_survives_a_different_rhythm_and_zones`).
- **Levels:** envelope boxes are L3; cores, piers, corners and cornices L0-L2; windows, portals, parapets and
  merlons L0-L1; window channels (one per bay column of a window block, standing in for its windows) L2 only.
- **Style:** every `style` setting scales rules through tables (`rules.HIERARCHY`, `rules.SETBACK_STRENGTH`,
  `facade.STANDING_ORNAMENT`), never by picking assets; docs/PLAN.md section 11 lists what each does. The plan
  carries its style (`Plan.style`) so checks can read it: dominance targets follow the hierarchy, and mirror
  symmetry is only required of bilateral styles. A new setting needs a sweep row (`review.STYLE_SWEEPS`) that shows
  it doing something; three settings first passed every test while changing nothing visible.
- **Style envelope:** `proportioned`, `tapered`, `grounded`, `restrained` (bounds in `metrics.py`) keep every seed
  and setting recognisably Art Deco. No secondary tower is ever more slender than the central tower, and
  pavilions stand lower than every sister tower; widen a bound only with a picture showing it still reads as Deco.
- **Ornament:** gated by density rho = `style.ornament_density` x the mass's standing (`facade.STANDING_ORNAMENT`);
  each system switches on above a threshold. Add new ornament the same way, so it follows the hierarchy
  (`ornament_hierarchy` checks it).
- **Order of decisions:** podium, then central tower, then secondary towers, then facades, then composition
  elements. Later steps read earlier decisions but never change them: secondary towers can't move the central
  tower (`test_secondary_towers_never_change_the_podium_or_central_massing`), facades can't change massing.
- **Composition:** secondary towers come in mirror twins (plus north-south axis towers for odd counts). Twins share
  every decision through their group seed (`Tower.seed`); giving a twin its own seed breaks symmetry. Ring 0 sister
  towers bridge to the central tower on one shared transfer floor; outer-ring pavilions fill their terrace, stay
  squat (`PAVILION_SLENDERNESS`) and bridge into the next tier's wall. Only the central tower takes
  `style.termination`.
- **Tags:** facade elements carry `mass`; tower sections carry `tower` and `stands_on`; bridges `from` and `to`.
  Metrics rely on these, not on parsing ids.
- **Off-centre masses:** anything placed relative to a mass must add the mass's own translation. Phase 2's first
  sister towers had their whole facade inside the central tower until this was fixed; `dressed` now checks it.
- **Seeds:** every random decision uses `rng(element_seed, "decision-name")`, with element seeds from
  `path_seed`/`derive_seed`. Never use global `random`, `hash()`, or a stream shared between elements.
  `test_changing_the_podium_does_not_reshuffle_the_tower` guards this.
- **IDs:** stable role/position paths (`arcology/tower.central/section.2`), not generation order.
- **Schema changes:** unknown fields are errors. A breaking change bumps `arcology-spec/N` and comes with a migration.
  `test_seed_values_are_pinned` must never be edited to make it pass: changing seeds changes every building.
- **Instancing:** a library entry per unique (recipe, params, LOD), and one manifest row per plan element (arrays
  stay compact). Don't rely on exporters for instancing.
- **Geometry:** recipes are lists of parts with materials: boxes, and prisms (a polygon in x-z extruded along y)
  for diagonals such as chevrons. Parts may touch but must never share a face pointing the same way (it flickers in
  rasterisers such as Unreal's); `test_no_two_parts_share_a_face_pointing_the_same_way` checks every recipe. Across
  elements, stand slightly proud instead (merlons stand 0.15 m in front of the parapet's face).

## Verifying changes

- Grammar or visual changes: run the contact sheet, and the detail sheet for anything at facade scale, and look at
  them (Read the JPEGs) before pushing. Tests cannot judge whether it looks designed: the first facade passed every
  check but read as a punched-window office grid until the stone between piers was removed, and the first secondary
  towers passed every check but read as thin fins stuck to the central tower until they became sister towers and
  terrace pavilions. In Phase 3 the contact sheet showed none of the new zones until L2 got window channels, and
  1.5 m merlons vanished at mid range until they became 3 m pylons. When a picture shows a defect the checks
  missed, add the check.
- Style changes: run the sweep sheet (does each setting visibly do what it says?) and the batch sheet (does every
  seed still read as the same family?). The first horizontal facades passed every check but read as a punched
  grid until the piers between windows gave way to glass.
- Put in the pull request: what changed, the `./scripts/check.sh` result, metric changes, and what the sheet showed.
  Send the sheets to the user in the session too. CI uploads all four as the small `review-sheets` artifact (full
  outputs in `review-full`) and posts `metrics.md`, `batch.md` and `sweep.md` to the job summary.

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
