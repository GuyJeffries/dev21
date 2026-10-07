"""Structural metrics on a resolved plan, from docs/PLAN.md section 20. Plain Python.

Massing checks compare each mass with the one directly below it (one stack so far).
Facade checks work on arrays without expanding them, so they stay fast at 10k+ windows.
Later phases add dominance, connection validity and termination.
"""

import json
from collections import Counter

from arcology.plan import LODS, Element, Plan, element_bounds, element_key, plan_bounds


def _whole(x: float, module: float) -> bool:
    return abs(x / module - round(x / module)) < 1e-6


def _inside(upper: Element, lower: Element) -> bool:
    (ulo, uhi), (llo, lhi) = element_bounds(upper), element_bounds(lower)
    return all(llo[i] - 1e-6 <= ulo[i] and uhi[i] <= lhi[i] + 1e-6 for i in (0, 1))


def _cells(e: Element) -> set[tuple[str, int, int]]:
    """(facade id, bay, floor) cells a window block or entrance fills."""
    if e.kind == "entrance":
        prefix = e.id.rsplit("/", 1)[0]
        (b0, b1), (f0, f1) = e.tags["bays"], e.tags["floors"]
        return {(prefix, b, f) for b in range(b0, b1) for f in range(f0, f1)}
    axes = {a["name"]: a for a in e.array["axes"]}
    bays = range(axes["bay"]["start"], axes["bay"]["start"] + axes["bay"]["count"])
    floors = range(axes["floor"]["start"], axes["floor"]["start"] + axes["floor"]["count"])
    return {(e.array["prefix"], b, f) for b in bays for f in floors}


def _facade_complete(plan: Plan, masses: list[Element]) -> bool:
    """Every bay of every floor of every facade is filled exactly once."""
    expected = set()
    for m in masses:
        floors = range(m.floor, m.floor + round(m.params["height"] / plan.floor_height))
        for side, length in (
            ("south", "width"),
            ("north", "width"),
            ("east", "depth"),
            ("west", "depth"),
        ):
            bays = range(round(m.params[length] / plan.bay_width))
            expected |= {(f"{m.id}/facade.{side}", b, f) for b in bays for f in floors}
    filled: Counter = Counter()
    for e in plan.elements:
        if e.kind in ("window", "entrance"):
            filled.update(_cells(e))
    return set(filled) == expected and all(n == 1 for n in filled.values())


def _symmetric(plan: Plan) -> bool:
    """Bilateral: mirroring the whole plan across x = 0 gives the same set of elements."""

    def signature(e: Element, mirror: bool):
        lo, hi = element_bounds(e)
        x0, x1 = (-hi[0], -lo[0]) if mirror else (lo[0], hi[0])
        box = tuple(round(v, 3) for v in (x0, lo[1], lo[2], x1, hi[1], hi[2]))
        return e.kind, e.recipe, json.dumps(e.params, sort_keys=True), e.count, box

    return Counter(signature(e, False) for e in plan.elements) == Counter(
        signature(e, True) for e in plan.elements
    )


def _entrance(plan: Plan, masses: list[Element]) -> bool:
    entrances = [e for e in plan.elements if e.kind == "entrance"]
    front = f"{masses[0].id}/facade.south/"
    return (
        len(entrances) == 1
        and entrances[0].id.startswith(front)
        and abs(entrances[0].translation[0]) < 1e-6
    )


def lod_counts(plan: Plan) -> dict:
    """Per representation level: unique library meshes and placed copies."""
    return {
        lod: {
            "unique": len({element_key(e, lod) for e in plan.elements if lod in e.lod}),
            "instances": sum(e.count for e in plan.elements if lod in e.lod),
        }
        for lod in LODS
    }


def measure(plan: Plan) -> dict:
    fh, bay = plan.floor_height, plan.bay_width
    masses = sorted((e for e in plan.elements if e.kind == "mass"), key=lambda e: e.translation[2])
    pairs = list(zip(masses, masses[1:], strict=False))
    tower = [e for e in masses if e.tags.get("role") == "tower"]
    lo, hi = plan_bounds(plan)

    def floors(es):
        return sum(round(e.params["height"] / fh) for e in es)

    def steps_on_grid(e: Element) -> bool:
        for axis in e.array["axes"] if e.array else []:
            size = sum(v * v for v in axis["step"]) ** 0.5
            if abs(size - (fh if axis["name"] == "floor" else bay)) > 1e-6:
                return False
        return True

    base = tower[0].params if tower else {"width": 0, "depth": 0}
    tower_height = sum(e.params["height"] for e in tower)
    checks = {
        "floor_aligned": all(_whole(e.translation[2], fh) for e in plan.elements)
        and all(_whole(e.params["height"], fh) for e in masses),
        "bay_aligned": all(
            _whole(e.params["width"], bay) and _whole(e.params["depth"], bay) for e in masses
        )
        and all(steps_on_grid(e) for e in plan.elements),
        "stacked": all(
            abs(a.translation[2] + a.params["height"] - b.translation[2]) < 1e-6 for a, b in pairs
        ),
        "setbacks_monotonic": all(
            b.params["width"] <= a.params["width"] and b.params["depth"] <= a.params["depth"]
            for a, b in pairs
        ),
        "contained": all(_inside(b, a) for a, b in pairs),
        "facade_complete": _facade_complete(plan, masses),
        "symmetric": _symmetric(plan),
        "entrance": _entrance(plan, masses),
    }
    return {
        "height_m": round(hi[2] - lo[2], 2),
        "floors": floors(masses),
        "podium_floors": floors(e for e in masses if e.tags.get("role") == "podium"),
        "tower_floors": floors(tower),
        "footprint_m": [round(hi[0] - lo[0], 2), round(hi[1] - lo[1], 2)],
        "tower_base_m": [base["width"], base["depth"]],
        "slenderness": round(tower_height / min(base["width"], base["depth"]), 2) if tower else 0,
        "windows": sum(e.count for e in plan.elements if e.kind == "window"),
        "lod": lod_counts(plan),
        "checks": checks,
    }


def failures(metrics: dict) -> list[str]:
    return [name for name, ok in metrics["checks"].items() if not ok]
