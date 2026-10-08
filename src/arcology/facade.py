"""Facade grammar: dresses each mass, edge by edge round its outline. Plain Python.

Phase 1 laid the grid: a core behind the facade, an L-shaped piece at each corner (a
re-entrant piece at notched corners), a stone pier on every bay line and a glazed channel in
every bay of every floor. Phase 3 fills the middle scale, largest first:

- Pilasters: every k-th bay line (`facade.pilaster_every`) carries a full-depth pier, set
  out symmetrically from the facade's centre; the piers between stand back. On a
  horizontal dominant axis (Phase 4) there are none: piers stand back to the glass line and
  stone spandrel bands run unbroken across them instead.
- Zones: the top floors of every mass are its capital (stone panels, shorter glass, a
  stepped head), the ground tier's bottom floors are the base (stone jambs narrowing the
  glass), and the shaft between keeps the glazed channels. At L2, where windows drop out,
  one channel per bay column of each block keeps the zones legible (glass or stone).
- A stepped cornice runs round the top of every mass.
- Portals: the main entrance on the podium's south face, and a door at the foot of each
  tower's outer faces, both taken out of the window grid.
- Ornament: bronze chevrons on capital panels, fluted pilasters, stepped merlons over the
  parapets at pilaster lines. Its density rho is the style's ornament_density scaled by the
  mass's standing (central tower, sister towers, podium, pavilions), and each system
  switches on above a threshold, so ornament gathers where the hierarchy peaks.

Every face is a layer tree (docs/LAYERS.md): the face splits into panels (columns of bays,
at pilaster lines and portal edges) and bands (runs of floors, at course boundaries), columns
first on a vertical face and bands first on a horizontal one. Each leaf has a treatment and
generates the elements that fill it: "cells" (windows, and channels at L2; leaves side by
side on the same floors share one array) or "portal".
Piers stand on every bay line except where a leaf that isn't cells spans it.

Courses (Phase 4b step 2) give every mass the same vertical structure: base, a foot floor on
the terrace it stands on, runs of shaft broken by sky lobbies on one building-wide rhythm
(anchored at the transfer floor, so lobbies line up across the towers), seams where bridges
cross, and the capital. Sky lobbies and the transfer course take base windows, a belt of
masonry across the glass. Composition then grades every leaf luxury or functional: portals
first, then by column (axis, edge, flank) and course (base, capital and seams before runs),
up to the mass's share of the building's luxury, so later treatments know where to go.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, replace

from arcology.compose import PARAPET_HEIGHT
from arcology.plan import Element, Region
from arcology.rules import (
    DETAIL,
    DISTANT,
    HIERARCHY,
    ROOT,
    STRUCTURE,
    Edge,
    ResolveError,
    box_extent,
    outline,
    ring_params,
    rnd,
    sample,
    standing,
)
from arcology.seeds import derive_seed, path_seed, rng
from arcology.spec import Spec

GLASS = 0.05  # glazing thickness
MULLION_DEPTH = 0.06  # mullions and transoms stand this far in front of the glass
MINOR_SETBACK = 0.2  # piers between pilasters stand back this far from the envelope
BAND_FRONT = 0.15  # horizontal axis: spandrel bands stand this far behind the envelope
FLUTES, REED = 3, 0.08  # a fluted pilaster's flutes, and how deep its reeds stand
CAPITAL_SHARE = 0.06  # capital floors per floor of the mass, at rho = 0.5
CAPITAL_SILL = 0.6  # share of a capital floor that is stone panel below the glass
BASE_SILL, BASE_JAMB = 0.15, 0.22  # base windows: low sill; jambs as a share of the bay
HEAD, CORBEL = 0.6, 0.3  # stone head over capital and base glass; corbels under it
CHEVRON_BAND, CHEVRON_RELIEF = 0.22, 0.08
RICH_SILL = 1.4  # a rich window's spandrel is at least this tall, to carry its chevrons
CORNICE_REACH, CORNICE_RISE = 0.3, 0.35  # per step of a cornice
# Merlons: pylons continuing pilasters above the roof, stepping in over the parapet; width as
# a share of the pier's, standing slightly proud so no face lies in the parapet's.
MERLON_STEPS, MERLON_RISE, MERLON_WIDTH, MERLON_PROUD = 3, 1.0, 2.0, 0.15

# Ornament density by standing, as a share of style.ornament_density, and the density each
# system needs.
STANDING_ORNAMENT = {"central": 1.0, "sister": 0.8, "podium": 0.7, "pavilion": 0.6}
CHEVRONS_AT, FLUTES_AT, MERLONS_AT = 0.4, 0.55, 0.6
DOUBLE_CHEVRONS_AT = 0.6

# Courses (docs/LAYERS.md section 5): every face splits into runs of floors, bottom up. The
# base and capital are the zones; a foot floor faces the terrace a mass stands on; seams mark
# where bridges cross (the transfer floor, a pavilion's landing); sky lobbies break the shaft
# into runs on one rhythm. Each course's cells take a window role.
FOOT_FLOORS = 1
MIN_RUN = 4  # shaft floors at least either side of a sky lobby
COURSE_ROLE = {
    "base": "base",
    "foot": "shaft",
    "run": "shaft",
    "lobby": "lobby",
    "transfer": "lobby",
    "bridge": "shaft",
    "capital": "capital",
}
SEAMS = ("foot", "lobby", "transfer", "bridge", "capital")  # courses where masses or runs meet

# The programme split: every leaf ranks by its column and course, and the highest ranked
# take the luxury (higher floors first, then nearer the axis) up to the mass's share, which
# its standing scales as it does ornament.
COLUMN_RANK = {"axis": 4.0, "edge": 0.5, "flank": 0.0, "full": 0.0}
COURSE_RANK = {
    "base": 3.0,
    "capital": 2.0,
    "transfer": 2.0,
    "lobby": 1.5,
    "foot": 1.5,
    "bridge": 1.5,
    "run": 0.0,
}
STANDING_LUXURY = {"central": 1.3, "sister": 1.0, "podium": 0.9, "pavilion": 0.7}
FACING_RANK = {"south": 3, "north": 2, "east": 1, "west": 1}  # the front first; notches last

# Treatments (docs/LAYERS.md sections 4 and 5): what a luxury leaf may become, by the kind of
# place (its course: runs, seams, the capital, the base) and its column. The seed picks one
# per kind of course and column on each tower, so a tower's luxury lobbies all match;
# `contrast` sets how many kinds take one, and favours cuts (openings and recesses, which
# carve a space into the core) over ornament. A pick that doesn't fit a leaf falls back
# along the list.
TREATMENTS = ("field", "opening", "recess", "giant", "rich")
CUTS = ("opening", "recess")
COLUMNS = ("axis", "flank", "edge", "full")
ALLOWED = {
    "run": {
        "axis": ("opening", "field", "rich"),
        "flank": ("giant", "rich"),
        "edge": ("rich",),
        "full": ("giant",),  # a run of plain stone across a whole face is a blank wall
    },
    "seam": {
        "axis": ("recess", "opening"),
        "flank": ("recess", "rich"),
        "edge": ("field",),
        "full": ("giant", "field"),
    },
    "capital": dict.fromkeys(COLUMNS, ("field",)),
    "base": {
        "axis": ("opening", "field"),
        "flank": ("giant", "field"),
        "edge": ("field",),
        "full": ("giant", "field"),
    },
}
OPENING_DEPTH, RECESS_DEPTH, MIN_CUT = 12.0, 6.0, 3.0  # metres into the building
RECESS_FLOORS = 3  # a recess is a loggia or terrace: at most this tall
FRAMES, FRAME_WIDTH, FRAME_STEP, SILL_STEP = 3, 0.6, 0.35, 0.45  # an opening's stepped frame
MULLION_PITCH, TRANSOM_PITCH = 3.0, 9.0  # an opening's coarse grid, metres
HALL_SLABS = 3  # floors between the slabs of the hall behind an opening
SLAB, RAIL, RAIL_HEIGHT = 0.35, 0.25, 1.1  # a recess's floor slabs and balustrades
GIANT_WIDTH, GIANT_PROUD = 2.5, 0.6  # a giant pier: width as a share of a pier's; metres proud
NICHE_WIDTH, NICHE_HEIGHT, NICHE_DEPTH = 0.5, 0.7, 0.5  # a field's slot: shares, metres
NICHE_SURROUND = 0.15  # each step of the niche's surround stands this far proud


@dataclass(frozen=True)
class PortalStyle:
    frames: int
    frame_step: float  # how far each stepped frame stands in front of the next
    plinth: float  # plinth reach in front of the outermost frame
    apron: float  # plinth reach beyond the portal on each side
    crest: float  # stepped crest above the portal
    canopy: float  # canopy reach in front of the outermost frame
    door_share: float  # canopy height as a share of the portal's
    door_cap: float  # and at most this


ENTRANCE = PortalStyle(3, 0.5, 2.0, 1.0, 2.4, 1.5, 0.5, 5.0)
DOOR = PortalStyle(2, 0.25, 0.6, 0.4, 1.2, 0.4, 0.75, 3.0)


@dataclass(frozen=True)
class Portal:
    """A portal centred at the foot of one facade, taken out of its window grid."""

    kind: str  # "entrance" or "door"
    edge: str
    bays: int | None  # None: one bay or two, whichever centres on the facade
    floors: int


@dataclass(frozen=True)
class FacadeSystem:
    """One building's facade dimensions, drawn once so every facade repeats them."""

    bay: float
    floor_height: float
    pier_width: float
    pier_depth: float
    recess: float
    density: float
    mullions: int
    pilaster_every: int
    ornament: float  # style.ornament_density
    spread: float = 1.0  # share of the ornament differences between standings kept (hierarchy)
    axis: str = "vertical"  # style.dominant_axis: continuous piers, or continuous spandrel bands
    run: int = 12  # band rhythm: floors in a shaft run between sky lobbies
    lobby: int = 1  # and in a sky lobby
    luxury: float = 0.25  # program.luxury: the building's luxury share of its facade area
    contrast: float = 0.5  # style.contrast
    treatments: tuple[str, ...] = TREATMENTS  # facade.treatments: the ones allowed

    @property
    def depth(self) -> float:
        """Envelope to core: piers stand proud by pier_depth, windows sit behind that."""
        return rnd(self.pier_depth + self.recess + GLASS)

    def window(self, zone: str, chevrons: int = 0, rich: bool = False) -> tuple[str, dict, tuple]:
        """Recipe, params and extent of a window in `zone`: a channel filling the bay
        between two piers, glazed above a spandrel (shaft) or a stone panel (capital),
        or a narrower opening between stone jambs (base). A rich shaft window carries
        bronze chevrons on its spandrel."""
        clear, fh = self.bay - self.pier_width, self.floor_height
        params = {
            "width": rnd(clear),
            "height": rnd(fh),
            "front": rnd(self.pier_depth),
            "recess": rnd(self.recess),
            "glass": GLASS,
            "mullions": self.mullions,
        }
        panel = self.pier_depth + self.recess / 2  # front of the spandrel or panel
        nearest = min(panel, self.pier_depth + self.recess - MULLION_DEPTH)
        if zone == "shaft":
            recipe = "window.deco_tall"
            params["sill"] = rnd(fh * (0.55 - 0.45 * self.density))
            spandrel = panel
            if self.axis == "horizontal":  # a stone band, standing forward, for a spandrel
                recipe = "window.deco_band"
                params["band"] = spandrel = BAND_FRONT
                nearest = BAND_FRONT
            pitch, count = 1.6 * CHEVRON_BAND, max(1, chevrons)
            if rich and self.axis == "vertical":  # room for the chevrons on a bronze panel
                params["sill"] = rnd(max(params["sill"], RICH_SILL))
            rise = 0.65 * params["sill"] - CHEVRON_BAND - (count - 1) * pitch
            if rich and rise > 0.2:
                params |= {
                    "chevrons": count,
                    "chevron_band": CHEVRON_BAND,
                    "rise": rnd(rise),
                    "relief": CHEVRON_RELIEF,
                }
                nearest = min(nearest, spandrel - CHEVRON_RELIEF)
        elif zone == "capital":
            recipe = "window.deco_capital"
            sill = fh * CAPITAL_SILL
            params |= {"sill": rnd(sill), "head": HEAD, "corbel": CORBEL}
            pitch = 1.6 * CHEVRON_BAND
            rise = 0.65 * sill - CHEVRON_BAND - (chevrons - 1) * pitch
            if chevrons and rise > 0.2:
                params |= {
                    "chevrons": chevrons,
                    "band": CHEVRON_BAND,
                    "rise": rnd(rise),
                    "relief": CHEVRON_RELIEF,
                }
                nearest = min(nearest, panel - CHEVRON_RELIEF)
        elif zone in ("base", "lobby"):  # a sky lobby is a base in the air
            recipe = "window.deco_base"
            params |= {"sill": rnd(fh * BASE_SILL), "head": HEAD, "jamb": rnd(BASE_JAMB * clear)}
        else:
            raise ValueError(f"unknown facade zone {zone!r}")
        extent = ((rnd(-clear / 2), rnd(nearest), 0.0), (rnd(clear / 2), self.depth, rnd(fh)))
        return recipe, params, extent


