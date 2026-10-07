# Scale layers and contrast: design note

**Status:** steps 1 (the tree) and 2 (courses and the programme split) built (2026-10-07); step 3 (treatments)
next. This step comes after Phase 4 and before Phase 5 (representation levels), which it sets up.

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

Target scale (section 12): a 2 km x 2 km base, 2 km high, with a pyramid rising about 1 km at roughly 45 degrees to
a peak buried in a fat central tower. At that scale a face has hundreds of bays and hundreds of floors, which is
millions of cells. Cells can only be
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
├── panel.000  bays 0-6     band.000  floors 20-50  cells
│                           band.030  floors 50-52  sky lobby: giant order
│                           band.032  floors 52-62  cells, capital at the top
├── panel.006  bays 6-10    as panel.000
├── panel.010  bays 10-16   AXIS
│                           band.000  floors 20-21  portal (door)
│                           band.001  floors 21-33  opening, 12 floors, space behind
│                           band.013  floors 33-50  cells, rich
│                           band.030  floors 50-62  field with a relief slot
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

Two mechanisms with different jobs (decided, section 12): **composition** makes the contrast and is regular, the
same logic on every building; **free placement** sets a building's tone and is occasional.

### Composition: courses and the programme split

- **Courses.** Every face splits into the same vertical structure: the base (the ground tier's, matching the
  entrance), a foot floor facing the terrace a mass stands on, runs of shaft, sky lobbies, seams where bridges cross
  (the transfer course on the central and sister towers, from the band under the bridges to their top; a landing on
  each pavilion and the wall it bridges into), and the capital under a terrace or crown.
- **Band rhythm.** Shafts break into runs (`facade.band_run`, 8 to 15 floors) between sky lobbies
  (`facade.lobby_floors`, 1 or 2), on one rhythm counted from the transfer floor (or the central tower's foot), so
  lobbies line up across the towers. A lobby needs four floors of run either side. With varied repetition each
  tower group draws its own run. This alone adds the missing middle frequency.
- **Columns.** Each panel is the axis (centred on the face), an edge (by a corner), a flank (between), or the full
  width (a band across a horizontal face).
- **Grades.** Every leaf is luxury or functional (its `grade`). A building draws its luxury share
  (`program.luxury`, 15% to 35%), and each mass's standing scales it as it scales ornament: more on the central
  tower, less on pavilions, closer together as the hierarchy weakens.
- **Places.** Composition ranks every leaf by its column (axis, then edge, then flank) and its course (base, then
  capital and transfer, then the other seams, then runs). Portals are always luxury; then the highest-ranked leaves
  take the luxury, higher floors first, then nearer the axis, then the front face first, up to the mass's share.
  Leaves ranked alike are graded together, so mirror images, and east and west faces, always match.
- **Seams** are the courses where masses or runs meet: foot, lobby, transfer, landing and capital. They, and the
  lines where luxury meets functional, take the seam treatments (deep bands, cornices, recessed loggias), so a
  boundary reads as a line rather than a change of colour.
- **Exceptions go to luxury.** Treatments (section 4) land in luxury leaves and on seams; functional leaves stay
  calm cells, the ground the contrast reads against, plain on purpose. The seed chooses the treatment, composition
  the place.
- **A `contrast` style setting** (0 to 1) sets how many luxury leaves take exceptions and how coarse they go.

### Free placement: a building's tone

- **Any layer can host one, sparingly.** Each building tries the layers largest first; a hit lowers every other
  layer's odds (to about 0.3 of what they were), so most buildings have one tone layer or none. The seed decides,
  the plan records it, and a sweep can force it.
- **Small layers** (detail, cell, panel, band) hit more often and are subtle: one giant window in a field of small
  ones, a band twice as tall as the rest, a panel that skips a level of the tree.
- **Large layers** (shaft, mass, building) hit in 15% to 20% of buildings and change the silhouette: colossal
  figures as pillars carrying a whole tower; a figure standing in one tower and leaning across to the next; an
  oversized doorway into a cavernous atrium that distorts the pyramid. Silhouette work favours them.
- **Budgets** cap each layer's count. Where a free placement overlaps composition, it wins locally (the atrium
  removes the cells it cuts through).
- **Symmetry.** On bilateral buildings small free placements mirror, since a lone odd window reads as a mistake;
  large gestures may break symmetry, since a figure leaning between two towers is one-sided by nature.
