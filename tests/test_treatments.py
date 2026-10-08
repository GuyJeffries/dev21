"""Treatments (docs/LAYERS.md, step 3): luxury leaves take exceptions where composition puts
them, as many as `contrast` asks; cuts carve a space into the core; the checks catch a
treatment in the wrong place or a space with nothing carved behind it."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
from statistics import median

import pytest

from arcology.facade import CUTS, TREATMENTS
from arcology.metrics import failures, layers, measure
from arcology.plan import instances
from arcology.resolve import resolve
from arcology.rules import CENTRAL, carve
from arcology.spec import load_spec, spec_with

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
PLAN = resolve(replace(SPEC, seed=37))
SEEDS = range(12)


def _exceptions(spec):
    return [layers(resolve(replace(spec, seed=s)))["exceptions"]["building"] for s in SEEDS]


def test_contrast_sets_how_many_luxury_places_take_an_exception():
    none, some, every = (_exceptions(spec_with(SPEC, "style.contrast", c)) for c in (0.0, 0.5, 1.0))
    assert max(none) == 0
    assert 0 < median(some) < median(every)


def test_every_treatment_is_used_and_only_on_luxury_leaves():
    seen = Counter()
    for style in ({}, {"dominant_axis": "horizontal"}):
        for seed in SEEDS:
            plan = resolve(replace(SPEC, seed=seed, style=replace(SPEC.style, **style)))
            for r in plan.regions:
                if r.treatment in TREATMENTS:
                    assert r.tags["grade"] == "luxury", r.id
                    seen[r.treatment] += 1
    assert set(seen) == set(TREATMENTS)


def test_the_spec_can_allow_fewer_treatments():
    spec = spec_with(spec_with(SPEC, "facade.treatments", ["field"]), "style.contrast", 1.0)
    plan = resolve(replace(spec, seed=37))
    assert {r.treatment for r in plan.regions if r.treatment} == {"cells", "portal", "field"}
    assert failures(measure(plan)) == []


def test_the_central_tower_always_expresses_its_axis():
    for seed in SEEDS:
        plan = resolve(replace(SPEC, seed=seed))
        assert any(
            r.treatment in TREATMENTS and r.tags["column"] == "axis"
            for r in plan.regions
            if r.mass.startswith(CENTRAL)
        ), seed


def test_twins_take_the_same_treatments_unless_asymmetric():
    def treated(plan, tower):
        return Counter(
            (r.treatment, r.tags["course"], r.tags["column"])
            for r in plan.regions
            if f"/{tower}/" in r.id and r.treatment in TREATMENTS
        )

    differ = 0
    for seed in SEEDS:
        plan = resolve(replace(SPEC, seed=seed))
        assert treated(plan, "tower.east.mid") == treated(plan, "tower.west.mid"), seed
        free = resolve(replace(spec_with(SPEC, "style.symmetry", "none"), seed=seed))
        differ += treated(free, "tower.east.mid") != treated(free, "tower.west.mid")
    assert differ


def test_cuts_carve_the_core_and_house_a_space():
    cut = [r for r in PLAN.regions if r.treatment in CUTS]
    assert {r.treatment for r in cut} == set(CUTS)
    cores = {e.tags["mass"]: e for e in PLAN.elements if e.kind == "core"}
    for mass in {r.mass for r in cut}:
        assert len(cores[mass].params["cuts"]) == sum(r.mass == mass for r in cut)
    halls = [e for e in PLAN.elements if e.kind == "space" and e.tags["program"] == "hall"]
    assert halls and all(e.lod for e in halls)  # lit, seen through the opening's glass
    terraces = [e for e in PLAN.elements if e.kind == "space" and e.tags["program"] == "terrace"]
    assert terraces and not any(e.lod for e in terraces)  # open air: nothing to draw
    # A core left whole behind its openings and recesses leaves the spaces solid.
    mass = cut[0].mass
    whole = replace(
        cores[mass], params={k: v for k, v in cores[mass].params.items() if k != "cuts"}
    )
    plan = replace(PLAN, elements=tuple(whole if e is cores[mass] else e for e in PLAN.elements))
    assert failures(measure(plan)) == ["housed"]


def test_a_recess_sets_its_back_wall_back_and_keeps_its_window_ids():
    leaf = next(r for r in PLAN.regions if r.treatment == "recess")
    calm = resolve(replace(spec_with(SPEC, "style.contrast", 0.0), seed=37))

    def windows(plan):  # the window copies in the leaf's bays and floors
        return {
            c.id: c
            for e in plan.elements
            if e.kind == "window" and (e.tags["mass"], e.tags["facade"]) == (leaf.mass, leaf.facade)
            for c in instances(plan, e)
            if leaf.bays[0] <= c.tags["bay"] < leaf.bays[1]
            and leaf.floors[0] <= c.floor < leaf.floors[1]
        }

    back, front = windows(PLAN), windows(calm)
    assert back.keys() == front.keys() and back
    depth = leaf.tags["depth"] - facade_depth(PLAN, leaf)
    for wid, w in back.items():
        moved = [abs(a - b) for a, b in zip(w.translation, front[wid].translation, strict=True)]
        assert max(moved) == pytest.approx(depth, abs=1e-3) and moved[2] == 0, wid


def facade_depth(plan, leaf):
    """Envelope to core on `leaf`'s mass: half the difference of the mass's and core's widths."""
    mass = plan.element(leaf.mass)
    core = plan.element(f"{leaf.mass}/core")
    return (mass.params["width"] - core.params["width"]) / 2


