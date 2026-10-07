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
from arcology.rules import CENTRAL, HIERARCHY, in_outline, outline, standing

MAX_SPAN = 30.0  # metres a bridge may span
RANKING = ("central", "sister", "pavilion")  # ornament must not increase down this order

# Style envelope (Phase 4): outside these a building drifts from Art Deco, towards a needle
# or spike (Gothic, fantasy), a slab with no setbacks, a tower with no base, or ornament
# turned to noise.
SLENDERNESS = (2.0, 8.0)  # central tower height over its base's narrower side
TAPER = (0.25, 0.95)  # its top section's narrower side over its base's: it steps back
PODIUM_SHARE = (0.08, 0.45)  # podium floors as a share of all floors
SPIRE_SHARE = 0.25  # at most this share of the central tower's height
ORNAMENT_CAP = 2.5  # ornament pieces per facade cell, on any standing


def _whole(x: float, module: float) -> bool:
    return abs(x / module - round(x / module)) < 1e-6


def _within(px: float, py: float, m: Element) -> bool:
    """Whether the world point (px, py) lies within mass `m`'s outline (notches excluded)."""
    x, y, _ = m.translation
    p = m.params
    return in_outline(px - x, py - y, p["width"], p["depth"], p.get("notch", 0.0), tol=1e-6)


def _inside(upper: Element, lower: Element) -> bool:
    """Every vertex of the upper mass's outline lies within the lower mass's outline."""
    x, y, _ = upper.translation
    p = upper.params
    corners = [e.b for e in outline(p["width"], p["depth"], p.get("notch", 0.0))]
    return all(_within(x + cx, y + cy, lower) for cx, cy in corners)


def _cells(e: Element) -> set[tuple[str, int, int]]:
    """(facade id, bay, floor) cells a window block or entrance fills."""
    if e.kind in ("entrance", "door"):
        prefix = e.id.rsplit("/", 1)[0]
        (b0, b1), (f0, f1) = e.tags["bays"], e.tags["floors"]
        return {(prefix, b, f) for b in range(b0, b1) for f in range(f0, f1)}
    axes = {a["name"]: a for a in e.array["axes"]}
    bays = range(axes["bay"]["start"], axes["bay"]["start"] + axes["bay"]["count"])
    floors = range(axes["floor"]["start"], axes["floor"]["start"] + axes["floor"]["count"])
    return {(e.array["prefix"], b, f) for b in bays for f in floors}


def _facade_complete(plan: Plan, masses: list[Element]) -> bool:
    """Every bay of every floor of every facade (one per outline edge) is filled exactly once."""
    expected = set()
    for m in masses:
        floors = range(m.floor, m.floor + round(m.params["height"] / plan.floor_height))
        for edge in outline(m.params["width"], m.params["depth"], m.params.get("notch", 0.0)):
            bays = range(round(edge.length / plan.bay_width))
            expected |= {(f"{m.id}/facade.{edge.name}", b, f) for b in bays for f in floors}
    filled: Counter = Counter()
    for e in plan.elements:
        if e.kind in ("window", "entrance", "door"):
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
    """No two towers, a tower and the podium, or a bridge and any mass or cornice occupy
    the same space; touching (a tower on a terrace, a bridge against a wall) is fine."""
    owner = {m.id: m.tags.get("tower", "podium") for m in masses}
    boxes = [(owner[m.id], element_bounds(m)) for m in masses]
    boxes += [
        (owner[e.tags["mass"]], element_bounds(e)) for e in plan.elements if e.kind == "cornice"
    ]
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
    """Every core, pier, window and channel of a mass lies within that mass's envelope."""
    boxes = {m.id: element_bounds(m) for m in masses}
    for e in plan.elements:
        if e.kind in ("core", "pier", "window", "channel"):
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
        across = (math.cos(a) * b.params["width"] / 2, math.sin(a) * b.params["width"] / 2)
        for point, m in (((x, y, z), ends[0]), (far, ends[1])):
            box = element_bounds(m)
            if not (_on_face(point, box) and box[0][2] <= z and top <= box[1][2]):
                return False
            # Both edges of the deck meet the wall, not a notch beside it.
            for side in (1, -1):
                if not _within(point[0] + side * across[0], point[1] + side * across[1], m):
                    return False
    return True


