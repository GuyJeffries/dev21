from dataclasses import replace
from pathlib import Path

import pytest

from arcology.metrics import failures, measure
from arcology.resolve import resolve
from arcology.spec import load_spec

PLAN = resolve(load_spec(Path(__file__).parents[1] / "specs/default.json"))
CENTRAL = "arcology/tower.central"
TOP = f"{CENTRAL}/section.3"
SOUTH = "arcology/podium/tier.0/facade.south"
EAST = "arcology/tower.east.mid/section.0"


def _first(mass, facade, kind, zone=None):
    """The id of the first element of `kind` on a facade (in a zone), found by its tags."""
    return next(
        e.id
        for e in PLAN.elements
        if e.kind == kind
        and e.tags.get("mass") == mass
        and e.tags.get("facade") == facade
        and (zone is None or e.tags.get("zone") == zone)
    )


TIER0 = "arcology/podium/tier.0"
ENTRANCE = _first(TIER0, "south", "entrance")


def _alter(element_id, **changes):
    elements = []
    for e in PLAN.elements:
        if e.id == element_id:
            params = {**e.params, **changes.pop("params", {})}
            e = replace(e, params=params, **changes)
        elements.append(e)
    return replace(PLAN, elements=tuple(elements))


def _widen(element_id, width):
    """Resize a mass the way the resolver would: params and extent together."""
    e = PLAN.element(element_id)
    (_, y0, z0), (_, y1, z1) = e.extent
    extent = ((-width / 2, y0, z0), (width / 2, y1, z1))
    return _alter(element_id, params={"width": width}, extent=extent)


def _taller(element_id, height):
    e = PLAN.element(element_id)
    (x0, y0, z0), (x1, y1, _) = e.extent
    return _alter(element_id, params={"height": height}, extent=((x0, y0, z0), (x1, y1, height)))


def _shift_bridge(dz):
    bridge = PLAN.element("arcology/bridge.east.mid")
    x, y, z = bridge.translation
    return _alter(bridge.id, translation=(x, y + 40.0, z + dz))


def _shift_window_block():
    block = PLAN.element(_first(EAST, "east", "window", "shaft"))
    x, y, z = block.translation
    return _alter(block.id, translation=(x + 3.0, y, z))


def _bridge_into_cornice():
    """The east bridge raised until its roof meets the top of the lower base section."""
    bridge = PLAN.element("arcology/bridge.east.mid")
    tops = [_z(m) + PLAN.element(m).params["height"] for m in (f"{CENTRAL}/section.0", EAST)]
    x, y, _ = bridge.translation
    return _alter(bridge.id, translation=(x, y, min(tops) - bridge.params["height"]))


def _drop(element_id):
    return replace(PLAN, elements=tuple(e for e in PLAN.elements if e.id != element_id))


def _duplicate(element_id):
    return replace(PLAN, elements=(*PLAN.elements, PLAN.element(element_id)))


def _z(element_id):
    return PLAN.element(element_id).translation[2]


def test_resolved_plan_passes_every_check():
    m = measure(PLAN)
    assert failures(m) == []
    assert m["floors"] == m["podium_floors"] + m["tower_floors"]
    assert m["height_m"] == m["floors"] * PLAN.floor_height
    assert m["lod"]["L0"]["instances"] > m["lod"]["L2"]["instances"] > m["lod"]["L3"]["instances"]


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        # Moving the top section also leaves its crown and its facade behind.
        (
            lambda: _alter(TOP, translation=(0.0, 0.0, _z(TOP) + 1)),
            {"floor_aligned", "stacked", "crowned", "dressed", "corniced"},
        ),
        (
            lambda: _alter(TOP, translation=(0.0, 0.0, _z(TOP) + 4)),
            {"stacked", "crowned", "dressed", "corniced"},
        ),
        (
            lambda: _widen(TOP, PLAN.element(TOP).params["width"] + 1),
            {"bay_aligned", "corniced"},
        ),
        (
            lambda: _widen(TOP, 600.0),
            {"setbacks_monotonic", "contained", "facade_complete", "corniced", "tiled"},
        ),
        (
            lambda: _alter(TOP, translation=(30.0, 0.0, _z(TOP))),
            {"contained", "symmetric", "crowned", "dressed", "corniced"},
        ),
        (
            lambda: _drop(_first(TIER0, "south", "window", "shaft")),
            {"facade_complete"},
        ),
        (
            lambda: _duplicate(_first(TIER0, "south", "window", "base")),
            {"facade_complete", "symmetric"},
        ),
        (lambda: _drop(f"{SOUTH}/piers.0"), {"symmetric"}),
        (lambda: _drop(f"{TOP}/cornice"), {"corniced"}),
        (lambda: _duplicate(f"{EAST}/cornice"), {"corniced", "symmetric"}),
        # A sister tower carrying more chevrons than the central tower.
        (
            lambda: _alter(_first(EAST, "east", "window", "capital"), params={"chevrons": 3}),
            {"ornament_hierarchy", "symmetric"},
        ),
        (lambda: _drop(ENTRANCE), {"entrance", "facade_complete"}),
        (
            lambda: _alter(
                ENTRANCE,
                translation=(6.0, *PLAN.element(ENTRANCE).translation[1:]),
            ),
            {"entrance", "symmetric"},
        ),
        (lambda: _drop(f"{CENTRAL}/crown"), {"crowned"}),
        # A sister tower dropped into the central tower: it collides, its bridge no longer
        # meets it, and its facade, floors and mirror twin no longer match.
        (
            lambda: _alter(EAST, floor=0, translation=(0.0, 0.0, 0.0)),
            {
                "clear",
                "connected",
                "contained",
                "dressed",
                "facade_complete",
                "stacked",
                "symmetric",
                "corniced",
                "tiled",
            },
        ),
        (
            lambda: _taller(EAST, 500.0),
            {
                "dominant",
                "facade_complete",
                "stacked",
                "symmetric",
                "corniced",
                "proportioned",
                "tiled",
            },
        ),
        (lambda: _shift_bridge(1.0), {"connected", "floor_aligned", "symmetric"}),
        (lambda: _shift_window_block(), {"dressed", "symmetric"}),
        (lambda: _bridge_into_cornice(), {"clear", "symmetric"}),
    ],
)
def test_each_check_catches_its_fault(broken, expected):
    assert set(failures(measure(broken()))) == expected
