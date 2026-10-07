# Scale layers and contrast: design note

**Status:** proposal for review (2026-10-07). This step comes after Phase 4 and before Phase 5 (representation
levels), which it sets up.

## 1. The problem

The buildings work as massing: the silhouettes hold up more often than not, and the podium, towers and composition
do their job. But they are boring, because everything below the massing happens at one scale. Every facade, whether
a 500 m podium face or a 30 m pavilion, is the same 6 m x 4 m cell (one bay by one floor) repeated edge to edge.
Pilasters, zones and ornament vary that texture but never break it; only the entrance and doors interrupt it. There
is texture everywhere and no events: nothing big against small, plain against busy, or solid against open.

Phase 3 filled the middle scale, but at a fixed scale. This step asks "what if?" of several scales at once, with
some regions skipping layers so the building has contrast. It comes before any design language for particular
places ("a huge dining room on a balcony"), so that those places have layer targets to claim.

## 2. What the mood board shows

Nine reference images (not in the repo): an aerial massing diagram of an arcology beside Central Park, two diffusion
renders of the same scene, five front elevations of a three-tower arcology on a pyramid (the upper half of a diamond
whose lower half is buried foundations), and a close-up of a giant window on a tower. They are diffusion images: they
struggle with scale and consistency and drift towards Gothic in places, so they set mood and direction, not detail.

- **Scale.** The diagram puts the footprint at roughly 2 km, four times ours. The elevations are drawn chunky so they
  read: at true scale, what looks like a window is a ten-storey hall and what looks like a rib is a building-sized
  wall. Readable features in the images therefore map to our coarse layers, and each must subdivide again inside.
- **Mass.** A tall pyramid (a third of the height or more, in many shallow tiers or a smooth slope), not our flat
  plinth; towers as bundles of vertical shafts rising past each other, which is what makes the silhouette.
- **Treatment of each face is the variety.** The five elevations share one silhouette and differ in how the pyramid
  faces are treated: plain planes with a rich axial spine; fine terracing crossed by a few huge diagonal ribs with
  dark voids between; horizontal tiers of varying height, some glazed ribbons and some blank stone, against a
  vertical spine; a stone frame of a few giant panels, some glazed onto lit atria; green terraces, ramps and round
  cantilevered platforms over a ground-level arcade.
- **The middle frequencies are filled.** We have setbacks (very coarse) and floors and bays (very fine) and a gap
  between. They add bands of several floors, frames of a few big panels, rib systems and tier rhythms.
- **Depth varies across one surface.** A glazed panel beside a solid one, a ribbon tier beside a blank one: some
  regions stop subdividing early while their neighbours go down to the cell. That is what reads as designed.
- **Density follows composition.** Densest on the axis, at the base and at joins; calm in the flanks and fields.
- **Diagonals** (hips, nested triangles, ribs, ramps) add a third direction, aligned to the pyramid.
- **Junctions and edges are places:** the flared skirt where a tower meets the pyramid, stepped hips, pavilions at
  tier corners, platforms ringing towers at set heights.
- **Opposite axes per mass:** a horizontal or plain base under vertically fluted towers.
- **Value contrast at large scale:** stone, dark glass, gold, blue, warm interior light, green.
- **The close-up** shows one giant opening (its own coarse mullion grid, ignoring the floor grid, edges still on it)
  in a stepped, chamfered frame; ornament at the frame and sill, not in the glass; a pier beside it that is a
  building in its own right (slot windows, fins); a colossal relief figure set in the pier; deep layering and shadow;
  a garden atrium visible inside.
- **Watch-outs:** pointed arches, tracery and needle spires are Gothic or sci-fi drift. The Deco equivalents are
  stepped, chamfered or parabolic arches and stepped finials; figures are few and on the axis.

Three principles follow:

1. **A self-similar vocabulary.** The same few Deco moves at every scale: stepped frame, pier, opening with its own
   grid, chevron, fluting. One recipe applied at three or four layers gives scale contrast without new assets.
2. **Every coarse element is a container.** A giant pier holds its own small windows; a giant opening holds a coarse
   grid and a space behind it. Where each region stops subdividing is the main control over contrast.
3. **Big openings need something behind them.** A glazed hall that reveals nothing reads as a hole, so skipping the
   window layer creates an interior space: the direct link between facade layers and program.

## 3. The layers

Scale layers are named, not numbered, because L0 to L3 already mean representation levels.