def _corniced(plan: Plan, masses: list[Element]) -> bool:
    """Every mass has one cornice, following its outline, in its top floor."""
    cornices: dict[str, list[Element]] = {}
    for e in plan.elements:
        if e.kind == "cornice":
            cornices.setdefault(e.tags["mass"], []).append(e)
    for m in masses:
        mine = cornices.get(m.id, [])
        if len(mine) != 1:
            return False
        p, q = mine[0].params, m.params
        if (p["width"], p["depth"], p.get("notch", 0)) != (
            q["width"],
            q["depth"],
            q.get("notch", 0),
        ):
            return False
        top = m.translation[2] + q["height"]
        if (
            abs(element_bounds(mine[0])[1][2] - top) > 1e-6
            or mine[0].translation[:2] != m.translation[:2]
        ):
            return False
    return True


def ornament(plan: Plan, masses: list[Element]) -> dict[str, float]:
    """Ornament per facade cell (bay x floor), by standing: chevrons on windows, flutes on
    piers (for every floor they rise through), and merlons."""
    fh, bay = plan.floor_height, plan.bay_width
    of = {m.id: standing(m) for m in masses}
    cells: Counter = Counter()
    for m in masses:
        edges = outline(m.params["width"], m.params["depth"], m.params.get("notch", 0.0))
        cells[of[m.id]] += round(m.params["height"] / fh) * sum(
            round(e.length / bay) for e in edges
        )
    pieces: Counter = Counter()
    for e in plan.elements:
        if e.tags.get("mass") not in of:
            continue
        if e.kind == "window":
            pieces[of[e.tags["mass"]]] += e.params.get("chevrons", 0) * e.count
        elif e.kind == "pier":
            floors = round(e.params["height"] / fh)
            pieces[of[e.tags["mass"]]] += e.params.get("flutes", 0) * e.count * floors
        elif e.kind == "merlon":
            pieces[of[e.tags["mass"]]] += e.count
    return {s: round(pieces[s] / cells[s], 4) for s in sorted(cells)}


def _ornament_hierarchy(plan: Plan, masses: list[Element]) -> bool:
    """No standing carries an ornament system more richly than the standing above it, down
    the RANKING: the most chevrons on a capital window, fluted pilasters, and merlons on
    parapets. A system is compared only where both standings have somewhere to carry it
    (capital windows, pilasters, parapets over pilasters). Per-cell density (`ornament`)
    varies with how many pilasters fit a facade, so it is reported rather than checked."""
    of = {m.id: standing(m) for m in masses}
    ids = {e.id for e in plan.elements}
    pilastered = {e.tags["mass"] for e in plan.elements if e.tags.get("order") == "pilaster"}
    level: dict[tuple[str, str], int] = {}  # (standing, system) -> richest, where carried

    def carry(s, system, value):
        level[s, system] = max(level.get((s, system), 0), value)

    for m in masses:
        if m.id in pilastered and f"{m.id}/parapet" in ids:
            carry(of[m.id], "merlons", 0)
    for e in plan.elements:
        s = of.get(e.tags.get("mass"))
        if s is None:
            continue
        if e.kind == "window" and e.tags.get("zone") == "capital":
            carry(s, "chevrons", e.params.get("chevrons", 0))
        elif e.tags.get("order") == "pilaster":
            carry(s, "flutes", e.params.get("flutes", 0))
        elif e.kind == "merlon":
            carry(s, "merlons", 1)
    ranked = [s for s in RANKING if s in of.values()]
    return all(
        level[a, system] >= level[b, system]
        for a, b in zip(ranked, ranked[1:], strict=False)
        for system in ("chevrons", "flutes", "merlons")
        if (a, system) in level and (b, system) in level
    )