def _pilasters(spec: Spec, seed: int) -> int:
    """Pilaster rhythm; none on a horizontal axis, where spandrel bands run unbroken."""
    every = sample(spec.facade.pilaster_every, seed, "pilaster_every", integer=True)
    return 0 if spec.style.dominant_axis == "horizontal" else every


def facade_system(spec: Spec) -> FacadeSystem:
    fs = path_seed(spec.seed, f"{ROOT}/facade")
    f = spec.facade
    system = FacadeSystem(
        bay=f.bay_width,
        floor_height=spec.floor_height,
        pier_width=rnd(sample(f.pier_width, fs, "pier_width")),
        pier_depth=f.pier_depth,
        recess=f.window_recess,
        density=rnd(sample(f.density, fs, "density")),
        mullions=sample(f.mullions, fs, "mullions", integer=True),
        pilaster_every=_pilasters(spec, fs),
        ornament=spec.style.ornament_density,
        spread=HIERARCHY[spec.style.hierarchy].spread,
        axis=spec.style.dominant_axis,
        run=sample(f.band_run, fs, "band_run", integer=True),
        lobby=sample(f.lobby_floors, fs, "lobby_floors", integer=True),
        luxury=rnd(sample(spec.program.luxury, path_seed(spec.seed, f"{ROOT}/program"), "luxury")),
        contrast=spec.style.contrast,
        treatments=tuple(spec.facade.treatments),
    )
    if system.pier_width >= system.bay / 2:
        raise ResolveError(
            f"{ROOT}/facade: piers {system.pier_width:g} m wide leave no room in a bay"
        )
    return system