| Layer | Typical size (current / target scale) | What it is | Today |
|---|---|---|---|
| Building | 0.5 / 2 km | The whole composition and its axis | Exists |
| Mass | 100-600 m / up to 2 km | Podium tiers, tower sections | Exists |
| Shaft | 20-60 m / 40-150 m wide | A vertical sub-mass of a tower; towers become bundles | Missing (silhouette) |
| Face | One edge of a mass's outline | A facade | Exists (`_Face`) |
| Band | 3-15 floors | A horizontal slice of a face: base, shaft runs, transfer, sky lobby, capital | Three fixed zones |
| Panel | 2-8 bays | A vertical slice of a band, between major piers | Implicit in the pilaster rhythm |
| Cell | 1 bay x 1 floor | A window and its piers | Every window |
| Detail | Under 1 m | Mullions, chevrons, flutes, joints | Inside recipes |

At target scale a face has hundreds of bays and hundreds of floors, which is millions of cells. Cells can only be
generated near the camera, which is a Phase 5 problem and the strongest reason to make the hierarchy explicit first.

## 4. The layer tree

Each face is subdivided top-down into a tree of rectangles on the face's grid (bays x floors). Every node either
**subdivides** into the next layer or **terminates** with a treatment that covers the whole node. Terminating early is
skipping layers.

The split order follows the face's dominant axis: a vertical face splits into panels (columns) first, then bands, so
a column can run the full height (an axial spine, a giant order); a horizontal face splits into bands first, so a tier
can run the full width (a ribbon, a blank course).

```
tower.central/section.0/facade.south: 26 bays, floors 20-62, vertical axis (columns first)
├── panel.000  bays 0-6     band.020  floors 20-50  cells
│                           band.050  floors 50-52  sky lobby: giant order
│                           band.052  floors 52-62  cells, capital at the top
├── panel.006  bays 6-10    as panel.000
├── panel.010  bays 10-16   AXIS
│                           band.020  floors 20-21  portal (door)
│                           band.021  floors 21-33  opening, 12 floors, space behind
│                           band.033  floors 33-50  cells, rich
│                           band.050  floors 50-62  field with a relief slot
├── panel.016  bays 16-20   mirror of panel.006
└── panel.020  bays 20-26   mirror of panel.000
```

### Treatments

A node terminates with one of a small vocabulary; the first two exist today:

| Treatment | Terminates at | What it is | Contains |
|---|---|---|---|
| Cells | Cell | The window grid with piers, by zone (base, shaft, capital) | Windows |
| Portal | Band or panel | The entrance and doors, as now, in a stepped frame | Doors |
| Field | Band or panel | Plain stone, with joints and optionally a relief or figure slot | Optional asset slot |
| Opening | Band or panel | One glazed opening in a stepped, chamfered frame, with its own coarse mullion grid and an ornamented sill band | A space behind |
| Recess | Band or panel | The envelope pushed back by several metres: a loggia or terrace with a floor slab and balustrade | A back wall (which subdivides again) and a space |
| Projection | Band or panel | A volume standing forward: a balcony slab, a platform, an oriel | Optional space |
| Giant order | Band | Piers spanning the whole band every few bays, deep glazing between | Cells, set deep |
| Rich | Panel | Cells with ornament raised a level (more chevrons, fluting, a relief band) | Windows |

Self-similar recipes: the stepped frame, opening grid, pier and chevron are parametrised by size, so the same recipe
serves a door, a ten-storey opening and a 200 m frame on the pyramid face. Containers recurse: a recess's back wall
and a giant order's infill are nodes that subdivide again.

### Interior spaces

An opening or recess creates a `space` element behind it: a volume with a `program` tag (hall, atrium, terrace,
dining room), the reserved tag from the plan. For now it is a stand-in shell (floor slabs every few floors, a back
wall, warm light) so a big opening never reads as a hole; real interiors come later. A recess needs the core to step
back behind it, so the core becomes a cut outline rather than one box.

## 5. Where the exceptions go

Exceptions are placed by composition, never at random positions, so they read as designed:

- **Zones on every face:** axis (the central column, which the pilaster rhythm already defines), flanks, edges (the
  end columns by the corners), base (the bottom band), top (the band under a setback or cornice), and junctions
  (the transfer floor, where a tower stands on a terrace, where a bridge lands).
- **Priority:** axis, then base, then top and junctions, then flanks. Density falls from the axis outwards.
- **The seed chooses the treatment, composition chooses the place.** Each zone has a short list of allowed
  treatments; the node's seed picks one.