- **Checks.** The style envelope still holds, except where a large gesture carries an explicit allowance (a leaning
  figure isn't "tapered"); the batch report gives the share of buildings with a large gesture.

## 6. Targets

Every node has a stable id, built from its position the way ids are now (panels by first bay, bands by first floor
counted from the mass's foot, so they survive changes elsewhere, such as a taller podium below):

```
arcology/tower.central/section.0/facade.south/panel.010/band.001
```

Seeds derive from the id as usual. Window copies keep their facade-wide ids (`.../facade.south/bay.012/floor.040`),
so window identity survives re-splitting; windows inside an opening simply don't exist.

Each node records its layer, rectangle (bays, floors), size in metres and height above ground. A face also records
its facing, standing (central, sister, podium, pavilion), luxury share and band rhythm; a panel its column; a band
its course; a leaf its column, course, role and grade. The plan holds the trees in `regions` (geometry stays in
`elements`); builders ignore it, while checks, reviews and later rules read it. Still to come: neighbours (a
terrace above, a bridge, a view).

Later design language claims targets by query. "A huge dining room on a balcony" becomes: a luxury band-layer leaf on
a seam, high up (a capital under a terrace, or a foot facing one), on the central tower; terminate it as a recess
with a projecting slab, and tag its space `program: dining` (the plan's reserved tag). Other target types the images
ask for:

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

- **Covered:** every face is tiled exactly once by terminal nodes (generalises `facade_complete`). Built: `tiled`.
- **Banded:** lobbies keep the building's rhythm, and no run is longer than a lobby could break. Built: `banded`.
- **Programmed:** every leaf graded, every portal luxury, the building's luxury share between 10% and 50%, no
  standing more luxurious than the one above it (within 0.03, as leaves come whole), and the grading mirror
  symmetric on bilateral styles. Built: `programmed`.
- **Contrast:** at least two layers above the cell are expressed in each building, and exceptions take between
  roughly 5% and 35% of the facade area (bounds tuned by eye): neither uniform nor noise.
- **Composed:** exceptions only in their allowed zones, and the axis is each main face's richest zone.
- **Housed:** every opening and recess has a space behind it.
- **Symmetric and clear:** the existing checks, with projections added to clearance.

## 9. Review evidence

- **Elevation sheet (built, no Blender):** flat south elevations of each building drawn with Pillow straight from
  the plan, leaves coloured by role (shaft, lobby, base, capital, portal), strong where luxury and pale where
  functional, and outlined by layer; the caption gives the luxury share and each role's. Cheap, deterministic and
  readable at a glance: it shows the contrast structure without judging rendered detail.
- **What-if sheet:** the same seeds with each treatment switched on alone, then combined, and the `contrast` setting
  swept; rendered at L2.
- **Mid-range view:** a new detail camera on one whole section face (150 to 300 m wide), where bands and panels read.

## 10. Steps

Each step is pushed with its sheets:

1. **The tree, no visual change.** Make the layers explicit in `facade.py`, add `Plan.regions` and the elevation
   sheet. The golden seeds' geometry stays identical.

   *Built.* Faces split into panels at pilaster lines and portal edges and into bands at zone boundaries (columns
   first; bands first on horizontal faces). Leaves are `cells` (role base, shaft or capital) or `portal`, and
   generate their elements; cells leaves side by side on the same floors share one window array, so the plan stays
   compact (676 elements for the default building, against 700 before; the tree adds about 2,500 regions). Piers
   stand on every bay line except where a leaf that isn't cells spans it. Every placed copy is identical to
   before on 48 plans (golden seeds and four more, default, horizontal and varied styles), except that L2 channels
   beside doors on horizontal faces split in two at the door's top, covering the same floors. A `tiled` check
   proves the leaves tile every face once; `arcology elevations` draws the trees with no Blender. The baseline it
   shows: 82-85% of every building's facade is shaft cells.
2. **Courses, zones and the programme split.** Courses with the band rhythm, columns, and every leaf graded luxury
   or functional by composition (section 5).

   *Built.* Faces split at course boundaries: base, foot, runs, sky lobbies, the transfer course and pavilion
   landings, capital. Sky lobbies (and the transfer course) take base windows, so at every distance they read as
   masonry belts across the glazed shaft, lined up across the towers on the transfer floor's rhythm; on horizontal
   faces they break the ribbons. Leaves carry `column`, `course` and `grade`; faces their luxury share and rhythm.
   Over 100 seeds the luxury share runs 16% to 37% of the facade (central tower 20% to 46%, pavilions 10% to 25%),
   and every style setting passes `banded` and `programmed`. The elevation sheet shows the result: an axis spine,
   capitals and lobby belts in luxury against a pale functional field. The default building has 1,124 elements
   (676 before) and 3,680 regions. The grades change no geometry yet.
3. **Treatments.** Field, opening (with its space), recess (with its slab and space), giant order, rich, placed in
   luxury leaves and on seams; the stepped frame and opening grid made self-similar; the `contrast` setting; empty
   figure slots (`asset_slot`) on the axis; small-layer free placements with the tone rule; then the checks, the
   what-if sheet and the mid-range view. You pick what works.
4. **Then:** tower shafts (silhouette), the pyramid (smooth and stepped), the move to target scale, large-layer
   free placements (they need shafts to carry and a pyramid to distort), and Phase 5.

## 11. Not in this step

Real interiors (stand-in shells only), figures and reliefs (empty slots only), the consequence system, scaling up to
2 km, the shaft layer, the pyramid and large-layer free placements. All of them build on the tree.

## 12. Decisions (2026-10-07)

1. **Target scale:** a square base 2 km x 2 km and an overall height of 2 km. The pyramid rises about 1 km to its
   peak (so its faces slope at roughly 45 degrees), but the peak is buried inside the central tower, which emerges
   from the pyramid and carries the height on. The central tower stays fat, as in today's contact sheets (a fifth or
   so of the base width); keep that proportion through the scale-up.
2. **The pyramid:** both smooth and stepped, and they can change on one building. The steps set the rhythm: flat
   terraces at the steps, with smooth sloped runs or stepped tiers between them.
3. **Placement:** two mechanisms (section 5). Composition is regular and driven by the programme: each building is
   divided into luxury and functional by a share, and the luxury areas and seams set the tone against the functional
   areas where this work isn't. Free placement sets a building's tone in particular layers: every layer can have it,
   each sparingly, and a layer having it lowers the others' likelihood; the very large layers make dramatic shapes
   on a smaller share of buildings, 15% to 20% (figures as pillars to entire towers, dancing figures spanning a
   leaning shape between towers, oversized doorways into cavernous atriums that distort the pyramid). Agreed
   defaults: a luxury share of 15% to 35% of the facade, more on the central tower; small free placements mirror on
   bilateral buildings, large gestures may break symmetry.
4. **Figures:** yes, empty asset slots now (`kind: "asset_slot"`, as section 9 of the plan reserves). Filling them
   will be generative too, later.
5. **Palette:** stones, concretes and metals only. Accents yes (contrasting stones and metals, such as bronze, gilt,
   nickel or dark granite), but not blue.