def facade_variant(spec: Spec, fac: FacadeSystem, seed: int) -> FacadeSystem:
    """A tower group's own facade, for varied repetition: density, mullions, pilaster rhythm
    and band rhythm drawn afresh within the spec's ranges; the bay, piers, depths and lobby
    height stay the building's, so the towers still share one grid."""
    fs = derive_seed(seed, "facade")
    f = spec.facade
    return replace(
        fac,
        density=rnd(sample(f.density, fs, "density")),
        mullions=sample(f.mullions, fs, "mullions", integer=True),
        pilaster_every=_pilasters(spec, fs),
        run=sample(f.band_run, fs, "band_run", integer=True),
    )


def entrance_size(spec: Spec, tier0: Element, fac: FacadeSystem) -> tuple[int, int]:
    """Main entrance size in (bays, floors), centred on the ground tier's south face."""
    eid = f"{tier0.id}/facade.south/entrance"
    es = path_seed(spec.seed, eid)
    n = round((tier0.params["width"] - 2 * tier0.params.get("notch", 0.0)) / fac.bay)
    bays = sample(spec.facade.entrance_bays, es, "bays", integer=True)
    floors = sample(spec.facade.entrance_floors, es, "floors", integer=True)
    if (n - bays) % 2:  # match the facade's parity so the portal can be centred
        bays = bays + 1 if bays + 1 <= n - 2 else bays - 1
    if not 1 <= bays <= n - 2:
        raise ResolveError(
            f"{eid}: {bays} bays won't fit with a bay either side on a {n}-bay facade"
        )
    tier_floors = round(tier0.params["height"] / fac.floor_height)
    if floors >= tier_floors:
        raise ResolveError(
            f"{eid}: {floors} floors is as tall as the {tier_floors}-floor tier it sits in"
        )
    return bays, floors


# Ornament and zones, from a mass's ornament density rho.


def ornament(m: Element, fac: FacadeSystem) -> float:
    """A mass's ornament density: the style's, less the share its standing gives up (less
    still the weaker the hierarchy)."""
    return rnd(fac.ornament * (1 - (1 - STANDING_ORNAMENT[standing(m)]) * fac.spread))


def luxury(m: Element, fac: FacadeSystem) -> float:
    """A mass's luxury share: the building's, scaled by its standing (less the weaker the
    hierarchy), so the central tower carries the most."""
    return rnd(min(1.0, fac.luxury * (1 + (STANDING_LUXURY[standing(m)] - 1) * fac.spread)))


def chevrons(rho: float) -> int:
    return 0 if rho < CHEVRONS_AT else 1 if rho < DOUBLE_CHEVRONS_AT else 2


def flutes(rho: float) -> int:
    return FLUTES if rho >= FLUTES_AT else 0


def cornice_steps(rho: float) -> int:
    return 1 + (rho >= CHEVRONS_AT) + (rho >= MERLONS_AT)


def capital_floors(floors: int, base: int, rho: float) -> int:
    """Floors in a mass's capital: a share of its height, richer with ornament, and always
    leaving a floor of shaft."""
    if floors < 3:
        return 0
    wanted = max(1, round(floors * CAPITAL_SHARE * (0.5 + rho)))
    return max(0, min(wanted, floors - base - 1))


def _stretches(floors) -> list[range]:
    """Ascending whole numbers grouped into consecutive ranges."""
    out: list[range] = []
    for f in floors:
        if out and out[-1].stop == f:
            out[-1] = range(out[-1].start, f + 1)
        else:
            out.append(range(f, f + 1))
    return out


def courses(
    floors: range,
    base: int,
    capital: int,
    *,
    foot: bool = False,
    seams=(),
    rhythm: tuple[int, int, int] | None = None,
) -> list[tuple[str, range]]:
    """A mass's courses, bottom up, tiling `floors`: the base and capital zones (`base` and
    `capital` floors), a foot floor if it stands on a terrace (`foot`), the `seams` given as
    (kind, floors) where they fall between those, and in each stretch of shaft left, sky
    lobbies on the `rhythm` (anchor floor, run, lobby): `lobby` floors at every anchor +
    j * (run + lobby), wherever MIN_RUN shaft floors stay either side. The rest are runs.
    One rhythm for every mass lines the lobbies up across the building."""
    label: dict[int, str] = dict.fromkeys(floors[:base], "base")
    label |= dict.fromkeys(floors[len(floors) - capital :], "capital")
    shaft = [f for f in floors if f not in label]
    if foot and len(shaft) > FOOT_FLOORS:
        label |= dict.fromkeys(shaft[:FOOT_FLOORS], "foot")
    for kind, seam in seams:
        label |= {f: kind for f in seam if f in floors and f not in label}
    if rhythm is not None:
        anchor, run, lobby = rhythm
        period = run + lobby
        for stretch in _stretches(f for f in floors if f not in label):
            p = anchor + math.ceil((stretch.start + MIN_RUN - anchor) / period) * period
            while p + lobby + MIN_RUN <= stretch.stop:
                label |= dict.fromkeys(range(p, p + lobby), "lobby")
                p += period
    out: list[tuple[str, range]] = []
    for f in floors:
        kind = label.get(f, "run")
        if out and out[-1][0] == kind:
            out[-1] = (kind, range(out[-1][1].start, f + 1))
        else:
            out.append((kind, range(f, f + 1)))
    return out


# Bay lines.


def pilaster_lines(n: int, k: int) -> set[int]:
    """Interior bay lines (1..n-1) of an n-bay facade that carry pilasters: every k-th,
    set out from the centre so the pattern is symmetric. The central group is k bays wide
    when n - k is even, otherwise k - 1 (so a single framed bay when k is 2)."""
    if k <= 0:
        return set()
    g = k if (n - k) % 2 == 0 else k - 1
    return {line for line in range(1, n) if (abs(2 * line - n) - g) % (2 * k) == 0}


def progressions(lines, stride: int) -> list[range]:
    """Sorted bay lines split into runs with a common stride (1 if stride < 1)."""
    stride = max(1, stride)
    runs: list[list[int]] = []
    for line in sorted(lines):
        run = next((r for r in runs if r[-1] + stride == line), None)
        if run is None:
            runs.append([line])
        else:
            run.append(line)
    return [range(r[0], r[-1] + 1, stride) for r in runs]