def test_slots_wait_on_the_axis_in_fields():
    slots = [e for e in PLAN.elements if e.kind == "asset_slot"]
    assert slots and all(e.lod == () for e in slots)  # empty until assets exist
    by_id = {r.id: r for r in PLAN.regions}
    for e in slots:
        (rid,) = e.tags["regions"]
        assert by_id[rid].treatment == "field" and by_id[rid].tags["column"] == "axis"
        field = PLAN.element(e.id.removesuffix("/slot"))
        assert field.params["niche"][:2] == [e.params["width"], e.params["height"]]
        low = (
            by_id[rid].tags["course"] == "capital"
            or by_id[rid].floors[1] - by_id[rid].floors[0] < 3
        )
        assert e.tags["slot"] == ("relief" if low else "figure")


def test_composed_catches_an_exception_out_of_place():
    functional = next(
        r for r in PLAN.regions if r.treatment == "cells" and r.tags["grade"] == "functional"
    )
    regions = tuple(replace(r, treatment="field") if r is functional else r for r in PLAN.regions)
    assert "composed" in failures(measure(replace(PLAN, regions=regions)))


@pytest.mark.parametrize(
    ("box", "cuts"),
    [
        (((0, 0, 0), (10, 10, 10)), [((2, -1, 2), (4, 3, 5))]),  # a bite from one face
        (((0, 0, 0), (10, 10, 10)), [((2, 2, 2), (4, 4, 4)), ((3, 3, 3), (12, 5, 6))]),
        (((0, 0, 0), (10, 10, 10)), [((20, 20, 20), (30, 30, 30))]),  # misses
    ],
)
def test_carve_tiles_what_is_left(box, cuts):
    def volume(b):
        (x0, y0, z0), (x1, y1, z1) = b
        return max(0, x1 - x0) * max(0, y1 - y0) * max(0, z1 - z0)

    def clip(b, c):
        return (
            tuple(max(b[0][i], c[0][i]) for i in range(3)),
            tuple(min(b[1][i], c[1][i]) for i in range(3)),
        )

    pieces = carve(box, cuts)
    removed = sum(volume(clip(box, c)) for c in cuts)
    if len(cuts) == 2:  # the two cuts overlap
        removed -= volume(clip(clip(box, cuts[0]), cuts[1]))
    assert sum(map(volume, pieces)) == pytest.approx(volume(box) - removed)
    for i, a in enumerate(pieces):
        assert all(volume(clip(a, c)) == 0 for c in cuts)
        assert all(volume(clip(a, b)) == 0 for b in pieces[i + 1 :])
