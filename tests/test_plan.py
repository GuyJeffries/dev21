import json
from dataclasses import replace
from pathlib import Path

from arcology.plan import Plan, element_bounds, instances
from arcology.resolve import resolve
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
PLAN = resolve(SPEC)
SOUTH = "arcology/podium/tier.0/facade.south"


def _block(zone):
    """The south face's first window block in `zone`: its left-most panel."""
    return next(
        e
        for e in PLAN.elements
        if e.kind == "window"
        and e.array["prefix"] == SOUTH
        and e.tags["zone"] == zone
        and e.array["axes"][0]["start"] == 0
    )


def _windows(plan):
    return {w.id: w for e in plan.elements if e.kind == "window" for w in instances(plan, e)}


def test_array_copies_have_grid_ids_floors_and_tags():
    block = _block("base")
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


# Without treatments, which take windows out where they fall and set a recess's back.
CALM = replace(SPEC, style=replace(SPEC.style, contrast=0.0))


def test_window_identity_survives_a_different_entrance():
    # A wider entrance re-splits the south facade into different blocks; every window that
    # still exists must keep its id, seed and position.
    narrow = _windows(resolve(replace(CALM, facade=replace(CALM.facade, entrance_bays=3))))
    wide = _windows(resolve(replace(CALM, facade=replace(CALM.facade, entrance_bays=7))))
    assert len(wide) < len(narrow)
    for wid, w in wide.items():
        assert (narrow[wid].seed, narrow[wid].translation) == (w.seed, w.translation), wid


def test_window_identity_survives_a_different_rhythm_and_zones():
    # Pilasters and ornament re-split facades into other blocks and zones (capital floors
    # follow ornament density); every window keeps its id, seed and position.
    before = _windows(resolve(CALM))
    after = _windows(
        resolve(
            replace(
                CALM,
                facade=replace(CALM.facade, pilaster_every=5),
                style=replace(CALM.style, ornament_density=1.0),
            )
        )
    )
    assert after.keys() == before.keys()
    for wid, w in after.items():
        assert (before[wid].seed, before[wid].translation) == (w.seed, w.translation), wid
    assert {w.recipe for w in after.values()} == {w.recipe for w in before.values()}
    assert sum(w.recipe == "window.deco_capital" for w in after.values()) > sum(
        w.recipe == "window.deco_capital" for w in before.values()
    )


def test_strided_arrays_name_copies_by_bay_line():
    block = next(e for e in PLAN.elements if e.id.endswith("/pilasters.0") and e.count > 2)
    axis = block.array["axes"][0]
    copies = list(instances(PLAN, block))
    lines = [axis["start"] + i * axis["stride"] for i in range(axis["count"])]
    assert [c.id for c in copies] == [f"{block.array['prefix']}/pier.{n:03d}" for n in lines]
    assert [c.tags["pier"] for c in copies] == lines
    step = sum(v * v for v in axis["step"]) ** 0.5
    assert step == axis["stride"] * PLAN.bay_width


def test_array_bounds_cover_every_copy():
    block = _block("shaft")
    lo, hi = element_bounds(block)
    for copy in instances(PLAN, block):
        clo, chi = element_bounds(copy)
        assert all(lo[k] <= clo[k] + 1e-9 and chi[k] <= hi[k] + 1e-9 for k in range(3))


def test_plan_with_arrays_round_trips_through_json():
    assert Plan.from_dict(json.loads(PLAN.to_json())) == PLAN