@dataclass(frozen=True)
class _Face:
    """One facade of one mass, along one edge of its outline: places elements in the
    facade's own frame (u along the edge from its centre, local -Y outward)."""

    mass: Element
    edge: Edge
    fac: FacadeSystem

    @property
    def length(self) -> float:
        return self.edge.length

    @property
    def bays(self) -> int:
        return round(self.length / self.fac.bay)

    @property
    def id(self) -> str:
        return f"{self.mass.id}/facade.{self.edge.name}"

    def u(self, line: float) -> float:
        """Facade coordinate (metres from the centre) of bay line `line`."""
        return -self.length / 2 + self.fac.bay * line

    def at(self, u: float, floor: int, inset: float = 0.0) -> tuple[float, float, float]:
        """World position of facade coordinate u at the base of `floor`, `inset` metres
        behind the envelope."""
        (ox, oy), (ux, uy), (nx, ny) = self.edge.mid, self.edge.direction, self.edge.normal
        mx, my, mz = self.mass.translation
        z = mz + (floor - self.mass.floor) * self.fac.floor_height
        return (rnd(mx + ox + ux * u - nx * inset), rnd(my + oy + uy * u - ny * inset), rnd(z))

    def cut(self, leaf: Region, depth: float) -> list[float]:
        """The box a cut treatment carves from the core behind `leaf`, `depth` metres deep
        from the envelope and between the faces of the piers at its edges, in the mass's
        frame: [x0, y0, z0, x1, y1, z1]."""
        (ox, oy), (ux, uy), (nx, ny) = self.edge.mid, self.edge.direction, self.edge.normal
        half = self.fac.pier_width / 2
        us = (self.u(leaf.bays[0]) + half, self.u(leaf.bays[1]) - half)
        pts = [(ox + ux * u - nx * y, oy + uy * u - ny * y) for u in us for y in (0.0, depth)]
        fh, f0 = self.fac.floor_height, self.mass.floor
        lo = (min(x for x, _ in pts), min(y for _, y in pts), (leaf.floors[0] - f0) * fh)
        hi = (max(x for x, _ in pts), max(y for _, y in pts), (leaf.floors[1] - f0) * fh)
        return [rnd(v) for v in (*lo, *hi)]

    def axis(self, name: str, start: int, count: int, stride: int = 1) -> dict:
        ux, uy = self.edge.direction
        step = (
            [0.0, 0.0, self.fac.floor_height]
            if name == "floor"
            else [rnd(ux * self.fac.bay * stride), rnd(uy * self.fac.bay * stride), 0.0]
        )
        axis = {"name": name, "start": start, "count": count, "step": step, "digits": 3}
        if stride != 1:
            axis["stride"] = stride
        return axis

    def element(
        self, name, kind, recipe, params, extent, u, floor, lod, inset=0.0, **extra
    ) -> Element:
        return Element(
            id=f"{self.id}/{name}",
            kind=kind,
            recipe=recipe,
            params=params,
            translation=self.at(u, floor, inset),
            rotation_z_deg=self.edge.rotation,
            extent=extent,
            floor=floor,
            seed=derive_seed(self.mass.seed, f"facade.{self.edge.name}/{name}"),
            lod=lod,
            tags={
                "facade": self.edge.name,
                "building": ROOT,
                "role": kind,
                "mass": self.mass.id,
                **extra.pop("tags", {}),
            },
            **extra,
        )

    def windows(
        self,
        name: str,
        bays: range,
        floors: range,
        zone: str,
        rho: float,
        regions: list[str],
        *,
        rich: bool = False,
        inset: float = 0.0,
    ):
        """A block of windows over `bays` x `floors` (a run of cells leaves side by side,
        named in `regions`), and its L2 channels; `inset` metres back for a recess."""
        if not bays or not floors:
            return []
        recipe, params, extent = self.fac.window(zone, chevrons(rho), rich)
        axes = [
            self.axis("bay", bays.start, len(bays)),
            self.axis("floor", floors.start, len(floors)),
        ]
        u = self.u(bays.start + 0.5)
        window = self.element(
            name,
            "window",
            recipe,
            params,
            extent,
            u,
            floors.start,
            DETAIL,
            inset,
            array={"prefix": self.id, "axes": axes},
            tags={"zone": zone, "regions": regions},
        )
        # At L2, one channel per bay column stands in for the block's windows, so distant
        # views keep the zones: dark glass up the shaft, stone in the base and capital.
        # On a horizontal axis the shaft's channels are banded, stone and glass floor by floor.
        fac, clear = self.fac, self.fac.bay - self.fac.pier_width
        h, front = rnd(len(floors) * fac.floor_height), rnd(fac.pier_depth + fac.recess / 2)
        recipe, cparams = "window.channel", {"material": "glass" if zone == "shaft" else "stone"}
        if "band" in params:
            front, recipe = params["band"], "window.channel_banded"
            cparams = {
                "floor_height": fac.floor_height,
                "sill": params["sill"],
                "glass": rnd(fac.pier_depth + fac.recess),
            }
        channel = self.element(
            name.replace("windows", "channels", 1),
            "channel",
            recipe,
            {"width": rnd(clear), "height": h, "front": front, "depth": fac.depth, **cparams},
            ((rnd(-clear / 2), front, 0.0), (rnd(clear / 2), fac.depth, h)),
            u,
            floors.start,
            DISTANT,
            inset,
            array={"prefix": f"{regions[0]}/channel", "axes": axes[:1]},
            tags={"zone": zone, "regions": regions},
        )
        return [window, channel]

    def piers(
        self,
        name: str,
        lines: range,
        floors: range,
        order: str,
        rho: float,
        shaft: list[range],
        *,
        prefix: str | None = None,
        inset: float = 0.0,
    ):
        """Piers on bay `lines` over `floors`: full-depth pilasters (fluted as ornament
        allows), or minor piers standing back between them. On a horizontal axis piers stand
        back and, up each stretch of `shaft` floors, give way to glass behind the spandrel
        bands they carry across, so each floor's windows read as one ribbon. A recess's
        back wall has plain piers ("back"), `inset` metres behind the envelope. Copies are
        named from `prefix` (default: the face) and their line."""
        fac = self.fac
        pw, dd = fac.pier_width, fac.depth
        from_floor = floors.start
        h = rnd(len(floors) * fac.floor_height)
        params = {"width": rnd(pw), "depth": dd, "height": h}
        recipe, front = "pier.strip", 0.0
        if order == "pilaster" and flutes(rho):
            recipe = "pier.fluted"
            params |= {"flutes": flutes(rho), "reed": REED}
        elif order == "pier" and fac.axis == "horizontal":
            front = params["front"] = fac.pier_depth
            bands = [
                [a - from_floor, b - a]
                for r in shaft
                if (a := max(r.start, from_floor)) < (b := min(r.stop, floors.stop))
            ]
            if bands:  # up the shaft: glass behind each floor's band
                recipe, front = "pier.banded", BAND_FRONT
                params |= {
                    "glass": rnd(fac.pier_depth + fac.recess),
                    "band": BAND_FRONT,
                    "floor_height": fac.floor_height,
                    "sill": rnd(fac.floor_height * (0.55 - 0.45 * fac.density)),
                    "bands": bands,
                }
        elif order == "pier" and fac.pilaster_every:
            front = params["front"] = MINOR_SETBACK
        extent = ((rnd(-pw / 2), front, 0.0), (rnd(pw / 2), dd, h))
        axes = [self.axis("pier", lines.start, len(lines), lines.step)]
        return [
            self.element(
                name,
                "pier",
                recipe,
                params,
                extent,
                self.u(lines.start),
                from_floor,
                STRUCTURE,
                inset,
                array={"prefix": prefix or self.id, "axes": axes},
                tags={"order": order},
            )
        ]

    def merlons(self, name: str, lines: range, roof: int) -> list[Element]:
        """Stepped merlons over pilaster `lines`: pylons rising from the roof through the
        parapet, stepping in above it."""
        w, dd = rnd(MERLON_WIDTH * self.fac.pier_width), self.fac.depth
        params = {
            "width": w,
            "depth": dd,
            "proud": MERLON_PROUD,
            "base": PARAPET_HEIGHT,
            "steps": MERLON_STEPS,
            "rise": MERLON_RISE,
        }
        top = rnd(PARAPET_HEIGHT + MERLON_STEPS * MERLON_RISE)
        extent = ((rnd(-w / 2), -MERLON_PROUD, 0.0), (rnd(w / 2), dd, top))
        axes = [self.axis("merlon", lines.start, len(lines), lines.step)]
        return [
            self.element(
                name,
                "merlon",
                "merlon.stepped",
                params,
                extent,
                self.u(lines.start),
                roof,
                DETAIL,
                array={"prefix": self.id, "axes": axes},
            )
        ]

    def portal(self, name: str, portal: Portal, bays: range, top: int, region: str) -> Element:
        """The entrance or a door, centred on the facade's foot over `bays`."""
        fac, f0 = self.fac, self.mass.floor
        style = ENTRANCE if portal.kind == "entrance" else DOOR
        clear = len(bays) * fac.bay - fac.pier_width
        height = portal.floors * fac.floor_height
        # The crest stays clear of the cornice at the top of the mass.
        room = (top - f0) * fac.floor_height - height - cornice_steps(1.0) * CORNICE_RISE - 0.1
        crest = rnd(max(0.0, min(style.crest, room)))
        params = {
            "width": rnd(clear),
            "height": rnd(height),
            "depth": fac.depth,
            "frames": style.frames,
            "frame_step": style.frame_step,
            "frame_width": rnd(min(0.6, clear / (4 * style.frames))),
            "door_height": rnd(min(height * style.door_share, style.door_cap)),
            "mullions": max(2, round(clear / 1.5)),
            "plinth": style.plinth,
            "apron": style.apron,
            "crest": crest,
            "canopy": style.canopy,
        }
        reach = style.frames * style.frame_step + style.plinth
        extent = (
            (rnd(-clear / 2 - style.apron), rnd(-reach), 0.0),
            (rnd(clear / 2 + style.apron), fac.depth, rnd(height + crest)),
        )
        tags = {
            "bays": [bays.start, bays.stop],
            "floors": [f0, f0 + portal.floors],
            "regions": [region],
        }
        return self.element(
            name,
            portal.kind,
            "entrance.deco_main",
            params,
            extent,
            self.u((bays.start + bays.stop) / 2),
            f0,
            DETAIL,
            tags=tags,
        )

    # Treatments: each fills its leaf between the piers at its edges.

    def _leaf(self, leaf: Region) -> tuple[float, float, float, dict]:
        """A leaf's clear width (between the faces of its edge piers), height, centre u, and
        the tags every element filling it carries."""
        (a, b), (f0, f1) = leaf.bays, leaf.floors
        tags = {"bays": [a, b], "floors": [f0, f1], "regions": [leaf.id]}
        width = rnd((b - a) * self.fac.bay - self.fac.pier_width)
        return width, rnd((f1 - f0) * self.fac.floor_height), self.u((a + b) / 2), tags

    def field(self, name: str, leaf: Region) -> list[Element]:
        """Plain stone, coursed every floor by a shallow joint; on the axis, a niche in a
        stepped surround holding an empty asset slot (a figure, or a relief in a capital)."""
        fac, dd = self.fac, self.fac.depth
        w, h, u, tags = self._leaf(leaf)
        params = {
            "width": w,
            "height": h,
            "front": BAND_FRONT,
            "depth": dd,
            "floor_height": fac.floor_height,
        }
        lo = BAND_FRONT
        out = []
        slot = leaf.tags.get("slot")
        if slot:
            nw, nh = rnd(w * NICHE_WIDTH), rnd(h * NICHE_HEIGHT)
            z0 = rnd((h - nh) / 2)
            params["niche"] = [nw, nh, z0, NICHE_DEPTH]
            lo = rnd(BAND_FRONT - 2 * NICHE_SURROUND)
            out.append(
                self.element(
                    f"{name}/slot",
                    "asset_slot",
                    f"slot.{slot}",
                    {"width": nw, "height": nh, "depth": NICHE_DEPTH},
                    (
                        (rnd(-nw / 2), BAND_FRONT, z0),
                        (rnd(nw / 2), rnd(BAND_FRONT + NICHE_DEPTH), rnd(z0 + nh)),
                    ),
                    u,
                    leaf.floors[0],
                    (),  # empty until assets exist
                    tags={**tags, "slot": slot},
                )
            )
        extent = ((rnd(-w / 2), lo, 0.0), (rnd(w / 2), dd, h))
        field = self.element(
            name, "field", "field.stone", params, extent, u, leaf.floors[0], STRUCTURE, tags=tags
        )
        return [field, *out]

    def opening(self, name: str, leaf: Region) -> list[Element]:
        """One glazed opening in a stepped frame receding into the wall, with its own coarse
        grid of mullions and transoms (ignoring the floors) over an ornamented sill, and the
        hall it lights: a space carved into the core, with a slab every few floors and a lit
        back wall."""
        fac = self.fac
        w, h, u, tags = self._leaf(leaf)
        frames = max(1, min(FRAMES, int((w - 1.5) / (2 * FRAME_WIDTH))))
        fw = rnd(min(FRAME_WIDTH, (w - 1.5) / (2 * frames))) if frames else 0.0
        glass = rnd(frames * FRAME_STEP + 0.6)
        inner_w, inner_h = w - 2 * frames * fw, h - frames * (fw + SILL_STEP)
        params = {
            "width": w,
            "height": h,
            "frames": frames,
            "frame_width": fw,
            "frame_step": FRAME_STEP,
            "sill_step": SILL_STEP,
            "glass": glass,
            "mullions": max(1, round(inner_w / MULLION_PITCH) - 1),
            "transoms": max(1, round(inner_h / TRANSOM_PITCH) - 1),
            "band": CHEVRON_RELIEF,
        }
        extent = ((rnd(-w / 2), -CHEVRON_RELIEF, 0.0), (rnd(w / 2), glass, h))
        depth = leaf.tags["depth"]
        hall = {
            "width": w,
            "height": h,
            "front": glass,
            "depth": depth,
            "floor_height": fac.floor_height,
            "every": HALL_SLABS,
        }
        f0 = leaf.floors[0]
        return [
            self.element(
                name, "opening", "opening.deco", params, extent, u, f0, STRUCTURE, tags=tags
            ),
            self.element(
                name.replace("opening", "hall"),
                "space",
                "space.hall",
                hall,
                ((rnd(-w / 2), glass, 0.0), (rnd(w / 2), depth, h)),
                u,
                f0,
                STRUCTURE,
                tags={**tags, "program": "hall"},
            ),
        ]

    def recess(self, name: str, leaf: Region) -> list[Element]:
        """A recess's slabs, one per floor with a balustrade at its front edge, and the
        terrace they make (a space with no geometry of its own); its back wall is cells,
        placed with the windows."""
        fac = self.fac
        w, h, u, tags = self._leaf(leaf)
        back = leaf.tags["depth"] - fac.depth  # the back wall's envelope
        floors = leaf.floors[1] - leaf.floors[0]
        params = {
            "width": w,
            "depth": rnd(back),
            "floors": floors,
            "floor_height": fac.floor_height,
            "slab": SLAB,
            "rail": RAIL,
            "rail_height": RAIL_HEIGHT,
        }
        top = rnd((floors - 1) * fac.floor_height + SLAB + RAIL_HEIGHT)
        f0 = leaf.floors[0]
        return [
            self.element(
                name,
                "slab",
                "recess.slab",
                params,
                ((rnd(-w / 2), 0.0, 0.0), (rnd(w / 2), rnd(back), top)),
                u,
                f0,
                STRUCTURE,
                tags=tags,
            ),
            self.element(
                name.replace("slab", "terrace"),
                "space",
                "space.terrace",
                {"width": w, "depth": rnd(back), "height": h},
                ((rnd(-w / 2), 0.0, 0.0), (rnd(w / 2), rnd(back), h)),
                u,
                f0,
                (),  # the open air of the terrace: nothing to draw
                tags={**tags, "program": "terrace"},
            ),
        ]

    def giant(self, name: str, leaf: Region) -> list[Element]:
        """A giant order: wide piers every two or three bays, standing proud of the wall in
        two steps and rising through the whole band, with deep glazing between them on a bay
        grid of bronze mullions, transoms and spandrels."""
        fac = self.fac
        w, h, u, tags = self._leaf(leaf)
        n = leaf.bays[1] - leaf.bays[0]
        lines = sorted(pilaster_lines(n, 2 if n < 5 else 3))
        params = {
            "width": w,
            "height": h,
            "depth": fac.depth,
            "floor_height": fac.floor_height,
            "piers": [rnd((line - n / 2) * fac.bay) for line in lines],
            "mullions": [
                rnd((line - n / 2) * fac.bay) for line in range(1, n) if line not in lines
            ],
            "pier_width": rnd(min(GIANT_WIDTH * fac.pier_width, fac.bay / 2)),
            "proud": GIANT_PROUD,
            "glass": GLASS,
        }
        extent = ((rnd(-w / 2), -GIANT_PROUD, 0.0), (rnd(w / 2), fac.depth, h))
        return [
            self.element(
                name,
                "giant",
                "order.giant",
                params,
                extent,
                u,
                leaf.floors[0],
                STRUCTURE,
                tags=tags,
            )
        ]


