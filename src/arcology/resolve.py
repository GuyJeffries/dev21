"""The grammar: spec -> resolved plan. Plain Python, no Blender.

Phase 0 massing: a stepped podium and a central tower with setbacks. Phase 1 dresses each
mass with a facade: stone piers on every bay line, an L-shaped piece at each corner, a
window on every bay of every floor, and a centred main entrance on the podium's south face.

Every value drawn from a spec range comes from the owning element's seed (see seeds.py),
and every dimension sits on the grids: heights in whole floors, widths in whole bays.

Representation levels (docs/PLAN.md section 13): the envelope box is L3; the core it
wraps, the piers and the corners are L0-L2; windows and the entrance are L0-L1.
"""

from dataclasses import dataclass

from arcology.plan import Element, Plan
from arcology.seeds import derive_seed, path_seed, rng
from arcology.spec import Spec

ROOT = "arcology"
DETAIL = ("L0", "L1")
STRUCTURE = ("L0", "L1", "L2")
ENVELOPE = ("L3",)

# Each facade's frame: rotation, and the direction of +u (left to right seen from outside).
SIDES = {
    "south": (0.0, (1, 0)),
    "east": (90.0, (0, 1)),
    "north": (180.0, (-1, 0)),
    "west": (270.0, (0, -1)),
}
# Each corner piece's rotation, and which corner of the mass it sits on.
CORNERS = {
    "se": (0.0, (1, -1)),
    "ne": (90.0, (1, 1)),
    "nw": (180.0, (-1, 1)),
    "sw": (270.0, (-1, -1)),
}

GLASS = 0.05  # glazing thickness
MULLION_DEPTH = 0.06  # mullions and transoms stand this far in front of the glass
ENTRANCE_FRAMES = 3
ENTRANCE_FRAME_STEP = 0.5  # how far each stepped frame stands in front of the next
ENTRANCE_PLINTH = 2.0  # plinth reach in front of the outermost frame
ENTRANCE_APRON = 1.0  # plinth reach beyond the portal on each side
ENTRANCE_CREST = 2.4  # stepped crest above the portal


class ResolveError(ValueError):
    """The spec's values, once drawn, can't form a valid building. Names the element."""


def sample(value, seed: int, name: str, *, integer: bool = False):
    """A spec value: fixed as given, or drawn from [min, max] by the decision `name`."""
    if not isinstance(value, tuple):
        return value
    lo, hi = value
    r = rng(seed, name)
    return r.randint(lo, hi) if integer else r.uniform(float(lo), float(hi))


def _bays(x: float, bay: float) -> float:
    """`x` rounded to a whole number of bays, at least one."""
    return max(1, round(x / bay)) * bay


def _r(x: float) -> float:
    return round(x, 4)


def _box(w, d, h):
    return ((_r(-w / 2), _r(-d / 2), 0.0), (_r(w / 2), _r(d / 2), _r(h)))


def _mass(eid, seed, width, depth, floor, floors, fh, role) -> Element:
    h = floors * fh
    return Element(
        id=eid,
        kind="mass",
        recipe="mass.box",
        params={"width": _r(width), "depth": _r(depth), "height": _r(h)},
        translation=(0.0, 0.0, _r(floor * fh)),
        extent=_box(width, depth, h),
        floor=floor,
        seed=seed,
        lod=ENVELOPE,
        tags={"role": role},
    )


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

    @property
    def depth(self) -> float:
        """Envelope to core: piers stand proud by pier_depth, windows sit behind that."""
        return _r(self.pier_depth + self.recess + GLASS)

    def window(self) -> tuple[dict, tuple]:
        """A glazed channel filling the bay between two piers: spandrel below, glass above."""
        clear = self.bay - self.pier_width
        params = {
            "width": _r(clear),
            "height": _r(self.floor_height),
            "front": _r(self.pier_depth),
            "recess": _r(self.recess),
            "glass": GLASS,
            "sill": _r(self.floor_height * (0.55 - 0.45 * self.density)),
            "mullions": self.mullions,
        }
        nearest = self.pier_depth + min(self.recess / 2, self.recess - MULLION_DEPTH)
        extent = (
            (_r(-clear / 2), _r(nearest), 0.0),
            (_r(clear / 2), self.depth, _r(self.floor_height)),
        )
        return params, extent


