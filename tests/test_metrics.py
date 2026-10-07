from dataclasses import replace
from pathlib import Path

import pytest

from arcology.metrics import failures, measure
from arcology.resolve import resolve
from arcology.spec import load_spec

PLAN = resolve(load_spec(Path(__file__).parents[1] / "specs/default.json"))
TOP = "arcology/tower.central/section.3"
SOUTH = "arcology/podium/tier.0/facade.south"


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
        (lambda: _alter(TOP, translation=(0.0, 0.0, _z(TOP) + 1)), {"floor_aligned", "stacked"}),
        (lambda: _alter(TOP, translation=(0.0, 0.0, _z(TOP) + 4)), {"stacked"}),
        (lambda: _widen(TOP, PLAN.element(TOP).params["width"] + 1), {"bay_aligned"}),
        (
            lambda: _widen(TOP, 600.0),
            {"setbacks_monotonic", "contained", "facade_complete"},
        ),
        (lambda: _alter(TOP, translation=(30.0, 0.0, _z(TOP))), {"contained", "symmetric"}),
        (lambda: _drop(f"{SOUTH}/windows.above"), {"facade_complete"}),
        (lambda: _duplicate(f"{SOUTH}/windows.left"), {"facade_complete", "symmetric"}),
        (
            lambda: _drop(f"{SOUTH}/piers.left"),
            {"symmetric"},
        ),
        (lambda: _drop(f"{SOUTH}/entrance"), {"entrance", "facade_complete"}),
        (
            lambda: _alter(
                f"{SOUTH}/entrance",
                translation=(6.0, *PLAN.element(f"{SOUTH}/entrance").translation[1:]),
            ),
            {"entrance", "symmetric"},
        ),
    ],
)
def test_each_check_catches_its_fault(broken, expected):
    assert set(failures(measure(broken()))) == expected