def _core_and_corners(mass: Element, fac: FacadeSystem, cuts=()) -> list[Element]:
    """The core, less any `cuts` (boxes in the mass's frame, behind openings and
    recesses), and the corner piers."""
    W, D, H = mass.params["width"], mass.params["depth"], mass.params["height"]
    notch, dd = mass.params.get("notch", 0.0), fac.depth
    core = {"width": rnd(W - 2 * dd), "depth": rnd(D - 2 * dd), "height": H}
    if notch:
        core["notch"] = notch  # an inward offset of a notched outline keeps the notch size
    if cuts:
        core["cuts"] = sorted(cuts)
    out = [
        Element(
            id=f"{mass.id}/core",
            kind="core",
            recipe="mass.notched" if notch else "mass.box",
            params=core,
            translation=mass.translation,
            extent=box_extent(W - 2 * dd, D - 2 * dd, H),
            floor=mass.floor,
            seed=derive_seed(mass.seed, "core"),
            lod=STRUCTURE,
            tags={"role": mass.tags["role"], "mass": mass.id},
        )
    ]
    arm = rnd(fac.pier_width / 2)
    mx, my, mz = mass.translation
    for edge in outline(W, D, notch):
        if edge.end_convex:  # L-shaped corner: the end half-piers of the two facades
            reach = rnd(max(arm, dd))
            recipe, extent = "pier.corner", ((-reach, 0.0, 0.0), (0.0, reach, H))
        else:  # re-entrant corner: both half-piers and the square between them
            recipe, extent = "pier.inner", ((-arm, -arm, 0.0), (dd, dd, H))
        out.append(
            Element(
                id=f"{mass.id}/corner.{edge.corner}",
                kind="pier",
                recipe=recipe,
                params={"arm": arm, "depth": dd, "height": H},
                translation=(rnd(mx + edge.b[0]), rnd(my + edge.b[1]), mz),
                rotation_z_deg=edge.rotation,  # incoming direction: local x along the edge
                extent=extent,
                floor=mass.floor,
                seed=derive_seed(mass.seed, f"corner.{edge.corner}"),
                lod=STRUCTURE,
                tags={"role": "corner", "mass": mass.id, "order": "corner"},
            )
        )
    return out