def _facade_system(spec: Spec) -> FacadeSystem:
    fs = path_seed(spec.seed, f"{ROOT}/facade")
    f = spec.facade
    system = FacadeSystem(
        bay=f.bay_width,
        floor_height=spec.floor_height,
        pier_width=_r(sample(f.pier_width, fs, "pier_width")),
        pier_depth=f.pier_depth,
        recess=f.window_recess,
        density=_r(sample(f.density, fs, "density")),
        mullions=sample(f.mullions, fs, "mullions", integer=True),
    )
    if system.pier_width >= system.bay / 2:
        raise ResolveError(
            f"{ROOT}/facade: piers {system.pier_width:g} m wide leave no room in a bay"
        )
    return system


def _entrance_params(clear: float, floors: int, fac: FacadeSystem) -> tuple[dict, tuple]:
    height = floors * fac.floor_height
    frame_width = _r(min(0.6, clear / (4 * ENTRANCE_FRAMES)))
    params = {
        "width": _r(clear),
        "height": _r(height),
        "depth": fac.depth,
        "frames": ENTRANCE_FRAMES,
        "frame_step": ENTRANCE_FRAME_STEP,
        "frame_width": frame_width,
        "door_height": _r(min(height * 0.5, 5.0)),
        "mullions": max(2, round(clear / 1.5)),
        "plinth": ENTRANCE_PLINTH,
        "apron": ENTRANCE_APRON,
        "crest": ENTRANCE_CREST,
    }
    reach = ENTRANCE_FRAMES * ENTRANCE_FRAME_STEP + ENTRANCE_PLINTH
    extent = (
        (_r(-clear / 2 - ENTRANCE_APRON), _r(-reach), 0.0),
        (_r(clear / 2 + ENTRANCE_APRON), fac.depth, _r(height + ENTRANCE_CREST)),
    )
    return params, extent


@dataclass(frozen=True)
class _Face:
    """One facade of one mass: places elements in the facade's own frame."""

    mass: Element
    side: str
    fac: FacadeSystem

    @property
    def rotation(self) -> float:
        return SIDES[self.side][0]

    @property
    def length(self) -> float:
        return self.mass.params["width" if self.side in ("south", "north") else "depth"]

    @property
    def bays(self) -> int:
        return round(self.length / self.fac.bay)

    @property
    def id(self) -> str:
        return f"{self.mass.id}/facade.{self.side}"

    def at(self, u: float, floor: int) -> tuple[float, float, float]:
        """World position of facade coordinate u (metres from centre) at the base of `floor`."""
        w, d = self.mass.params["width"], self.mass.params["depth"]
        ox, oy = {
            "south": (0, -d / 2),
            "east": (w / 2, 0),
            "north": (0, d / 2),
            "west": (-w / 2, 0),
        }[self.side]
        ux, uy = SIDES[self.side][1]
        z = self.mass.translation[2] + (floor - self.mass.floor) * self.fac.floor_height
        return (_r(ox + ux * u), _r(oy + uy * u), _r(z))

    def axis(self, name: str, start: int, count: int) -> dict:
        ux, uy = SIDES[self.side][1]
        step = (
            [0.0, 0.0, self.fac.floor_height]
            if name == "floor"
            else [_r(ux * self.fac.bay), _r(uy * self.fac.bay), 0.0]
        )
        return {"name": name, "start": start, "count": count, "step": step, "digits": 3}

    def element(self, name, kind, recipe, params, extent, u, floor, lod, **extra) -> Element:
        return Element(
            id=f"{self.id}/{name}",
            kind=kind,
            recipe=recipe,
            params=params,
            translation=self.at(u, floor),
            rotation_z_deg=self.rotation,
            extent=extent,
            floor=floor,
            seed=derive_seed(self.mass.seed, f"facade.{self.side}/{name}"),
            lod=lod,
            tags={"facade": self.side, "building": ROOT, "role": kind, **extra.pop("tags", {})},
            **extra,
        )

    def windows(self, name: str, bays: range, floors: range) -> list[Element]:
        if not bays or not floors:
            return []
        params, extent = self.fac.window()
        u = -self.length / 2 + self.fac.bay * (bays.start + 0.5)
        axes = [
            self.axis("bay", bays.start, len(bays)),
            self.axis("floor", floors.start, len(floors)),
        ]
        array = {"prefix": self.id, "axes": axes}
        return [
            self.element(
                name,
                "window",
                "window.deco_tall",
                params,
                extent,
                u,
                floors.start,
                DETAIL,
                array=array,
            )
        ]

    def piers(self, name: str, lines: range, from_floor: int) -> list[Element]:
        """Piers on interior bay lines, from `from_floor` to the top of the mass."""
        if not lines:
            return []
        pw, dd = self.fac.pier_width, self.fac.depth
        h = _r(self.mass.params["height"] - (from_floor - self.mass.floor) * self.fac.floor_height)
        params = {"width": _r(pw), "depth": dd, "height": h}
        extent = ((_r(-pw / 2), 0.0, 0.0), (_r(pw / 2), dd, h))
        u = -self.length / 2 + self.fac.bay * lines.start
        array = {"prefix": self.id, "axes": [self.axis("pier", lines.start, len(lines))]}
        return [
            self.element(
                name, "pier", "pier.strip", params, extent, u, from_floor, STRUCTURE, array=array
            )
        ]


