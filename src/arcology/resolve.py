"""The grammar, Phase 0: a stepped podium and a central tower with setbacks, as massing boxes.

Plain Python, no Blender. Every value drawn from a spec range comes from the owning
element's seed (see seeds.py), and every dimension sits on the grids: heights in whole
floors, widths and depths in whole bays.
"""

from arcology.plan import LODS, Element, Plan
from arcology.seeds import derive_seed, path_seed, rng
from arcology.spec import Spec

ROOT = "arcology"


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


def _mass(eid, seed, width, depth, floor, floors, fh, role) -> Element:
    return Element(
        id=eid,
        kind="mass",
        recipe="mass.box",
        params={"width": _r(width), "depth": _r(depth), "height": _r(floors * fh)},
        translation=(0.0, 0.0, _r(floor * fh)),
        floor=floor,
        seed=seed,
        lod=LODS,
        tags={"role": role},
    )


def resolve(spec: Spec) -> Plan:
    fh, bay = spec.floor_height, spec.facade.bay_width
    elements: list[Element] = []

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
        elements.append(_mass(tid, ts, w, d, floor, floors, fh, "podium"))
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
        elements.append(_mass(sid, sseed, w, d, start, count, fh, "tower"))

    return Plan(seed=spec.seed, floor_height=fh, bay_width=bay, elements=tuple(elements))