- **Symmetry:** mirrored nodes (and mirrored faces, east and west) share their decisions, as twins already do.
- **Hierarchy:** bigger and richer events on the central tower, fewer on pavilions, as ornament does now.
- **A `contrast` style setting** (0 to 1) sets how many zones get exceptions and how coarse they go.
- **Variable band heights:** long shafts break every 8 to 15 floors into runs, with occasional double-height
  sky-lobby bands; tiers vary in height. This alone adds the missing middle frequency.

## 6. Targets

Every node has a stable id, built from its position the way ids are now (bands by first floor, panels by first bay,
so they survive changes elsewhere):

```
arcology/tower.central/section.0/facade.south/panel.010/band.021
```

Seeds derive from the id as usual. Window copies keep their facade-wide ids (`.../facade.south/bay.012/floor.040`),
so window identity survives re-splitting; windows inside an opening simply don't exist.

Each node records: layer, rectangle (bays, floors), size in metres, height above ground, facing, zone, standing
(central, sister, podium, pavilion), and its neighbours (a setback or terrace above, a bridge, a view). The plan gains
a `regions` list holding the tree (geometry stays in `elements`); builders ignore it, while checks, reviews and later
rules read it.

Later design language claims targets by query. "A huge dining room on a balcony" becomes: a band-layer node on the
axis or top zone, high up, under a setback or facing a terrace, on the central tower; terminate it as a recess with a
projecting slab, and tag its space `program: dining`. Other target types the images ask for:

- **Rings:** band levels on towers that carry platforms (and later `provision: private_landing`).
- **Junctions:** where masses meet (a flared skirt, a transfer gallery).
- **Edges:** hips and corners (stepped terraces, corner pavilions).
- **Asset slots:** figure and relief recesses in fields and piers, on the axis (empty until assets exist).

## 7. How it sets up Phase 5

Each representation level becomes "draw the tree down to layer X":

| Level | Drawn |
|---|---|
| L3 | Masses and crowns |
| L2 | Terminal nodes at band and panel layers as stand-ins (fields as stone, openings as lit glass, recesses as shadow, giant piers); cells as channels, as now |
| L1 | Plus cells, simplified |
| L0 | Everything, generated near the camera at target scale |

The current L2 window channels are a crude version of this.

## 8. Checks

- **Covered:** every face is tiled exactly once by terminal nodes (generalises `facade_complete`).
- **Contrast:** at least two layers above the cell are expressed in each building, and exceptions take between
  roughly 5% and 35% of the facade area (bounds tuned by eye): neither uniform nor noise.
- **Composed:** exceptions only in their allowed zones, and the axis is each main face's richest zone.
- **Housed:** every opening and recess has a space behind it.
- **Symmetric and clear:** the existing checks, with projections added to clearance.

## 9. Review evidence

- **Elevation sheet (new, no Blender):** flat elevations of each building's main faces drawn with Pillow straight
  from the plan, regions coloured by treatment and outlined by layer. Cheap, deterministic and readable at a glance:
  it shows the contrast structure without judging rendered detail. It also shows today's uniform state as the
  baseline.
- **What-if sheet:** the same seeds with each treatment switched on alone, then combined, and the `contrast` setting
  swept; rendered at L2.
- **Mid-range view:** a new detail camera on one whole section face (150 to 300 m wide), where bands and panels read.

## 10. Steps

Each step is pushed with its sheets:

1. **The tree, no visual change.** Make the layers explicit in `facade.py`, add `Plan.regions` and the elevation
   sheet. The golden seeds' geometry stays identical.
2. **Zones and band rhythm.** Composition zones on every face; variable band heights, shaft runs and sky lobbies.
3. **Treatments.** Field, opening (with its space), recess (with its slab and space), giant order, rich; the stepped
   frame and opening grid made self-similar; the `contrast` setting; then the checks, the what-if sheet and the
   mid-range view. You pick what works.
4. **Then:** tower shafts (silhouette), the pyramid podium, the move to target scale, and Phase 5.

## 11. Not in this step

Real interiors (stand-in shells only), figures and reliefs (empty slots only), the consequence system, scaling up to
2 km, the shaft layer and the pyramid. All of them build on the tree.

## 12. Open questions

1. **Target scale:** roughly a 2 km footprint and a 1.5 to 2.5 km height, or something else?
2. **The pyramid:** a smooth slope (images 4 and 7) as well as stepped tiers (images 5, 6 and 8)? A smooth face needs
   sloped geometry; many small steps approximate it and also cover terracing.
3. **Placement:** exceptions strictly by composition (very Deco), or also a small budget of free placements for
   surprise?
4. **Figures:** empty asset slots in this step, or later?
5. **Palette:** add the blue accent (lapis or teal) now?
