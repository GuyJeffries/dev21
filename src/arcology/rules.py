"""Primitives shared by the grammar's rule modules (resolve, compose). Plain Python."""

import math
from dataclasses import dataclass

from arcology.plan import Element
from arcology.seeds import rng

ROOT = "arcology"
CENTRAL = f"{ROOT}/tower.central"

# Representation levels each kind of element belongs to (docs/PLAN.md section 13).
DETAIL = ("L0", "L1")
STRUCTURE = ("L0", "L1", "L2")
DISTANT = ("L2",)  # stand-ins for detail that drops out at L2
ENVELOPE = ("L3",)
EVERY_LEVEL = ("L0", "L1", "L2", "L3")


class ResolveError(ValueError):
    """The spec's values, once drawn, can't form a valid building. Names the element."""


def sample(value, seed: int, name: str, *, integer: bool = False):
    """A spec value: fixed as given, or drawn from [min, max] by the decision `name`."""
    if not isinstance(value, tuple):
        return value
    lo, hi = value
    r = rng(seed, name)
    return r.randint(lo, hi) if integer else r.uniform(float(lo), float(hi))


def notch_for(wanted_bays: int, bay: float, steps: list[float], smallest: float) -> float:
    """A corner notch of `wanted_bays`, no deeper than any setback step (so no upper corner
    overhangs a notch) and leaving the smallest section at least a bay on every face."""
    room = min([*steps, (smallest - bay) / 2])
    return max(0, min(wanted_bays, math.floor(room / bay + 1e-9))) * bay


def bays(x: float, bay: float) -> float:
    """`x` rounded to a whole number of bays, at least one."""
    return max(1, round(x / bay)) * bay


def rnd(x: float) -> float:
    return round(x, 4)


def box_extent(w, d, h):
    return ((rnd(-w / 2), rnd(-d / 2), 0.0), (rnd(w / 2), rnd(d / 2), rnd(h)))


def mass(eid, seed, width, depth, floor, floors, fh, tags, x=0.0, y=0.0, notch=0.0) -> Element:
    """A massing block (the envelope, L3), base-centred at (x, y) on `floor`: a box, or with
    every corner notched."""
    h = floors * fh
    params = {"width": rnd(width), "depth": rnd(depth), "height": rnd(h)}
    if notch:
        params["notch"] = rnd(notch)
    return Element(
        id=eid,
        kind="mass",
        recipe="mass.notched" if notch else "mass.box",
        params=params,
        translation=(rnd(x), rnd(y), rnd(floor * fh)),
        extent=box_extent(width, depth, h),
        floor=floor,
        seed=seed,
        lod=ENVELOPE,
        tags=tags,
    )


def standing(m: Element) -> str:
    """A mass's place in the hierarchy: central, sister (ring 0), pavilion, or podium."""
    if m.tags.get("role") == "podium":
        return "podium"
    if m.tags.get("tower") == CENTRAL:
        return "central"
    return "sister" if m.tags.get("ring", 0) == 0 else "pavilion"


def ring_params(m: Element, rings: list[list[float]]) -> dict:
    """Ring recipe params following `m`'s outline; rings are [reach, z0, z1], reach
    positive outward from the envelope, negative inward."""
    params = {"width": m.params["width"], "depth": m.params["depth"]}
    if m.params.get("notch"):
        params["notch"] = m.params["notch"]
    params["rings"] = [[rnd(v) for v in ring] for ring in rings]
    return params


# Outlines: a mass's footprint as a rectilinear polygon, walked counter-clockwise.

SIDE_ROTATION = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}
_NORMAL_SIDE = {(0, -1): "south", (1, 0): "east", (0, 1): "north", (-1, 0): "west"}


@dataclass(frozen=True)
class Edge:
    """One straight run of a footprint, relative to the mass's centre.

    Walking a counter-clockwise outline, the interior is on the left, so the outward
    normal is the direction turned right. `corner` names the vertex at the edge's end,
    and `end_convex` says whether the outline turns left (convex) or right there.
    """

    name: str
    a: tuple[float, float]
    b: tuple[float, float]
    corner: str
    end_convex: bool

    @property
    def length(self) -> float:
        return abs(self.b[0] - self.a[0]) + abs(self.b[1] - self.a[1])

    @property
    def direction(self) -> tuple[int, int]:
        dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
        return (
            int(math.copysign(1, dx)) if abs(dx) > 1e-9 else 0,
            int(math.copysign(1, dy)) if abs(dy) > 1e-9 else 0,
        )

    @property
    def normal(self) -> tuple[int, int]:
        dx, dy = self.direction
        return (dy, -dx)

    @property
    def side(self) -> str:
        return _NORMAL_SIDE[self.normal]

    @property
    def rotation(self) -> float:
        """The facade frame's rotation: local -Y outward, local +X along the edge."""
        return SIDE_ROTATION[self.side]

    @property
    def mid(self) -> tuple[float, float]:
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2)


def outline(width: float, depth: float, notch: float = 0.0) -> list[Edge]:
    """Counter-clockwise footprint edges: a rectangle, or one with every corner notched
    (a square of side `notch` cut from each corner, leaving re-entrant corners)."""
    w, d, c = width / 2, depth / 2, notch
    if c <= 0:
        points = [
            ((-w, -d), "south", "se"),
            ((w, -d), "east", "ne"),
            ((w, d), "north", "nw"),
            ((-w, d), "west", "sw"),
        ]
    else:
        points = [
            ((-w + c, -d), "south", "se.1"),
            ((w - c, -d), "se.east", "se.2"),
            ((w - c, -d + c), "se.south", "se.3"),
            ((w, -d + c), "east", "ne.1"),
            ((w, d - c), "ne.north", "ne.2"),
            ((w - c, d - c), "ne.east", "ne.3"),
            ((w - c, d), "north", "nw.1"),
            ((-w + c, d), "nw.west", "nw.2"),
            ((-w + c, d - c), "nw.north", "nw.3"),
            ((-w, d - c), "west", "sw.1"),
            ((-w, -d + c), "sw.south", "sw.2"),
            ((-w + c, -d + c), "sw.west", "sw.3"),
        ]
    n = len(points)
    edges = []
    for i, (a, name, corner) in enumerate(points):
        b, c_next = points[(i + 1) % n][0], points[(i + 2) % n][0]
        d1 = (b[0] - a[0], b[1] - a[1])
        d2 = (c_next[0] - b[0], c_next[1] - b[1])
        convex = d1[0] * d2[1] - d1[1] * d2[0] > 0
        edges.append(Edge(name, (rnd(a[0]), rnd(a[1])), (rnd(b[0]), rnd(b[1])), corner, convex))
    return edges


def in_outline(
    x: float, y: float, width: float, depth: float, notch: float = 0.0, tol: float = 1e-6
) -> bool:
    """Whether (x, y), relative to the mass's centre, lies within its footprint."""
    if abs(x) > width / 2 + tol or abs(y) > depth / 2 + tol:
        return False
    return not (abs(x) > width / 2 - notch + tol and abs(y) > depth / 2 - notch + tol)