def _crowned(plan: Plan, stacks: list[list[Element]]) -> bool:
    """Every tower ends in exactly one crown, sitting on its top section: a ring (a flat
    termination) following its outline, or stepped tiers within it."""
    crowns = [e for e in plan.elements if e.kind == "crown"]
    for stack in stacks[1:]:
        top = stack[-1]
        mine = [c for c in crowns if c.tags.get("tower") == top.tags["tower"]]
        if len(mine) != 1:
            return False
        (clo, chi), (_, thi) = element_bounds(mine[0]), element_bounds(top)
        if "rings" in mine[0].params:
            p, q = mine[0].params, top.params
            within = mine[0].translation[:2] == top.translation[:2] and (
                p["width"],
                p["depth"],
                p.get("notch", 0),
            ) == (q["width"], q["depth"], q.get("notch", 0))
        else:
            corners = [(x, y) for x in (clo[0], chi[0]) for y in (clo[1], chi[1])]
            within = all(_within(x, y, top) for x, y in corners)
        if abs(clo[2] - thi[2]) > 1e-6 or not within:
            return False
    return True


def _style(plan: Plan, central, towers, tower_floors: int, podium_floors: int) -> dict:
    """The proportions the style envelope bounds (see SLENDERNESS and the rest)."""

    def slender(sections):
        height = sum(s.params["height"] for s in sections)
        return height / min(sections[0].params["width"], sections[0].params["depth"])

    narrow = [min(s.params["width"], s.params["depth"]) for s in central]
    spires = [e for e in plan.elements if e.kind == "crown" and e.params.get("spire_height", 0) > 0]
    height = sum(s.params["height"] for s in central)
    secondary = [slender(stack[1:]) for stack in towers if stack[1].tags["tower"] != CENTRAL]
    return {
        "slenderness": round(slender(central), 2) if central else 0.0,
        "secondary_slenderness": round(max(secondary, default=0.0), 2),
        "taper": round(narrow[-1] / narrow[0], 2) if central else 0.0,
        "podium_share": round(podium_floors / max(1, podium_floors + tower_floors), 3),
        "spires": len(spires),
        "spire_share": round(
            max((e.params["spire_height"] / height for e in spires), default=0.0), 3
        )
        if central
        else 0.0,
    }


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
        """Array steps are whole floors or whole bays, matching the axis's stride."""
        for axis in e.array["axes"] if e.array else []:
            size = sum(v * v for v in axis["step"]) ** 0.5
            unit = fh if axis["name"] == "floor" else bay
            if abs(size - unit * axis.get("stride", 1)) > 1e-6:
                return False
        return True

    base = central[0].params if central else {"width": 0, "depth": 0}
    tower_floors = floors(central)
    style = _style(plan, central, stacks[1:], tower_floors, floors(stacks[0]))
    density = ornament(plan, masses)
    dominance = round(tower_floors / max(secondary.values()), 2) if secondary else None
    checks = {
        "floor_aligned": all(_whole(e.translation[2], fh) for e in plan.elements)
        and all(_whole(e.params["height"], fh) for e in masses),
        "bay_aligned": all(
            _whole(e.params["width"], bay)
            and _whole(e.params["depth"], bay)
            and _whole(e.params.get("notch", 0.0), bay)
            for e in masses
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
        "corniced": _corniced(plan, masses),
        "ornament_hierarchy": _ornament_hierarchy(plan, masses),
        # Mirror symmetry is only required of bilateral styles.
        "symmetric": plan.style.get("symmetry", "bilateral") != "bilateral" or _symmetric(plan),
        "entrance": _entrance(plan, stacks[0]),
        "dominant": dominance is None
        or dominance >= HIERARCHY[plan.style.get("hierarchy", "strong")].dominance,
        "connected": _connections(plan),
        "crowned": _crowned(plan, stacks),
        "clear": _clear(plan, masses),
        # The style envelope.
        "proportioned": SLENDERNESS[0] <= style["slenderness"] <= SLENDERNESS[1]
        and style["secondary_slenderness"] <= style["slenderness"] + 1e-6,
        "tapered": TAPER[0] <= style["taper"] <= TAPER[1],
        "grounded": PODIUM_SHARE[0] <= style["podium_share"] <= PODIUM_SHARE[1],
        "restrained": style["spires"] <= 1
        and style["spire_share"] <= SPIRE_SHARE
        and max(density.values()) <= ORNAMENT_CAP,
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
        "slenderness": style["slenderness"],
        "style": style,
        "windows": sum(e.count for e in plan.elements if e.kind == "window"),
        "ornament": density,
        "lod": lod_counts(plan),
        "checks": checks,
    }


def failures(metrics: dict) -> list[str]:
    return [name for name, ok in metrics["checks"].items() if not ok]
