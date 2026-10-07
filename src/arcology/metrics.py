"""Structural metrics on a resolved plan, from docs/PLAN.md section 20. Plain Python.

Phase 0 has a single stack (podium tiers, then tower sections), so the stacking checks
compare each mass with the one directly below it. Later phases add dominance,
connection validity, symmetry and termination.
"""

from arcology.plan import Element, Plan, element_bounds, plan_bounds


def _whole(x: float, module: float) -> bool:
    return abs(x / module - round(x / module)) < 1e-6


def _inside(upper: Element, lower: Element) -> bool:
    (ulo, uhi), (llo, lhi) = element_bounds(upper), element_bounds(lower)
    return all(llo[i] - 1e-6 <= ulo[i] and uhi[i] <= lhi[i] + 1e-6 for i in (0, 1))


def measure(plan: Plan) -> dict:
    fh, bay = plan.floor_height, plan.bay_width
    masses = sorted((e for e in plan.elements if e.kind == "mass"), key=lambda e: e.translation[2])
    pairs = list(zip(masses, masses[1:], strict=False))
    tower = [e for e in masses if e.tags.get("role") == "tower"]
    lo, hi = plan_bounds(plan)

    def floors(es):
        return sum(round(e.params["height"] / fh) for e in es)

    base = tower[0].params if tower else {"width": 0, "depth": 0}
    tower_height = sum(e.params["height"] for e in tower)
    checks = {
        "floor_aligned": all(
            _whole(e.translation[2], fh) and _whole(e.params["height"], fh) for e in masses
        ),
        "bay_aligned": all(
            _whole(e.params["width"], bay) and _whole(e.params["depth"], bay) for e in masses
        ),
        "stacked": all(
            abs(a.translation[2] + a.params["height"] - b.translation[2]) < 1e-6 for a, b in pairs
        ),
        "setbacks_monotonic": all(
            b.params["width"] <= a.params["width"] and b.params["depth"] <= a.params["depth"]
            for a, b in pairs
        ),
        "contained": all(_inside(b, a) for a, b in pairs),
    }
    return {
        "height_m": round(hi[2] - lo[2], 2),
        "floors": floors(masses),
        "podium_floors": floors(e for e in masses if e.tags.get("role") == "podium"),
        "tower_floors": floors(tower),
        "footprint_m": [round(hi[0] - lo[0], 2), round(hi[1] - lo[1], 2)],
        "tower_base_m": [base["width"], base["depth"]],
        "slenderness": round(tower_height / min(base["width"], base["depth"]), 2) if tower else 0,
        "checks": checks,
    }


def failures(metrics: dict) -> list[str]:
    return [name for name, ok in metrics["checks"].items() if not ok]
