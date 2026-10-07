"""Structural metrics on a resolved plan, from docs/PLAN.md section 20. Plain Python.

Massing checks walk each stack (the podium tiers; each tower standing on the top tier)
comparing every mass with the one directly below it. Facade checks work on arrays without
expanding them, so they stay fast at 10k+ windows. Composition checks cover dominance,
bridges, crowns and clearance between towers.
"""

import json
import math
from collections import Counter

from arcology.plan import LODS, Element, Plan, element_bounds, element_key, plan_bounds

CENTRAL = "arcology/tower.central"
DOMINANCE = 1.3  # central tower floors / tallest secondary tower's, at least
MAX_SPAN = 30.0  # metres a bridge may span


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


def _stacks(masses: list[Element]) -> list[list[Element]]:
    """Each stack bottom-up: the podium tiers, and each tower on the tier it stands on."""
    podium = sorted((m for m in masses if m.tags.get("role") == "podium"), key=lambda m: m.floor)
    tiers = {m.id: m for m in podium}
    towers: dict[str, list[Element]] = {}
    for m in masses:
        if m.tags.get("role") == "tower":
            towers.setdefault(m.tags["tower"], []).append(m)
    return [podium] + [
        [tiers[ms[0].tags["stands_on"]], *sorted(ms, key=lambda m: m.floor)]
        for ms in towers.values()
    ]


def _overlap(a, b) -> float:
    (alo, ahi), (blo, bhi) = a, b
    return math.prod(max(0.0, min(ahi[i], bhi[i]) - max(alo[i], blo[i])) for i in range(3))


def _clear(plan: Plan, masses: list[Element]) -> bool:
    """No two towers, a tower and the podium, or a bridge and any mass occupy the same
    space; touching (a tower on a terrace, a bridge against a wall) is fine."""
    boxes = [(m.tags.get("tower", "podium"), element_bounds(m)) for m in masses]
    boxes += [(e.id, element_bounds(e)) for e in plan.elements if e.kind == "bridge"]
    return all(
        _overlap(a, b) <= 1e-6
        for i, (owner_a, a) in enumerate(boxes)
        for owner_b, b in boxes[i + 1 :]
        if owner_a != owner_b
    )


def _on_face(point, box, tol=1e-3) -> bool:
    """`point` lies on a vertical face of `box` (within it, and on its x or y boundary)."""
    lo, hi = box
    inside = all(lo[i] - tol <= point[i] <= hi[i] + tol for i in range(3))
    return inside and any(
        abs(point[i] - lo[i]) < tol or abs(point[i] - hi[i]) < tol for i in (0, 1)
    )


def _dressed(plan: Plan, masses: list[Element]) -> bool:
    """Every core, pier and window of a mass lies within that mass's envelope."""
    boxes = {m.id: element_bounds(m) for m in masses}
    for e in plan.elements:
        if e.kind in ("core", "pier", "window"):
            lo, hi = boxes[e.tags["mass"]]
            elo, ehi = element_bounds(e)
            if not all(lo[i] - 1e-3 <= elo[i] and ehi[i] <= hi[i] + 1e-3 for i in range(3)):
                return False
    return True


def _connections(plan: Plan) -> bool:
    """Every bridge runs straight from a face of one mass to a face of another, at one
    floor, within both masses' heights, spanning no more than MAX_SPAN."""
    by_id = {e.id: e for e in plan.elements}
    for b in (e for e in plan.elements if e.kind == "bridge"):
        ends = [by_id.get(b.tags["from"]), by_id.get(b.tags["to"])]
        if any(m is None or m.kind != "mass" for m in ends) or b.params["span"] > MAX_SPAN:
            return False
        a = math.radians(b.rotation_z_deg)
        x, y, z = b.translation
        top = z + b.params["height"]
        far = (x + b.params["span"] * math.sin(a), y - b.params["span"] * math.cos(a), z)
        for point, m in (((x, y, z), ends[0]), (far, ends[1])):
            box = element_bounds(m)
            if not (_on_face(point, box) and box[0][2] <= z and top <= box[1][2]):
                return False
    return True


def _crowned(plan: Plan, stacks: list[list[Element]]) -> bool:
    """Every tower ends in exactly one crown, sitting on its top section."""
    crowns = [e for e in plan.elements if e.kind == "crown"]
    for stack in stacks[1:]:
        top = stack[-1]
        mine = [c for c in crowns if c.tags.get("tower") == top.tags["tower"]]
        if len(mine) != 1:
            return False
        (clo, chi), (tlo, thi) = element_bounds(mine[0]), element_bounds(top)
        if abs(clo[2] - thi[2]) > 1e-6 or not all(
            tlo[i] - 1e-6 <= clo[i] and chi[i] <= thi[i] + 1e-6 for i in (0, 1)
        ):
            return False
    return True


def measure(plan: Plan) -> dict:
    fh, bay = plan.floor_height, plan.bay_width
    masses = [e for e in plan.elements if e.kind == "mass"]
    stacks = _stacks(masses)
    pairs = [(a, b) for stack in stacks for a, b in zip(stack, stack[1:], strict=False)]
    central = [m for m in masses if m.tags.get("tower") == CENTRAL]
    secondary: dict[str, int] = {}
    for m in masses:
        if m.tags.get("role") == "tower" and m.tags["tower"] != CENTRAL:
            secondary[m.tags["tower"]] = secondary.get(m.tags["tower"], 0) + round(
                m.params["height"] / fh
            )
    lo, hi = plan_bounds(plan)
    tip = max(element_bounds(e)[1][2] for e in plan.elements)

    def floors(es):
        return sum(round(e.params["height"] / fh) for e in es)

    def steps_on_grid(e: Element) -> bool:
        for axis in e.array["axes"] if e.array else []:
            size = sum(v * v for v in axis["step"]) ** 0.5
            if abs(size - (fh if axis["name"] == "floor" else bay)) > 1e-6:
                return False
        return True

    base = central[0].params if central else {"width": 0, "depth": 0}
    tower_floors = floors(central)
    dominance = round(tower_floors / max(secondary.values()), 2) if secondary else None
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
        "dressed": _dressed(plan, masses),
        "symmetric": _symmetric(plan),
        "entrance": _entrance(plan, stacks[0]),
        "dominant": dominance is None or dominance >= DOMINANCE,
        "connected": _connections(plan),
        "crowned": _crowned(plan, stacks),
        "clear": _clear(plan, masses),
    }
    return {
        "height_m": round(hi[2] - lo[2], 2),
        "tip_m": round(tip, 1),
        "floors": tower_floors + floors(stacks[0]),
        "podium_floors": floors(stacks[0]),
        "tower_floors": tower_floors,
        "towers": len(secondary),
        "dominance": dominance,
        "footprint_m": [round(hi[0] - lo[0], 2), round(hi[1] - lo[1], 2)],
        "tower_base_m": [base["width"], base["depth"]],
        "slenderness": round(floors(central) * fh / min(base["width"], base["depth"]), 2)
        if central
        else 0,
        "windows": sum(e.count for e in plan.elements if e.kind == "window"),
        "lod": lod_counts(plan),
        "checks": checks,
    }


def failures(metrics: dict) -> list[str]:
    return [name for name, ok in metrics["checks"].items() if not ok]
