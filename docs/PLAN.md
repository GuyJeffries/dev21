# Arcology Generator: Project Plan

**Status:** Phases 0 to 4 complete (2026-10-07). Phase 4b (scale layers and contrast, [`LAYERS.md`](LAYERS.md)) under
way: the layer tree, and courses with the luxury/functional programme split, are built; treatments next. Then
Phase 5.

Revision 2 (2026-10-07). Revises the original proposal after review. This plan is a starting point, not the full
scope: the objective right now is to get it working, with "exciting retro-futurist arcologies" as a later pass.

## What changed from revision 1

- **Spelling:** arcology, throughout and in code.
- **Three layers, not two.** The grammar moves out of the Blender add-on into plain Python. Blender, and later
  Houdini or Unreal, only turn a resolved plan into geometry. This is what makes "independent of Blender" real.
- **The schema is explicit and versioned from day one**, with units and a floor module fixed now.
- **Seeds are derived per element** from the element's ID path, so changing one part doesn't reshuffle the rest.
- **Instancing is designed in** through an element library and a placement manifest. Blender's exporters don't
  preserve instancing on their own (tested, see Appendix A).
- **Cloud-first.** Development and review happen in cloud sessions. Unreal is deferred, and Blender acts as a
  stand-in world assembler so the move to Unreal becomes a port of a thin layer, not a redesign.
- **Phases re-cut:** a thin Phase 0 for foundations; a Blender district before any Unreal work.
- **Measurable checks** sit alongside visual judgement, and contact sheets are the main review tool.
- **Geometry Nodes where it pays**, generated from code. Python mesh building (bmesh) comes first.

---

## 1. Purpose

Develop a procedural architectural system that generates enormous Art Deco-inspired arcologies from a small,
reusable vocabulary of architectural rules and primitives.

Architecture is described rather than modelled. A building is a structured specification, interpreted by procedural
geometry tools and ultimately rendered as part of a very large scene.

Pipeline: **architectural specification → procedural construction → world/scene.** The specification and the
grammar stay independent of any one application, so Blender, Houdini or a future dedicated editor can be
alternative implementations. Early prototypes are Blender only.

Overall goal: *a system to procedurally generate endless exciting retro-futurist arcologies and supporting
stylised structures.*

### Core principle

Architecture is a grammar, not a library of buildings. A building is a program composed of smaller programs:

```
building → sections → elements → atoms → geometry
```

The aim is a small number of powerful rules that generate a very large architectural vocabulary.

## 2. Goals and non-goals

### Primary goals

- Generate large, distinctive Art Deco arcologies procedurally.
- Create architectural variation without thousands of bespoke assets.
- Make architectural relationships explicit: proportion, hierarchy, symmetry, repetition, attachment, scale,
  negative space, termination.
- Produce buildings that are structurally coherent, not collections of interesting shapes.
- Generate different representations of the same building for different viewing distances.
- Allow individual architectural parameters to be edited and explored.
- Export large scenes efficiently into Unreal.
- Keep the architectural description independent of the rendering engine.
- Eventually support cinematic views where one generated building can be recognised from another building's windows
  or streets.

### Non-goals (for now)

- Complete interiors for every building.
- A general-purpose procedural modelling application, or a Houdini replacement.
- A giant catalogue of unique architectural meshes.
- A Godot editor before the architectural system is proven.
- Every visible object at maximum detail.
- Unreal integration at scale before Phase 7.
- Node graphs hand-authored in `.blend` files as a source of truth. They can't be diffed or reviewed in pull requests.
- An interactive UI before parameter sweep sheets (section 20) show it's needed.

## 3. Working constraints

- **Development happens in Claude Code cloud sessions.** You review pull requests rather than running code.
- **Bandwidth is limited.** Few round trips; review evidence must be small (compressed contact sheets, metric
  tables). Judging a change must never require downloading large builds.
