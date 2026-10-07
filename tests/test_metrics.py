from dataclasses import replace
from pathlib import Path

import pytest

from arcology.metrics import failures, measure
from arcology.resolve import resolve
from arcology.spec import load_spec

PLAN = resolve(load_spec(Path(__file__).parents[1] / "specs/default.json"))
TOP = len(PLAN.elements) - 1


def _alter(index, **changes):
    e = PLAN.elements[index]
    params = {**e.params, **changes.pop("params", {})}
    elements = list(PLAN.elements)
    elements[index] = replace(e, params=params, **changes)
    return replace(PLAN, elements=tuple(elements))


def test_resolved_plan_passes_every_check():
    m = measure(PLAN)
    assert failures(m) == []
    assert m["floors"] == m["podium_floors"] + m["tower_floors"]
    assert m["height_m"] == m["floors"] * PLAN.floor_height


@pytest.mark.parametrize(
    ("broken", "expected"),
    [
        (
            lambda: _alter(TOP, translation=(0.0, 0.0, PLAN.elements[TOP].translation[2] + 1)),
            {"floor_aligned", "stacked"},
        ),
        (
            lambda: _alter(TOP, translation=(0.0, 0.0, PLAN.elements[TOP].translation[2] + 4)),
            {"stacked"},
        ),
        (
            lambda: _alter(TOP, params={"width": PLAN.elements[TOP].params["width"] + 1}),
            {"bay_aligned"},
        ),
        (lambda: _alter(TOP, params={"width": 600.0}), {"setbacks_monotonic", "contained"}),
        (
            lambda: _alter(TOP, translation=(30.0, 0.0, PLAN.elements[TOP].translation[2])),
            {"contained"},
        ),
    ],
)
def test_each_check_catches_its_fault(broken, expected):
    assert set(failures(measure(broken()))) == expected