def _cornice(mass: Element, fac: FacadeSystem, rho: float) -> Element:
    """A stepped cornice in the top floor, corbelled out in steps."""
    fh = fac.floor_height
    W, D, H = mass.params["width"], mass.params["depth"], mass.params["height"]
    steps = cornice_steps(rho)
    rings = [
        [
            CORNICE_REACH * (i + 1),
            fh - CORNICE_RISE * (steps - i),
            fh - CORNICE_RISE * (steps - i - 1),
        ]
        for i in range(steps)
    ]
    r = CORNICE_REACH * steps
    x, y, z = mass.translation
    floors = round(H / fh)
    return Element(
        id=f"{mass.id}/cornice",
        kind="cornice",
        recipe="cornice.ring",
        params=ring_params(mass, rings),
        translation=(x, y, rnd(z + H - fh)),
        extent=(
            (rnd(-W / 2 - r), rnd(-D / 2 - r), rnd(fh - CORNICE_RISE * steps)),
            (rnd(W / 2 + r), rnd(D / 2 + r), rnd(fh)),
        ),
        floor=mass.floor + floors - 1,
        seed=derive_seed(mass.seed, "cornice"),
        lod=STRUCTURE,
        tags={"role": "cornice", "mass": mass.id},
    )


def _cuts(edges, start: int, stop: int) -> list[range]:
    """[start, stop) cut at the given edges into consecutive ranges."""
    points = sorted({start, stop, *(e for e in edges if start < e < stop)})
    return [range(a, b) for a, b in zip(points, points[1:], strict=False)]


def _column(bays: range, n: int) -> str:
    """Where a column of bays stands on an n-bay face: the whole face, its axis (centred on
    it), an edge (by a corner) or a flank (between)."""
    if (bays.start, bays.stop) == (0, n):
        return "full"
    if bays.start + bays.stop == n:
        return "axis"
    return "edge" if bays.start == 0 or bays.stop == n else "flank"


AXIS_MIN = 2  # bays: the axis column is at least this wide


def axis_span(n: int, major: set[int], gap: range | None) -> range | None:
    """The axis column of an n-bay vertical face: its central pilaster group, widened to the
    next pilaster lines out while it is narrower than AXIS_MIN bays or doesn't hold the
    portal (`gap`), so an opening on the axis is never a one-bay slot and a door never
    splits the axis full height. None without pilasters."""
    lines = sorted(line for line in major if 2 * line < n)
    if not lines:
        return None
    i = len(lines) - 1
    while i > 0 and (n - 2 * lines[i] < AXIS_MIN or (gap is not None and lines[i] > gap.start)):
        i -= 1
    return range(lines[i], n - lines[i])