- **The cloud container runs Blender headless** (`bpy` 5.2 from PyPI, Cycles on the CPU, no GPU). Unreal and Houdini
  aren't available there.
- **You have Blender and Unreal locally**, to be used sparingly: occasional checks, not a daily loop.

Consequences:

- Everything that can be checked automatically must run headless in the cloud.
- Blender stands in for Unreal as the world assembler until Phase 7.
- The handover to Unreal is a data package designed now and exercised later.

## 4. Target architectural model

The fundamental generated object is the **arcology**: one enormous integrated building, not a collection of
unrelated towers.

**Target scale** (decided 2026-10-07, see [`LAYERS.md`](LAYERS.md) section 12): a square base 2 km x 2 km and an
overall height of 2 km. The visible base is the upper half of a diamond (the lower half is buried foundations): a
pyramid rising about 1 km to a peak buried inside a fat central tower. Today's buildings are about a quarter of
that size.

```
ARCOLOGY
├── Primary mass ........ pyramid / stepped podium
├── Central tower ....... dominant continuous mass
├── Secondary towers .... 0 to 9 of them
├── Connections ......... bridges, terraces, galleries, transfer floors
├── Facade grammar ...... bays, windows, doors, panels, vertical elements, ornament
└── Internal life ....... residential, commercial, entertainment, transport, public/civic
```

Secondary towers are not independent towers placed beside the main one. Their dimensions, positions and relationships
are constrained by the central building, so the result reads as one architectural object.

## 5. System architecture

```
 ARCOLOGY SPEC (JSON, versioned)        what you edit; the source of truth
        │
        ▼
 RESOLVER (plain Python, no Blender)    the grammar: rules, constraints, style, seeds
        │
        ▼
 RESOLVED PLAN (JSON)                   every element placed, identified and tagged
        │
        ▼
 ELEMENT BUILDER (Blender)              each unique (recipe, params, LOD) → one mesh
        │
        ├──► ELEMENT LIBRARY            one .glb per unique element per LOD
        └──► PLACEMENT MANIFEST         element key + transform + ID + tags, per instance
                     │
                     ▼
               ASSEMBLER                manifest → instanced scene
               Blender now (review renders, district tests)
               Unreal later (Phase 7: same manifest, ported assembler)
```

| Layer | Owns | Depends on |
|---|---|---|
| Spec | Architectural intent: dimensions, style, counts, relationships, seed | Nothing |
| Resolver | The grammar: placement, constraints, symmetry, repetition, setbacks, seeds, IDs, tags | Spec only (plain Python) |
| Resolved plan | The full list of elements: what, where, which LOD, tagged | Produced by the resolver |
| Element builder | Turning one recipe + params into geometry | Blender (later also Houdini) |
| Assembler | Placing library meshes as instances to form a scene | Blender now, Unreal later |

Why this split:

- **Portability.** Houdini or Unreal only need to implement the builder and assembler against the same plan.
- **Testability.** Structural rules are tested on the resolved plan in milliseconds, without Blender.
- **Identity.** Every window, bay and tower has a stable ID path, which section 10's interior and cinematic
  continuity depends on.
- **Instancing.** Identical elements share one library mesh; the manifest lists placements.
- **Editors.** A future Godot editor, or a Blender panel, reads and writes the same spec.

## 6. Data model

### 6.1 Specification (schema v0)

Small, explicit and versioned. Missing fields take documented defaults; unknown fields are errors. A breaking change
bumps the version and comes with a migration.

```json
{
  "schema": "arcology-spec/0",
  "seed": 18472,
  "units": "m",
  "floor_height": 4.0,
  "style": {
    "symmetry": "bilateral",
    "dominant_axis": "vertical",
    "hierarchy": "strong",
    "ornament_density": 0.65,
    "setback_strength": "high",
    "repetition": "regular",
    "termination": "stepped"
  },
  "primary_mass": { "form": "stepped_podium", "width": 600, "depth": 600, "tiers": [8, 6, 4] },
  "central_tower": { "width": 120, "depth": 120, "floors": 105, "setbacks": [40, 70, 90] },
  "secondary_towers": { "count": 6, "placement": "radial", "height_ratio": [0.4, 0.7] },
  "facade": { "bay_width": 6.0, "window": "deco_tall", "density": 0.8 }
}
```

