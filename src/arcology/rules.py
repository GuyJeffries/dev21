"""Primitives shared by the grammar's rule modules (resolve, compose). Plain Python."""

from arcology.plan import Element
from arcology.seeds import rng

ROOT = "arcology"

# Representation levels each kind of element belongs to (docs/PLAN.md section 13).
DETAIL = ("L0", "L1")
STRUCTURE = ("L0", "L1", "L2")
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


def bays(x: float, bay: float) -> float:
    """`x` rounded to a whole number of bays, at least one."""
    return max(1, round(x / bay)) * bay


def rnd(x: float) -> float:
    return round(x, 4)


def box_extent(w, d, h):
    return ((rnd(-w / 2), rnd(-d / 2), 0.0), (rnd(w / 2), rnd(d / 2), rnd(h)))


def mass(eid, seed, width, depth, floor, floors, fh, tags, x=0.0, y=0.0) -> Element:
    """A massing box (the envelope, L3), base-centred at (x, y) on `floor`."""
    h = floors * fh
    return Element(
        id=eid,
        kind="mass",
        recipe="mass.box",
        params={"width": rnd(width), "depth": rnd(depth), "height": rnd(h)},
        translation=(rnd(x), rnd(y), rnd(floor * fh)),
        extent=box_extent(width, depth, h),
        floor=floor,
        seed=seed,
        lod=ENVELOPE,
        tags=tags,
    )