def _dress(mass: Element, fac: FacadeSystem, entrance: tuple[int, int] | None) -> list[Element]:
    """Core, corners, piers and windows for one mass.

    `entrance` is (bays, floors) of a portal centred on the mass's south face, or None.
    """
    W, D, H = mass.params["width"], mass.params["depth"], mass.params["height"]
    f0, dd = mass.floor, fac.depth
    top = f0 + round(H / fac.floor_height)
    out = [
        Element(
            id=f"{mass.id}/core",
            kind="core",
            recipe="mass.box",
            params={"width": _r(W - 2 * dd), "depth": _r(D - 2 * dd), "height": H},
            translation=mass.translation,
            extent=_box(W - 2 * dd, D - 2 * dd, H),
            floor=f0,
            seed=derive_seed(mass.seed, "core"),
            lod=STRUCTURE,
            tags={"role": mass.tags["role"]},
        )
    ]

    reach = _r(max(fac.pier_width / 2, dd))
    for name, (rotation, (sx, sy)) in CORNERS.items():
        out.append(
            Element(
                id=f"{mass.id}/corner.{name}",
                kind="pier",
                recipe="pier.corner",
                params={"arm": _r(fac.pier_width / 2), "depth": dd, "height": H},
                translation=(_r(sx * W / 2), _r(sy * D / 2), mass.translation[2]),
                rotation_z_deg=rotation,
                extent=((-reach, 0.0, 0.0), (0.0, reach, H)),
                floor=f0,
                seed=derive_seed(mass.seed, f"corner.{name}"),
                lod=STRUCTURE,
                tags={"role": "corner"},
            )
        )

    for side in SIDES:
        face = _Face(mass, side, fac)
        n = face.bays
        if side != "south" or entrance is None:
            out += face.piers("piers", range(1, n), f0)
            out += face.windows("windows", range(n), range(f0, top))
            continue
        eb, ef = entrance
        a = (n - eb) // 2  # first bay of the portal; the portal is centred
        out += face.piers("piers.left", range(1, a + 1), f0)
        out += face.piers("piers.above", range(a + 1, a + eb), f0 + ef)
        out += face.piers("piers.right", range(a + eb, n), f0)
        out += face.windows("windows.left", range(a), range(f0, top))
        out += face.windows("windows.above", range(a, a + eb), range(f0 + ef, top))
        out += face.windows("windows.right", range(a + eb, n), range(f0, top))
        params, extent = _entrance_params(eb * fac.bay - fac.pier_width, ef, fac)
        extra = {"tags": {"bays": [a, a + eb], "floors": [f0, f0 + ef]}}
        out.append(
            face.element(
                "entrance",
                "entrance",
                "entrance.deco_main",
                params,
                extent,
                0.0,
                f0,
                DETAIL,
                **extra,
            )
        )
    return out