`tiers` and `setbacks` are in floors, not metres. See section 7.

### 6.2 Resolved plan

A tree of elements produced by the resolver. Each element records:

```json
{
  "id": "arcology/tower.central/section.2/facade.north/bay.07/window.03",
  "kind": "window",
  "recipe": "window.deco_tall",
  "params": { "width": 1.8, "height": 3.2, "recess": 0.3, "mullions": 2 },
  "transform": { "translation": [12.0, -60.0, 84.0], "rotation_z_deg": 0 },
  "floor": 21,
  "lod": ["L0", "L1"],
  "tags": { "program": "residential", "facing": "north" },
  "seed": 9183402711
}
```

### 6.3 Element library and placement manifest

- **Element key:** a hash of (recipe, params, LOD). Each unique key is built once into a mesh in the element library.
- **Placement manifest:** one row per instance: element key, transform, element ID, tags.
- **Together they are the Unreal handover package.** The Unreal assembler (Phase 7) imports the library as static
  meshes and creates instances from the manifest.

## 7. Conventions

- **Units:** metres, Z up, right-handed. Facade names: north = +Y, east = +X. Conversion to Unreal's centimetres and
  axes happens only in the Unreal assembler.
- **Floor module:** `floor_height` (default 4.0 m) is the vertical unit. Setbacks, terraces, bridges, transfer floors
  and window rows all sit on floor boundaries. `bay_width` is the horizontal unit on facades.
- **Seeds:** each element's seed is derived from its parent's seed and its ID path with a stable hash (`hashlib`),
  never Python's `hash()` (randomised per process) and never one shared random stream. Changing the number of
  secondary towers must not change the central tower's facade, and a test enforces this.
- **Determinism:** the same spec gives a byte-identical resolved plan and element library.
- **IDs:** stable paths built from role and position (`tower.ne.1`, `facade.north`, `bay.07`), not generation
  order, so adding a sibling doesn't rename existing elements.

## 8. Architectural grammar

| Level | Purpose | Examples |
|---|---|---|
| Style | Defines the visual grammar | Deco, symmetry, vertical emphasis |
| Atom | Primitive architectural operation | Box, plane, cylinder, recess |
| Element | Reusable architectural component | Window, door, pilaster |
| Section | Larger architectural composition | Facade bay, podium tier, tower section |
| Building | Complete architectural object | Arcology |
| District | Buildings in their environment | Several arcologies and supporting structures |

**Initial primitives:** BOX, PLANE, CYLINDER, ARCH, STEP, GROOVE, RECESS, EXTRUSION.
**Operations:** scale, offset, repetition, mirroring, stacking, subdivision, inset, projection.

The objective is not every possible primitive. It is the smallest vocabulary that produces convincing variation.

## 9. Architectural modules

- **Structural:** primary mass, podium, central tower, secondary tower, setback, bridge, terrace, gallery, crown,
  parapet.
- **Facade:** facade section, bay, window, door, panel, vertical strip, pilaster, column, cornice.
- **Decoration:** stepped motif, chevron, sunburst, geometric band, fluting, relief frame.

**Assets** (statues, reliefs, signage, lamps, vehicles, people, furniture, unusual machinery, bespoke artwork) are
hand-made where individual identity matters, but their architectural hosting is procedural:

```
STATUE (asset) → procedural plinth → procedural recess → procedural framing → procedural lighting
```

In the resolved plan an asset is an element with `kind: "asset_slot"`. The assembler fills the slot.

## 10. Windows and doors

A window is not a mesh called `ArtDecoWindow01`; it is an architectural intention.