def layer_tree(
    face: _Face,
    plan: list[tuple[str, range]],
    portal: tuple[Portal, range, range] | None,
    major: set[int],
    **face_tags,
) -> list[Region]:
    """A face's layer tree, parents before children (docs/LAYERS.md). Ids name panels by
    their first bay and bands by their first floor counted from the mass's foot, so a change
    below (a taller podium) doesn't rename a tower's regions.

    A vertical face splits into columns first, so a column can run the full height: at its
    pilaster lines outside the axis (`axis_span`), then each column into bands at its
    courses (`plan`, from `courses`); the axis column's band holding the portal splits again
    at the portal's edges. A horizontal face splits into bands first, so a band can run the
    full width; the bands the portal sits in split into panels at its edges and the
    pilaster lines (none, on a horizontal axis). Panels carry their column (axis, flank,
    edge or full) and bands their course. Each leaf carries both, and is "cells" (its role
    from its course: base, shaft, lobby or capital) or "portal" (the entrance or a door,
    `portal` being (portal, bays, floors)). The face carries `face_tags` too."""
    mass, fac = face.mass, face.fac
    n, f0 = face.bays, mass.floor
    top = f0 + round(mass.params["height"] / fac.floor_height)
    gap, low = (portal[1], portal[2]) if portal else (range(0), range(f0, f0))
    course_cuts = {r.start for _, r in plan}
    floor_cuts = course_cuts | ({low.stop} if portal else set())

    def course(floors: range) -> str:
        return next(kind for kind, r in plan if r.start <= floors.start < r.stop)

    def node(rid, layer, parent, bays, floors, treatment=None, role=None, **extra) -> Region:
        tags = {
            "size_m": [rnd(len(bays) * fac.bay), rnd(len(floors) * fac.floor_height)],
            "height_m": rnd(floors.start * fac.floor_height),
            **extra,
        }
        if role:
            tags["role"] = role
        return Region(
            rid,
            layer,
            parent,
            mass.id,
            face.edge.name,
            (bays.start, bays.stop),
            (floors.start, floors.stop),
            treatment,
            tags,
        )

    def leaf(rid, layer, parent, bays, floors) -> Region:
        where = {"course": course(floors), "column": _column(bays, n)}
        if portal and bays.start >= gap.start and bays.stop <= gap.stop and floors.stop <= low.stop:
            return node(rid, layer, parent, bays, floors, "portal", "portal", **where)
        return node(
            rid, layer, parent, bays, floors, "cells", COURSE_ROLE[where["course"]], **where
        )

    tree = [
        node(
            face.id,
            "face",
            None,
            range(n),
            range(f0, top),
            facing=face.edge.side,
            standing=standing(mass),
            **face_tags,
        )
    ]
    if fac.axis == "horizontal":
        columns = {*(line for line in major if not gap.start < line < gap.stop)}
        if portal:
            columns |= {gap.start, gap.stop}
        for floors in _cuts(floor_cuts, f0, top):
            split = portal and floors.stop <= low.stop
            panels = _cuts(columns, 0, n) if split else [range(n)]
            bid = f"{face.id}/band.{floors.start - f0:03d}"
            if len(panels) == 1:  # the band is the leaf
                tree.append(leaf(bid, "band", face.id, range(n), floors))
                continue
            tree.append(node(bid, "band", face.id, range(n), floors, course=course(floors)))
            for bays in panels:
                tree.append(leaf(f"{bid}/panel.{bays.start:03d}", "panel", bid, bays, floors))
    else:
        axis = axis_span(n, major, gap if portal else None)
        if axis is None:  # no pilasters: the portal's edges cut the face full height
            columns = {gap.start, gap.stop} if portal else set()
        else:
            columns = {line for line in major if line <= axis.start or line >= axis.stop}
        for bays in _cuts(columns, 0, n):
            pid = f"{face.id}/panel.{bays.start:03d}"
            tree.append(node(pid, "panel", face.id, bays, range(f0, top), column=_column(bays, n)))
            holds = portal and bays.start <= gap.start and gap.stop <= bays.stop
            for floors in _cuts(floor_cuts if holds else course_cuts, f0, top):
                bid = f"{pid}/band.{floors.start - f0:03d}"
                if holds and floors.stop <= low.stop and bays != gap:
                    tree.append(node(bid, "band", pid, bays, floors, course=course(floors)))
                    for sub in _cuts({gap.start, gap.stop}, bays.start, bays.stop):
                        tree.append(leaf(f"{bid}/panel.{sub.start:03d}", "panel", bid, sub, floors))
                else:
                    tree.append(leaf(bid, "band", pid, bays, floors))
    return tree


def _area(r: Region) -> int:
    return (r.bays[1] - r.bays[0]) * (r.floors[1] - r.floors[0])


def programme(regions: list[Region], target: float) -> list[Region]:
    """Grades every leaf of one mass's faces luxury or functional (a `grade` tag): portals
    always luxury, then leaves in order of rank (COLUMN_RANK + COURSE_RANK), higher floors
    first, then nearer their face's axis, then the front face first (FACING_RANK), each
    taken while it brings the luxury area nearer `target` (a share of the mass's facade
    area). Leaves alike in all of these are graded together, so mirror images, and east and
    west faces, always match."""
    width = {r.facade: r.bays[1] for r in regions if r.layer == "face"}
    leaves = [r for r in regions if r.treatment]
    groups: dict[tuple, list[Region]] = defaultdict(list)
    for r in leaves:
        if r.treatment == "portal":
            key: tuple = (math.inf,)
        else:
            rank = COLUMN_RANK[r.tags["column"]] + COURSE_RANK[r.tags["course"]]
            offset = abs(r.bays[0] + r.bays[1] - width[r.facade])
            key = (rank, *r.floors, -offset, FACING_RANK.get(r.facade, 0))
        groups[key].append(r)
    wanted = target * sum(map(_area, leaves))
    chosen, area = set(), 0
    for key in sorted(groups, reverse=True):
        size = sum(map(_area, groups[key]))
        if key[0] == math.inf or area + size / 2 < wanted:
            chosen |= {r.id for r in groups[key]}
            area += size
    return [
        replace(r, tags={**r.tags, "grade": "luxury" if r.id in chosen else "functional"})
        if r.treatment
        else r
        for r in regions
    ]


def _runs(floors: range, blocked: list[range]) -> list[range]:
    """The parts of `floors` not covered by any of `blocked`, as consecutive ranges."""
    runs, start = [], floors.start
    for b in sorted(blocked, key=lambda r: r.start):
        if b.start > start:
            runs.append(range(start, b.start))
        start = max(start, b.stop)
    if start < floors.stop:
        runs.append(range(start, floors.stop))
    return runs


def _place(course: str) -> str:
    """The kind of place a course is, for ALLOWED: run, seam, capital or base."""
    return course if course in ("run", "capital", "base") else "seam"


def _fits(treatment: str, leaf: Region, mass: Element, fac: FacadeSystem, n: int) -> dict | None:
    """The tags `treatment` adds to `leaf` if it fits there, else None. Cuts need a main face
    (not a notch's), a column clear of the corners, the mass's top floor left whole (it holds
    the cornice), and depth: at most a third of the core, and no deeper than the leaf stands
    from either end of its face, so cuts from two faces never meet. An opening is at least
    two floors tall, a recess at most RECESS_FLOORS; a giant order needs three bays and two
    floors; rich windows are shaft windows."""
    (a, b), (f0, f1) = leaf.bays, leaf.floors
    column, top = leaf.tags["column"], mass.floor + round(mass.params["height"] / fac.floor_height)
    if treatment == "field":
        slot = None
        if column == "axis":
            slot = "relief" if leaf.tags["course"] == "capital" or f1 - f0 < 3 else "figure"
        return {"slot": slot} if slot else {}
    if treatment == "giant":
        return {} if b - a >= 3 and f1 - f0 >= 2 else None
    if treatment == "rich":
        return {} if leaf.tags["role"] == "shaft" else None
    if leaf.facade not in FACING_RANK or column not in ("axis", "flank") or f1 >= top:
        return None
    if treatment == "opening" and f1 - f0 < 2 or treatment == "recess" and f1 - f0 > RECESS_FLOORS:
        return None
    across = mass.params["depth" if leaf.facade in ("south", "north") else "width"] - 2 * fac.depth
    nominal = OPENING_DEPTH if treatment == "opening" else RECESS_DEPTH + fac.depth
    depth = rnd(min(nominal, min(a, n - b) * fac.bay, across / 3))
    room = depth - (fac.depth if treatment == "recess" else FRAMES * FRAME_STEP + 0.6)
    return {"depth": depth} if room >= MIN_CUT else None


def treatments(regions: list[Region], mass: Element, fac: FacadeSystem, seed: int) -> list[Region]:
    """Exceptions for one mass's luxury leaves (see ALLOWED). Each kind of place, a course
    and a column, takes one with probability `contrast` scaled by the mass's standing (as
    ornament is), drawn from `seed` (the tower's, shared by mirror twins), so every luxury
    leaf of that kind on the tower matches; on the central tower the axis (on a horizontal
    axis, the full-width bands) always takes one unless contrast is 0, so every building
    expresses its spine. A pick that doesn't fit
    a leaf falls back along its list, else the leaf stays cells. Functional leaves and
    portals are never touched."""
    share = fac.contrast * (1 - (1 - STANDING_ORNAMENT[standing(mass)]) * fac.spread)
    spine = fac.contrast > 0 and standing(mass) == "central"
    spine_column = "full" if fac.axis == "horizontal" else "axis"
    width = {r.facade: r.bays[1] for r in regions if r.layer == "face"}
    picked: dict[tuple[str, str], str | None] = {}

    def pick(course: str, column: str) -> str | None:
        if (course, column) not in picked:
            r = rng(seed, f"treatment.{course}.{column}")
            take = r.random() < share or (spine and column == spine_column)
            options = [t for t in ALLOWED[_place(course)][column] if t in fac.treatments]
            weights = [
                0.5 + fac.contrast if t in CUTS else 1.5 - fac.contrast if t == "rich" else 1.0
                for t in options
            ]
            choice = r.choices(options, weights)[0] if options else None
            picked[course, column] = choice if take else None
        return picked[course, column]

    out = []
    for r in regions:
        if r.treatment == "cells" and r.tags["grade"] == "luxury":
            course, column = r.tags["course"], r.tags["column"]
            first = pick(course, column)
            if first is not None:
                options = [first] + [
                    t for t in ALLOWED[_place(course)][column] if t != first and t in fac.treatments
                ]
                for t in options:
                    extra = _fits(t, r, mass, fac, width[r.facade])
                    if extra is not None:
                        r = replace(r, treatment=t, tags={**r.tags, **extra})
                        break
        out.append(r)
    return out