def _entrance(spec: Spec, tier0: Element, fac: FacadeSystem) -> tuple[int, int]:
    """Portal size in (bays, floors), centred on the south face of the bottom podium tier."""
    eid = f"{tier0.id}/facade.south/entrance"
    es = path_seed(spec.seed, eid)
    n = round(tier0.params["width"] / fac.bay)
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


def resolve(spec: Spec) -> Plan:
    fh, bay = spec.floor_height, spec.facade.bay_width
    masses: list[Element] = []

    # Podium: each tier steps in by the same whole number of bays per side.
    pid = f"{ROOT}/podium"
    ps = path_seed(spec.seed, pid)
    pm = spec.primary_mass
    base_w = _bays(sample(pm.width, ps, "width"), bay)
    base_d = _bays(sample(pm.depth, ps, "depth"), bay)
    inset = sample(pm.tier_inset, ps, "tier_inset")
    step_w, step_d = _bays(inset * base_w, bay), _bays(inset * base_d, bay)
    floor = 0
    for i, tier in enumerate(pm.tiers):
        tid = f"{pid}/tier.{i}"
        ts = derive_seed(ps, f"tier.{i}")
        w, d = base_w - 2 * i * step_w, base_d - 2 * i * step_d
        if w < bay or d < bay:
            raise ResolveError(f"{tid}: podium steps in to nothing; reduce tier_inset or tiers")
        floors = sample(tier, ts, "floors", integer=True)
        masses.append(_mass(tid, ts, w, d, floor, floors, fh, "podium"))
        floor += floors
    top_w, top_d = w, d

    # Central tower: sits on the top tier with at least a bay of terrace on every side,
    # and steps in at each setback floor.
    cid = f"{ROOT}/tower.central"
    cs = path_seed(spec.seed, cid)
    ct = spec.central_tower
    w = _bays(sample(ct.width, cs, "width"), bay)
    d = _bays(sample(ct.depth, cs, "depth"), bay)
    floors = sample(ct.floors, cs, "floors", integer=True)
    inset = sample(ct.setback_inset, cs, "setback_inset")
    setbacks = [
        sample(s, derive_seed(cs, f"setback.{k}"), "floor", integer=True)
        for k, s in enumerate(ct.setbacks)
    ]
    if setbacks != sorted(set(setbacks)) or any(not 0 < s < floors for s in setbacks):
        raise ResolveError(
            f"{cid}: setbacks {setbacks} must rise strictly between floor 1 and {floors - 1}"
        )
    if w > top_w - 2 * bay or d > top_d - 2 * bay:
        raise ResolveError(
            f"{cid}: a {w:g} x {d:g} m tower doesn't fit on the {top_w:g} x {top_d:g} m "
            "top podium tier with a bay of terrace on each side"
        )
    marks = [0, *setbacks, floors]
    for k in range(len(marks) - 1):
        sid = f"{cid}/section.{k}"
        if k:
            w, d = w - 2 * _bays(inset * w, bay), d - 2 * _bays(inset * d, bay)
            if w < bay or d < bay:
                raise ResolveError(f"{sid}: tower steps in to nothing; reduce setback_inset")
        sseed = derive_seed(cs, f"section.{k}")
        start, count = floor + marks[k], marks[k + 1] - marks[k]
        masses.append(_mass(sid, sseed, w, d, start, count, fh, "tower"))

    # Facades, after massing so facade choices can never change the massing.
    fac = _facade_system(spec)
    portal = _entrance(spec, masses[0], fac)
    elements: list[Element] = []
    for m in masses:
        elements.append(m)
        elements.extend(_dress(m, fac, portal if m is masses[0] else None))
    return Plan(seed=spec.seed, floor_height=fh, bay_width=bay, elements=tuple(elements))
