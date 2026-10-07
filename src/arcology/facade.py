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
"""

from collections import defaultdict
from dataclasses import dataclass, replace

from arcology.compose import PARAPET_HEIGHT
from arcology.plan import Element
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
from arcology.seeds import derive_seed, path_seed
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
CORNICE_REACH, CORNICE_RISE = 0.3, 0.35  # per step of a cornice
# Merlons: pylons continuing pilasters above the roof, stepping in over the parapet; width as
# a share of the pier's, standing slightly proud so no face lies in the parapet's.
MERLON_STEPS, MERLON_RISE, MERLON_WIDTH, MERLON_PROUD = 3, 1.0, 2.0, 0.15

# Ornament density by standing, as a share of style.ornament_density, and the density each
# system needs.
STANDING_ORNAMENT = {"central": 1.0, "sister": 0.8, "podium": 0.7, "pavilion": 0.6}
CHEVRONS_AT, FLUTES_AT, MERLONS_AT = 0.4, 0.55, 0.6
DOUBLE_CHEVRONS_AT = 0.6


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

    @property
    def depth(self) -> float:
        """Envelope to core: piers stand proud by pier_depth, windows sit behind that."""
        return rnd(self.pier_depth + self.recess + GLASS)

    def window(self, zone: str, chevrons: int = 0) -> tuple[str, dict, tuple]:
        """Recipe, params and extent of a window in `zone`: a channel filling the bay
        between two piers, glazed above a spandrel (shaft) or a stone panel (capital),
        or a narrower opening between stone jambs (base)."""
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
            if self.axis == "horizontal":  # a stone band, standing forward, for a spandrel
                recipe = "window.deco_band"
                params["band"] = BAND_FRONT
                nearest = BAND_FRONT
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
        elif zone == "base":
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
    )
    if system.pier_width >= system.bay / 2:
        raise ResolveError(
            f"{ROOT}/facade: piers {system.pier_width:g} m wide leave no room in a bay"
        )
    return system


def facade_variant(spec: Spec, fac: FacadeSystem, seed: int) -> FacadeSystem:
    """A tower group's own facade, for varied repetition: density, mullions and pilaster
    rhythm drawn afresh within the spec's ranges; the bay, piers and depths stay the
    building's, so the towers still share one grid."""
    fs = derive_seed(seed, "facade")
    f = spec.facade
    return replace(
        fac,
        density=rnd(sample(f.density, fs, "density")),
        mullions=sample(f.mullions, fs, "mullions", integer=True),
        pilaster_every=_pilasters(spec, fs),
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

    def at(self, u: float, floor: int) -> tuple[float, float, float]:
        """World position of facade coordinate u at the base of `floor`."""
        (ox, oy), (ux, uy) = self.edge.mid, self.edge.direction
        mx, my, mz = self.mass.translation
        z = mz + (floor - self.mass.floor) * self.fac.floor_height
        return (rnd(mx + ox + ux * u), rnd(my + oy + uy * u), rnd(z))

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

    def element(self, name, kind, recipe, params, extent, u, floor, lod, **extra) -> Element:
        return Element(
            id=f"{self.id}/{name}",
            kind=kind,
            recipe=recipe,
            params=params,
            translation=self.at(u, floor),
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

    def windows(self, name: str, bays: range, floors: range, zone: str, rho: float):
        if not bays or not floors:
            return []
        recipe, params, extent = self.fac.window(zone, chevrons(rho))
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
            array={"prefix": self.id, "axes": axes},
            tags={"zone": zone},
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
            array={"prefix": f"{self.id}/channel.{zone}", "axes": axes[:1]},
            tags={"zone": zone},
        )
        return [window, channel]

    def piers(self, name: str, lines: range, from_floor: int, order: str, rho: float, shaft: range):
        """Piers on bay `lines` from `from_floor` to the top of the mass: full-depth
        pilasters (fluted as ornament allows), or minor piers standing back between them. On
        a horizontal axis piers stand back and, up the `shaft`, give way to glass behind the
        spandrel bands they carry across, so each floor's windows read as one ribbon."""
        fac = self.fac
        pw, dd = fac.pier_width, fac.depth
        h = rnd(self.mass.params["height"] - (from_floor - self.mass.floor) * fac.floor_height)
        params = {"width": rnd(pw), "depth": dd, "height": h}
        recipe, front = "pier.strip", 0.0
        if order == "pilaster" and flutes(rho):
            recipe = "pier.fluted"
            params |= {"flutes": flutes(rho), "reed": REED}
        elif order == "pier" and fac.axis == "horizontal":
            front = params["front"] = fac.pier_depth
            first = max(shaft.start, from_floor)
            if shaft.stop > first:  # up the shaft: glass behind each floor's band
                recipe, front = "pier.banded", BAND_FRONT
                params |= {
                    "glass": rnd(fac.pier_depth + fac.recess),
                    "band": BAND_FRONT,
                    "floor_height": fac.floor_height,
                    "sill": rnd(fac.floor_height * (0.55 - 0.45 * fac.density)),
                    "bands": [first - from_floor, shaft.stop - first],
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
                array={"prefix": self.id, "axes": axes},
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

    def portal(self, portal: Portal, bays: range, top: int) -> Element:
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
        tags = {"bays": [bays.start, bays.stop], "floors": [f0, f0 + portal.floors]}
        return self.element(
            portal.kind,
            portal.kind,
            "entrance.deco_main",
            params,
            extent,
            self.u((bays.start + bays.stop) / 2),
            f0,
            DETAIL,
            tags=tags,
        )


def _core_and_corners(mass: Element, fac: FacadeSystem) -> list[Element]:
    W, D, H = mass.params["width"], mass.params["depth"], mass.params["height"]
    notch, dd = mass.params.get("notch", 0.0), fac.depth
    core = {"width": rnd(W - 2 * dd), "depth": rnd(D - 2 * dd), "height": H}
    if notch:
        core["notch"] = notch  # an inward offset of a notched outline keeps the notch size
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


def dress(
    mass: Element,
    fac: FacadeSystem,
    *,
    portals: tuple[Portal, ...] = (),
    base: int = 0,
    parapet: bool = False,
) -> list[Element]:
    """Core, corners, piers, windows, portals and cornice for one mass; merlons too if it
    has a parapet (it is a terrace, not a tower top) and ornament allows.

    `base` is the number of floors in the base zone (the ground tier's, matching the entrance).
    """
    rho = ornament(mass, fac)
    fh, f0, k = fac.floor_height, mass.floor, fac.pilaster_every
    floors = round(mass.params["height"] / fh)
    top = f0 + floors
    capital = capital_floors(floors, base, rho)
    zones = [
        ("base", range(f0, f0 + base)),
        ("shaft", range(f0 + base, top - capital)),
        ("capital", range(top - capital, top)),
    ]
    out = _core_and_corners(mass, fac)
    for edge in outline(mass.params["width"], mass.params["depth"], mass.params.get("notch", 0.0)):
        face = _Face(mass, edge, fac)
        n = face.bays
        portal = next((p for p in portals if p.edge == edge.name), None)
        if portal is None:
            gap, pf = range(0), f0
            rects = [("", range(n), range(f0, top))]
        else:
            pb = portal.bays if portal.bays is not None else 2 - n % 2
            a = (n - pb) // 2
            gap, pf = range(a, a + pb), f0 + portal.floors
            rects = [
                (".left", range(a), range(f0, top)),
                (".above", gap, range(pf, top)),
                (".right", range(a + pb, n), range(f0, top)),
            ]

        major = pilaster_lines(n, k)
        groups = defaultdict(list)  # (order, from floor) -> bay lines
        for line in range(1, n):
            order = "pilaster" if line in major else "pier"
            groups[order, pf if gap.start < line < gap.stop else f0].append(line)
        named = defaultdict(int)
        for (order, start), lines in sorted(groups.items()):
            for run in progressions(lines, k):
                out += face.piers(f"{order}s.{named[order]}", run, start, order, rho, zones[1][1])
                named[order] += 1

        for zone, zone_floors in zones:
            for part, bays, rect_floors in rects:
                fl = range(
                    max(zone_floors.start, rect_floors.start),
                    min(zone_floors.stop, rect_floors.stop),
                )
                out += face.windows(f"windows.{zone}{part}", bays, fl, zone, rho)
        if portal is not None:
            out.append(face.portal(portal, gap, top))
        if parapet and rho >= MERLONS_AT:
            for i, run in enumerate(progressions(major, k)):
                out += face.merlons(f"merlons.{i}", run, top)
    out.append(_cornice(mass, fac, rho))
    return out