def _beside(leaves: list[Region], line: int) -> tuple[range, ...]:
    """The stretches of floors where shaft windows stand beside bay `line`."""
    floors = {
        f
        for r in leaves
        if r.treatment in ("cells", "rich")
        and r.tags["role"] == "shaft"
        and r.bays[0] <= line <= r.bays[1]
        for f in range(*r.floors)
    }
    return tuple(_stretches(sorted(floors)))


def dress(
    mass: Element,
    fac: FacadeSystem,
    *,
    portals: tuple[Portal, ...] = (),
    base: int = 0,
    parapet: bool = False,
    foot: bool = False,
    seams=(),
    anchor: int | None = None,
    seed: int | None = None,
) -> tuple[list[Element], list[Region]]:
    """Core, corners, piers, windows, portals, treatments and cornice for one mass; merlons
    too if it has a parapet (it is a terrace, not a tower top) and ornament allows. Returns
    the elements and every face's layer tree, each leaf graded luxury or functional and the
    luxury ones treated as `treatments` decides.

    `base` is the number of floors in the base zone (the ground tier's, matching the
    entrance); `foot`, `seams` and `anchor` (the floor the building's band rhythm counts
    from, None for no sky lobbies) set the courses (see `courses`); `seed` draws the
    treatments (default the mass's own; resolve passes the tower's, shared by twins).
    """
    rho = ornament(mass, fac)
    fh, f0, k = fac.floor_height, mass.floor, fac.pilaster_every
    floors = round(mass.params["height"] / fh)
    top = f0 + floors
    rhythm = None if anchor is None else (anchor, fac.run, fac.lobby)
    plan = courses(
        range(f0, top),
        base,
        capital_floors(floors, base, rho),
        foot=foot,
        seams=seams,
        rhythm=rhythm,
    )
    target = luxury(mass, fac)
    face_tags = {"luxury": target} | ({"rhythm": list(rhythm)} if rhythm else {})

    # Every face's tree first: grades and treatments are decided across the whole mass.
    faces, regions = [], []
    for edge in outline(mass.params["width"], mass.params["depth"], mass.params.get("notch", 0.0)):
        face = _Face(mass, edge, fac)
        n = face.bays
        portal = next((p for p in portals if p.edge == edge.name), None)
        placed = None
        if portal is not None:
            pb = portal.bays if portal.bays is not None else 2 - n % 2
            a = (n - pb) // 2
            placed = (portal, range(a, a + pb), range(f0, f0 + portal.floors))
        major = pilaster_lines(n, k)
        faces.append((face, portal, major))
        regions += layer_tree(face, plan, placed, major, **face_tags)
    regions = programme(regions, target)
    regions = treatments(regions, mass, fac, mass.seed if seed is None else seed)
    leaves_of = defaultdict(list)
    for r in regions:
        if r.treatment:
            leaves_of[r.facade].append(r)
    by_face = {face.edge.name: face for face, _, _ in faces}
    cuts = [by_face[r.facade].cut(r, r.tags["depth"]) for r in regions if r.treatment in CUTS]
    out = _core_and_corners(mass, fac, cuts)

    for face, portal, major in faces:
        n, leaves = face.bays, leaves_of[face.edge.name]

        # Piers on every interior bay line, over the floors no leaf other than cells spans;
        # copies above the lowest run on a line are named from the floor they start on. On a
        # horizontal axis a pier carries spandrel bands only beside shaft windows.
        groups = defaultdict(list)  # (order, start, stop, prefix, bands) -> bay lines
        for line in range(1, n):
            blocked = [
                range(*r.floors)
                for r in leaves
                if r.treatment not in ("cells", "rich") and r.bays[0] < line < r.bays[1]
            ]
            order = "pilaster" if line in major else "pier"
            bands = _beside(leaves, line) if fac.axis == "horizontal" else ()
            for i, run in enumerate(_runs(range(f0, top), blocked)):
                prefix = face.id if i == 0 else f"{face.id}/floor.{run.start:03d}"
                groups[order, run.start, run.stop, prefix, bands].append(line)
        named = defaultdict(int)
        for (order, start, stop, prefix, bands), lines in sorted(
            groups.items(), key=lambda g: (*g[0][:4], [(r.start, r.stop) for r in g[0][4]])
        ):
            for run in progressions(lines, k):
                name = f"{order}s.{named[order]}"
                out += face.piers(
                    name, run, range(start, stop), order, rho, list(bands), prefix=prefix
                )
                named[order] += 1

        # Cells leaves side by side on the same floors share one window array (and one row of
        # channels), so the plan stays compact however finely the face is split. Rich leaves
        # join only rich ones; a recess's back wall is its own block, set back.
        runs: list[list[Region]] = []
        for r in sorted(leaves, key=lambda r: (r.floors, r.bays)):
            last = runs[-1][-1] if runs else None
            if (
                r.treatment in ("cells", "rich")
                and last is not None
                and (last.floors, last.tags["role"], last.treatment, last.bays[1])
                == (r.floors, r.tags["role"], r.treatment, r.bays[0])
            ):
                runs[-1].append(r)
            else:
                runs.append([r])
        for run in runs:
            first = run[0]
            name = first.id.removeprefix(face.id + "/")
            bays, rows = range(first.bays[0], run[-1].bays[1]), range(*first.floors)
            role, treatment = first.tags.get("role"), first.treatment
            ids = [r.id for r in run]
            if treatment in ("cells", "rich"):
                out += face.windows(
                    f"{name}/windows", bays, rows, role, rho, ids, rich=treatment == "rich"
                )
            elif treatment == "recess":
                back = first.tags["depth"] - fac.depth
                out += face.windows(f"{name}/windows", bays, rows, role, rho, ids, inset=back)
                inner = range(bays.start + 1, bays.stop)
                if inner:
                    out += face.piers(
                        f"{name}/piers",
                        inner,
                        rows,
                        "back",
                        rho,
                        [],
                        prefix=f"{first.id}/back",
                        inset=back,
                    )
                out += face.recess(f"{name}/slab", first)
            elif treatment == "field":
                out += face.field(f"{name}/field", first)
            elif treatment == "opening":
                out += face.opening(f"{name}/opening", first)
            elif treatment == "giant":
                out += face.giant(f"{name}/giant", first)
            else:  # portal
                out.append(face.portal(f"{name}/{portal.kind}", portal, bays, top, first.id))
        if parapet and rho >= MERLONS_AT:
            for i, run in enumerate(progressions(major, k)):
                out += face.merlons(f"merlons.{i}", run, top)
    out.append(_cornice(mass, fac, rho))
    return out, regions
