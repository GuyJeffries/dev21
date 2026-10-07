import json
from dataclasses import replace
from pathlib import Path

from arcology.plan import Plan, element_bounds, instances
from arcology.resolve import resolve
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
PLAN = resolve(SPEC)
SOUTH = "arcology/podium/tier.0/facade.south"


def _windows(plan):
    return {w.id: w for e in plan.elements if e.kind == "window" for w in instances(plan, e)}


def test_array_copies_have_grid_ids_floors_and_tags():
    block = PLAN.element(f"{SOUTH}/windows.left")
    copies = list(instances(PLAN, block))
    assert len(copies) == block.count
    first, last = copies[0], copies[-1]
    assert first.id == f"{SOUTH}/bay.000/floor.000"
    assert (first.tags["facade"], first.tags["bay"], first.tags["floor"]) == ("south", 0, 0)
    bays, floors = (a["count"] for a in block.array["axes"])
    assert last.id == f"{SOUTH}/bay.{bays - 1:03d}/floor.{floors - 1:03d}"
    assert last.floor == floors - 1
    assert last.translation[2] == (floors - 1) * PLAN.floor_height
    assert last.translation[0] == first.translation[0] + (bays - 1) * PLAN.bay_width
    assert all(c.array is None for c in copies)


def test_window_ids_and_seeds_are_unique():
    windows = _windows(PLAN)
    assert len(windows) == sum(e.count for e in PLAN.elements if e.kind == "window")
    assert len({w.seed for w in windows.values()}) == len(windows)


def test_window_identity_survives_a_different_entrance():
    # A wider entrance re-splits the south facade into different blocks; every window that
    # still exists must keep its id, seed and position.
    narrow = _windows(resolve(replace(SPEC, facade=replace(SPEC.facade, entrance_bays=3))))
    wide = _windows(resolve(replace(SPEC, facade=replace(SPEC.facade, entrance_bays=7))))
    assert len(wide) < len(narrow)
    for wid, w in wide.items():
        assert (narrow[wid].seed, narrow[wid].translation) == (w.seed, w.translation), wid


def test_array_bounds_cover_every_copy():
    block = PLAN.element(f"{SOUTH}/windows.left")
    lo, hi = element_bounds(block)
    for copy in instances(PLAN, block):
        clo, chi = element_bounds(copy)
        assert all(lo[k] <= clo[k] + 1e-9 and chi[k] <= hi[k] + 1e-9 for k in range(3))


def test_plan_with_arrays_round_trips_through_json():
    assert Plan.from_dict(json.loads(PLAN.to_json())) == PLAN