```
Window: opening → recess → frame → glazing → mullions → vertical emphasis → cap / sill
Door:   opening → door → frame → surround → threshold → canopy / projection → upper composition
```

**Parameters:** proportion, scale, number, pairing, triplets, banks, recess, projection, frame depth, mullions,
ornament, hierarchy, repetition. A major entrance comes from the same language as a service door.

**Identity:** from Phase 1, every window in the resolved plan carries building, facade, bay, floor, position,
orientation and type. Interior connection and exterior view are added later. This makes the cinematic continuity in
section 19 possible without generating every interior.

## 11. Style system

Style is encoded as constraints, not assets. It's a section of the spec, read by the resolver:

```
symmetry = bilateral        dominant_axis = vertical     hierarchy = strong
ornament_density = 0.65     setback_strength = high      repetition = regular
termination = stepped
```

It controls proportion, symmetry, hierarchy, dominant axis, repetition, setback rhythm, ornament density, material,
silhouette, negative space and termination. The same modules then produce many buildings in one recognisable language.

As built (Phase 4), each setting scales rules rather than choosing assets:

| Setting | Effect |
|---|---|
| `symmetry` | `bilateral`: mirror twins share every decision. `none`: twins draw their own heights, sizes and crowns, and slots fill singly, so an odd count leaves a tower unpaired |
| `dominant_axis` | `vertical`: continuous piers, pilasters every few bays. `horizontal` (streamline): no pilasters; stone spandrel bands run unbroken over piers that give way to glass, so each floor reads as a ribbon |
| `hierarchy` | `strong` / `moderate` / `weak`: secondary towers taller, broader and closer, with less height falloff by ring and a lower dominance target (1.3 / 1.2 / 1.1); ornament spread more evenly |
| `ornament_density` | The central tower's; other standings take a share that the hierarchy sets |
| `setback_strength` | `high` / `medium` / `low`: the drawn setback inset at full or 60%, and at `low` only every other setback (steps can't shrink below a bay) |
| `repetition` | `regular`: one facade system. `varied`: each tower group draws its own density, mullions and pilaster rhythm; twins share theirs |
| `termination` | The central tower's crown: `stepped`, `spire` or `flat` |

**Style envelope.** Checks that keep every setting recognisably Art Deco: the central tower's slenderness stays
within 2-8 and no secondary tower is more slender than it (no needles, no stubs), it tapers to 25-95% of its base
width (no slab), the podium is 8-45% of the floors (a base to stand on), a single spire takes at most a quarter of
the tower's height, and ornament stays below 2.5 pieces per facade cell. The 100-seed batch sheet shows the
silhouettes and the envelope's ranges on every push.

## 12. Architectural consequence system

The architecture embodies the dystopia without announcing it. It represents the utopian ideals of its period
(glamour, luxury, privacy, status, leisure, sunlight, views, convenience, exclusivity), and every ideal has physical
consequences:

```
IDEAL                    private flying-car access
REQUIREMENT              elevated private landing platform
PHYSICAL CONSEQUENCES    height, exposure, wind, aircraft traffic, security, noise, maintenance, distance from ground
```

> The architecture doesn't tell you that it is dystopian. The architecture accidentally demonstrates that it is.

**Implementation:** the schema reserves `program` and `provision` tags from v0 (for example
`provision: private_landing`). Consequences later become resolver rules that add physical requirements, not generic
decay or grime. The system itself is scheduled after Phase 4.

## 13. Representation levels

The same description generates progressively cheaper representations:

| Level | Contents |
|---|---|
| L0 Hero | Full grammar, detailed facade, windows, doors, ornament, assets, selected interiors |
| L1 Architectural | Major massing, facade rhythm, simplified windows, large ornament |
| L2 Silhouette | Major masses, tower relationships, large verticals, significant facade rhythm |
| L3 Horizon | Overall silhouette, major verticals, colour/value, distinctive landmarks |

- A level is a filter on which elements exist, plus how each element kind is built at that level.
- Each level has budgets for unique meshes, instances and triangles, recorded in the metrics. The numbers are set in
  Phase 5.
- **Unreal note:** Nanite reduces geometric detail automatically, so in Unreal, element and instance counts and
  materials matter more than triangle counts. The levels should therefore define which details exist at each
  distance; polygon reduction is secondary.

The world contains descriptions and representations, not thousands of unique high-resolution buildings.

## 14. Blender's role

1. **Element builder:** bmesh first. Geometry Nodes, generated from code, for repetition-heavy recipes where it
   pays (tested to work headless).
2. **Stand-in assembler:** builds scenes from the placement manifest using instancing. This is what the Unreal
   assembler will later do.
3. **Review renderer:** contact sheets, sweep sheets and distance sheets, rendered with Cycles on the CPU.
4. **Optional local add-on** (Phase 4 or later): the same package installed in your local Blender with a small panel
   for spec parameters. This gives local interactivity without a cloud round trip. Your Blender version must match
   the `bpy` version (currently 5.2).

## 15. Unreal's role

Unreal remains the world, camera and rendering machine: the enormous scene, terrain, placement, streaming, instancing,
LOD/HLOD, lighting, atmosphere, camera work, cinematics and final render. The generator doesn't try to solve those
problems.

**Deferred to Phase 7. It's ready by construction:**

- The handover package (element library, placement manifest, material list) is defined and tested in the cloud.
- The Blender assembler mirrors what the Unreal assembler will do, so Phase 7 ports a thin layer.
- Planned Unreal side:
  - a Python editor script imports the library as static meshes and builds instanced static meshes (ISM/HISM) or
    feeds Unreal's procedural tools (PCG);
  - Nanite enabled;
  - World Partition for streaming.
- **Open questions only Unreal can answer, deferred to Phase 7:**
  - material translation;
  - Nanite combined with instancing at arcology scale;
  - HLOD strategy;
  - import time for very large manifests.

## 16. Houdini

Houdini remains the strongest mature tool for procedural architecture. Under this architecture it's an alternative
builder and assembler for the same resolved plan, with a direct route into Unreal through Houdini Engine. It's
evaluated if the grammar strains Blender or Python (Gate 4). It isn't available in the cloud.

## 17. Godot editor (possible future)

A dedicated front end for graph editing, module selection, parameter editing, relationship visualisation, presets and
validation, reading and writing the spec JSON. Build it only if the local Blender add-on proves to be the bottleneck
(Gate 2). Otherwise the project risks becoming a UI project before the architectural system is understood.

## 18. Development phases

| Phase | Goal | Where |
|---|---|---|
| 0 | Foundations: schema, resolver skeleton, seeds, review pipeline | Cloud |
| 1 | Massing and first facade | Cloud |
| 2 | Arcology composition | Cloud |
| 3 | Facade grammar | Cloud |
| 4 | Style and variation | Cloud (optional local add-on) |
| 4b | Scale layers and contrast ([`LAYERS.md`](LAYERS.md)) | Cloud |
| 5 | Representation levels | Cloud |
| 6 | District assembled in Blender | Cloud |
| 7 | Unreal integration | Local, when bandwidth allows |
| Later | Interiors through windows, consequence system, Houdini, Godot | Mixed |

### Phase 0: Foundations

**Build:**
- New package layout: `spec`, `resolve`, `build`, `assemble`, `review`.
- Schema v0 with validation and defaults.
- Seed derivation.
- Resolved-plan writer.
- Element library and manifest writer.
- Contact-sheet renderer plus a CI metrics table.
- Retire the rocks-and-trees placeholder; the harness carries over.

**Done when:**
- A spec produces a deterministic plan.
- A test proves changing one parameter only changes its own part of the plan.
- CI posts a contact sheet of plain massing boxes.

### Phase 1: Massing and first facade

**Build:**
- BOX, STEP, RECESS and EXTRUSION; repetition; symmetry.
- Stepped podium; central tower with setbacks on the floor grid.
- One bay system, one full window recipe, one main-entrance door recipe.
- L0 and L2.

**Done when:** a 12-seed contact sheet shows buildings that are visibly different but stylistically related, and the
structural metrics pass.

### Phase 2: Arcology composition

**Build:**
- 0 to 9 secondary towers with constrained placement.
- Bridges, terraces, galleries and transfer floors.
- Crowns and termination.

**Done when:** the building reads as one enormous building, not a tower with attachments, and the dominance,
containment, connection and symmetry metrics pass.

**As built:** sister towers in ring 0 (at most one per central face, so they can be substantial) bridge to the
central tower on one shared transfer floor marked by stone bands; outer-ring pavilions fill the lower terraces,
stay squat and bridge into the next tier's wall; every tower is crowned and only the central one takes the spire.
The first attempt, three slim towers per lane, passed every check but read as fins stuck to the central tower.

### Phase 3: Facade grammar

**Build:**
- Window and door variants.
- Bays, pilasters, panels, vertical elements, cornices.
- Two or three ornament systems (stepped motif, chevron, fluting).
- Ornament density and hierarchy.

**Done when:** large variation emerges without bespoke assets, and ornament reinforces hierarchy instead of becoming
noise.

**As built:** the middle scale, between massing and windows. Shapes: towers may have notched corners, and podium
tiers below the top a notch no deeper than a tier step (the extrusion primitive and outline-following rings make
any rectilinear outline possible). Facades: pilasters on every k-th bay line, set out symmetrically from each
facade's centre, with the piers between set back; base, shaft and capital zones with their own windows; a stepped
cornice on every mass; doors at the foot of every tower. Ornament: chevrons on capital panels, fluted pilasters
and stepped merlons over parapets, switched on by an ornament density (`style.ornament_density` scaled by each
mass's standing: central 1.0, sister 0.8, podium 0.7, pavilion 0.6), so ornament gathers on the central tower.
At L2, one channel per bay column stands in for each window block, so the zones read at a distance; the first
contact sheet of this phase showed none of them, because windows are L0-L1 only.

### Phase 4: Style and variation

**Build:**
- Style parameters, controlled randomness, symmetry and density controls, massing and facade variation.
- Parameter sweep sheets.
- Optional local Blender add-on panel.

**Done when:** a 100-seed batch stays recognisably in style, checked for accidental Gothic or fantasy drift.

**As built:** every style setting is wired (section 11), the style envelope checks drift automatically, and CI renders
a sweep sheet (each style setting along a row, one seed) and a 100-seed batch sheet at L3 with the envelope's
ranges. The first sweep showed three settings with no visible effect: medium and low setbacks were identical (steps
round to whole bays), a weak hierarchy changed nothing (narrow sister towers were capped by the new slenderness
rule), and asymmetric twins came out equal; each now changes the building. The first horizontal facades read as a
punched-window grid until the piers between windows gave way to glass. The envelope also caught real drift in the
grammar: sister towers 12 m wide and 300 m tall (slenderness 25), now capped at the central tower's slenderness,
which in turn needed pavilions held below the shortest sister. The optional local add-on is not built (Gate 2).

### Phase 4b: Scale layers and contrast

**Build:** an explicit tree of scale layers on every facade (band, panel, cell), with regions that stop subdividing
early (fields, openings with spaces behind, recesses, giant orders), placed by composition; regions recorded in the
plan as targets for later design language. Design and steps in [`LAYERS.md`](LAYERS.md).

**Built so far:** step 1, every face a layer tree whose leaves generate their elements, drawn by the elevation sheet;
step 2, courses (base, foot, runs, sky lobbies on one building-wide rhythm, bridge seams, capital) and every leaf
graded luxury or functional by composition (`program.luxury`), so exceptions have places to go. Free placements
(a building's tone, with large-layer gestures in 15% to 20% of buildings) are decided and come after the
treatments.

**Done when:** the buildings show events at several scales against a calm texture, and still read as Art Deco.

### Phase 5: Representation levels

**Build:** L0 to L3 with budgets; distance sheets showing one building at each level.

**Done when:** the building keeps its identity as it gets cheaper, and the budgets are met.

### Phase 6: District assembled in Blender

**Build:**
- A district spec that places many arcologies and supporting structures.
- The assembler with instancing.
- Measurements of Blender's limits.
- Freeze the handover package at v1.

**Done when:** a district renders in the cloud from library plus manifest, and the handover package is documented
and stable. This is the stepping stone to Unreal.

### Phase 7: Unreal integration

**Build:**
- Port the assembler to an Unreal Python editor script.
- Import a district.
- Nanite, instancing, World Partition, materials, cameras.

**Done when:** the district loads and streams in Unreal from the handover package, without per-building
hand-authoring.

## 19. First vertical slice (Phases 0 and 1)

Deliberately small:

- one podium;
- one central tower with setbacks;
- one bay system, one window recipe, one door recipe;
- seeded variation;
- L0 and L2.

Parameters to vary:
- seed;
- floor height;
- podium tiers and width;
- central tower footprint and floors;
- setback rhythm;
- bay width;
- window proportion;
- facade density;
- symmetry.

In the cloud, "immediately see a different but coherent building" means a contact sheet or sweep sheet in the pull
request. With the optional local add-on (Phase 4), it means live in your Blender.

**Interiors (later):** generated only where the camera needs them (rooms, halls, corridors, partitions, furniture
zones, circulation, lighting, services). The window is the shared interface:

```
Inside building 3 → looking through window → distinctive building 2 → cut to exterior of building 2
```

## 20. Testing and review

### Automated (every push, in CI)

- **Resolver unit tests:** rules, constraints and IDs.
- **Determinism:** same spec gives identical output.
- **Seed locality:** changing one parameter only changes its subtree.
- **Schema validation and defaults.**
- **Budgets per representation level.**
- **Structural metrics.** Targets are initial and will be tuned:

| Metric | Definition | Initial target |
|---|---|---|
| Dominance | Central tower height ÷ tallest secondary tower | ≥ 1.3 |
| Containment | Each secondary tower stands on the podium or connects to it | 100% |
| Connection validity | Bridges join two masses, both ends on the same floor, span within limit | 100% |
| Symmetry | Mismatched mirrored elements when symmetry is bilateral | 0 |
| Setback rhythm | Footprint never grows with height; setbacks at the spec's floors | Pass |
| Termination | Every tower ends in a crown or termination element | 100% |
| Floor alignment | Elements sit on floor boundaries | 100% |
| Cornices | Every mass has one cornice, following its outline, in its top floor | 100% |
| Tiled | Every facade's layer tree has leaves that tile it exactly once (docs/LAYERS.md) | 100% |
| Banded | Sky lobbies on the building's band rhythm; no run longer than a lobby could break | Pass |
| Programmed | Every leaf graded luxury or functional, portals luxury; luxury 10-50% of the facade, ranked by standing, mirrored when bilateral | Pass |
| Ornament hierarchy | No standing carries an ornament system more richly than the standing above it | Pass |
| Style envelope | Slenderness, taper, podium share, spire share and ornament within the bounds in section 11 | Pass |

### Visual (judged by you, from the pull request)

- **Contact sheets:** a grid of N seeds.
- **Sweep sheets:** one parameter varied across a row; this is how exploring parameters works while we're
  cloud-only.
- **Distance sheets:** one building at L0 to L3.
- **Golden seeds:** a fixed set rendered on every pull request, shown before and after when they change.

### Pull request evidence

- What changed.
- The check result.
- The metrics diff.
- A contact sheet.

For bandwidth, sheets stay around 500 KB (compressed JPEG). Full-resolution renders go only into CI artifacts.

### Questions for human review

- **Architectural:**
  - Does it read as one object?
  - Is the central tower dominant?
  - Do the secondary towers belong?
  - Are the connections believable?
  - Does scale transition logically?
  - Does ornament reinforce hierarchy?
  - Is there enough negative space?
  - Does the silhouette work?
  - Does it terminate convincingly?
- **Style:**
  - Is it still Art Deco?
  - Is there Gothic or fantasy drift?
  - Does variation preserve the style?
  - Is decoration becoming noise?
  - Are the period ideals still present?
- **Procedural:**
  - Do the same rules give substantially different buildings?
  - Does a seed reproduce a building?
  - Can one parameter change without breaking the whole?
  - Do all representations come from one description?

## 21. Decision gates

- **Gate 1: is Blender enough as the builder?** (End of Phase 2 or 3.)
  - If recipes stay comfortable in Python and Geometry Nodes: continue.
  - If geometry construction becomes the bottleneck: evaluate Houdini as the builder.
  - The resolver is unaffected either way.
- **Gate 2: is a local interactive tool needed?** (Phase 4.)
  - If sweep sheets are enough: no UI work.
  - Otherwise: build the local Blender add-on panel first.
  - Prototype a Godot editor only if the Blender interface itself is the bottleneck.
  - **Decision (Phase 4):** sweep sheets are enough for now; no add-on. Revisit if exploring parameters by pull
    request becomes the bottleneck.
- **Gate 3: ready for Unreal?** (After Phase 6.)
  - Entry criteria: handover package v1 stable, a district assembled in Blender, and bandwidth available on your side.
- **Gate 4: Houdini?** (Any time.)
  - If the grammar strains Python or Blender, or Houdini Engine offers a clearly better route into Unreal.

## 22. Technical stack

| Component | Role |
|---|---|
| Spec (JSON, versioned schema) | Source of truth |
| Resolver (Python, no Blender dependency) | Architectural grammar |
| Blender (`bpy`, headless in the cloud) | Element builder, stand-in assembler, review renderer |
| Geometry Nodes (generated from code) | Repetition-heavy element recipes where it pays |
| Blender add-on (optional, local) | Interactive parameter editing |
| Unreal Engine | World, streaming, cameras, final rendering (Phase 7) |
| Houdini | Alternative builder/assembler (Gate 4) |
| Godot | Possible future spec editor (Gate 2) |
| GitHub Actions | Checks, metrics and contact sheets on every push |

## 23. Core principle

The project should resist becoming a procedural modelling library. The real product is the architectural grammar.

```
small vocabulary → architectural grammar → architectural description → procedural construction
→ many buildings → many representations → enormous world
```

The most important early experiment is not "can we generate a building?" It is:

> Can a very small set of architectural rules produce buildings that feel deliberately designed rather than
> randomly assembled?

If that works, the rest of the pipeline becomes an engineering problem rather than an attempt to hand-author an
impossibly large city.

---

## Appendix A: Environment findings (2026-10-07)

- **Blender:** `bpy` 5.2.2 from PyPI runs headless in the cloud container (download.blender.org is blocked). Cycles
  on the CPU renders previews in seconds. EEVEE needs a GPU and kills the process.
- **Geometry Nodes:** a node tree built entirely from Python evaluates headless (1,200 instanced boxes in 18 ms).
- **USD export:** dropped Geometry Nodes instances entirely (empty scene). 1,200 objects sharing one mesh were
  written as 1,200 separate meshes, even with instancing enabled.
- **glTF export:** shared one mesh across 1,200 nodes but didn't emit GPU instancing, and skipped Geometry Nodes
  instances.
- **Conclusion:** instancing is carried by the placement manifest (section 6.3), not by exporters.
- **Godot:** 4.7.2 works when built from source (about 22 minutes, because Godot downloads are blocked). Headless
  import, GDScript tests and software-rendered screenshots all worked.
- **Not available in the cloud:** Unreal and Houdini (no GPU; account downloads and licences required).
