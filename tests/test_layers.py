"""The layer tree (docs/LAYERS.md): every face splits into panels and bands, its leaves tile
it, and the elements filling a leaf name it (step 1); bands follow courses on one rhythm, and
every leaf is graded luxury or functional by composition (step 2)."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from arcology.elevation import FILLS, elevation_sheet, leaf_kind
from arcology.facade import MIN_RUN, courses, facade_system, pilaster_lines
from arcology.metrics import failures, layers, measure
from arcology.plan import Plan, instances
from arcology.resolve import resolve
from arcology.rules import CENTRAL
from arcology.spec import load_spec, spec_with

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
PLAN = resolve(SPEC)
SOUTH = "arcology/podium/tier.0/facade.south"


def _children(plan, rid):
    return [r for r in plan.regions if r.parent == rid]


def _leaves(plan, face):
    return [r for r in plan.regions if r.treatment and r.id.startswith(face + "/")]


def test_vertical_faces_split_into_columns_at_pilasters_and_portal_edges():
    face = next(r for r in PLAN.regions if r.id == SOUTH)
    panels = _children(PLAN, SOUTH)
    assert {p.layer for p in panels} == {"panel"}
    entrance = next(e for e in PLAN.elements if e.kind == "entrance")
    a, b = entrance.tags["bays"]
    n = face.bays[1]
    k = facade_system(SPEC).pilaster_every
    major = {line for line in pilaster_lines(n, k) if not a < line < b}
    cuts = sorted({0, n, a, b, *major})
    assert [p.bays for p in sorted(panels, key=lambda p: p.bays)] == list(
        zip(cuts, cuts[1:], strict=False)
    )
    # Every panel runs the face's full height and splits into bands.
    for panel in panels:
        assert panel.floors == face.floors
        assert {c.layer for c in _children(PLAN, panel.id)} == {"band"}


def test_the_portal_is_a_leaf_and_the_bands_follow_the_zones():
    entrance = next(e for e in PLAN.elements if e.kind == "entrance")
    (rid,) = entrance.tags["regions"]
    leaf = next(r for r in PLAN.regions if r.id == rid)
    assert leaf.treatment == "portal"
    assert (list(leaf.bays), list(leaf.floors)) == (entrance.tags["bays"], entrance.tags["floors"])
    roles = {r.tags["role"] for r in _leaves(PLAN, SOUTH)}
    assert roles == {"base", "shaft", "capital", "portal"}


def test_horizontal_faces_split_into_bands_first():
    plan = resolve(replace(SPEC, style=replace(SPEC.style, dominant_axis="horizontal")))
    assert {r.layer for r in _children(plan, SOUTH)} == {"band"}
    # Only bands the portal sits in split into panels; the rest run the full width.
    for band in _children(plan, SOUTH):
        if band.treatment is None:
            assert {c.treatment for c in _children(plan, band.id)} >= {"portal", "cells"}
        else:
            assert band.bays == (0, next(r for r in plan.regions if r.id == SOUTH).bays[1])
    assert failures(measure(plan)) == []


def test_region_ids_are_positions_that_survive_changes_below():
    leaf = next(r for r in PLAN.regions if r.treatment and r.mass.endswith("section.0"))
    assert leaf.id.endswith(f"/panel.{leaf.bays[0]:03d}/band.{leaf.floors[0] - _foot(leaf):03d}")
    taller = resolve(replace(SPEC, primary_mass=replace(SPEC.primary_mass, tiers=(9, 9, 9))))

    def tower(plan):
        central = "arcology/tower.central"
        return {(r.id, r.bays, r.treatment) for r in plan.regions if r.mass.startswith(central)}

    assert tower(taller) == tower(PLAN)


def _foot(region):
    return PLAN.element(region.mass).floor


def test_every_window_lies_within_the_leaves_it_names():
    by_id = {r.id: r for r in PLAN.regions}
    for e in PLAN.elements:
        if e.kind not in ("window", "channel"):
            continue
        leaves = [by_id[rid] for rid in e.tags["regions"]]
        for copy in instances(PLAN, e):
            if e.kind == "window":
                assert any(
                    r.bays[0] <= copy.tags["bay"] < r.bays[1]
                    and r.floors[0] <= copy.floor < r.floors[1]
                    for r in leaves
                ), e.id


def test_layer_numbers_add_up():
    stats = layers(PLAN)
    assert stats["regions"]["face"] == len(
        {(r.mass, r.facade) for r in PLAN.regions if r.layer == "face"}
    )
    assert sum(stats["area"].values()) == pytest.approx(1.0, abs=1e-3)
    assert stats["leaves"] == sum(1 for r in PLAN.regions if r.treatment)


def _without(plan, rid):
    return replace(plan, regions=tuple(r for r in plan.regions if r.id != rid))


@pytest.mark.parametrize(
    "broken",
    [
        lambda: _without(PLAN, next(r.id for r in PLAN.regions if r.treatment)),  # a hole
        lambda: replace(PLAN, regions=(*PLAN.regions, PLAN.regions[3])),  # an overlap
        lambda: _without(PLAN, SOUTH),  # a face with no tree
    ],
)
def test_tiled_catches_holes_overlaps_and_missing_trees(broken):
    assert "tiled" in failures(measure(broken()))


def test_regions_round_trip_through_the_plan_json():
    again = Plan.from_dict(json.loads(PLAN.to_json()))
    assert again.regions == PLAN.regions


def test_elevation_sheet_draws_every_leaf_in_a_known_colour(tmp_path):
    plans = elevation_sheet(SPEC, [4, 5], tmp_path, tile=(120, 100), cols=2)
    sheet = Image.open(tmp_path / "elevation_sheet.jpg")
    assert sheet.size[0] == 240 and sheet.size[1] > 100
    kinds = {leaf_kind(r) for p in plans for r in p.regions if r.treatment}
    assert kinds <= set(FILLS)
    assert {"luxury.shaft", "functional.shaft", "luxury.lobby", "portal"} <= kinds


def test_courses_tile_the_floors_with_lobbies_on_the_rhythm():
    plan = courses(
        range(100, 160),
        0,
        3,
        foot=True,
        seams=[("transfer", range(118, 121))],
        rhythm=(119, 10, 2),
    )
    assert [f for _, r in plan for f in r] == list(range(100, 160))
    assert plan[0] == ("foot", range(100, 101)) and plan[-1] == ("capital", range(157, 160))
    assert ("transfer", range(118, 121)) in plan
    lobbies = [r for kind, r in plan if kind == "lobby"]
    assert lobbies == [range(107, 109), range(131, 133), range(143, 145)]  # 119 + 12j
    for i, (kind, _) in enumerate(plan):
        if kind == "lobby":  # with MIN_RUN floors of run either side
            for _, r in (plan[i - 1], plan[i + 1]):
                assert len(r) >= MIN_RUN
    # Too short for a lobby: base, run, capital.
    assert courses(range(6), 2, 1, rhythm=(0, 8, 1)) == [
        ("base", range(2)),
        ("run", range(2, 5)),
        ("capital", range(5, 6)),
    ]


def _datum(plan):
    return next(
        e.floor
        for e in plan.elements
        if e.kind == "bridge" and e.tags["from"] == f"{CENTRAL}/section.0"
    )


def test_lobbies_line_up_across_the_building_on_the_transfer_floor():
    datum, fac = _datum(PLAN), facade_system(SPEC)
    faces = [r for r in PLAN.regions if r.layer == "face"]
    assert {tuple(r.tags["rhythm"]) for r in faces} == {(datum, fac.run, fac.lobby)}
    # The transfer course runs round the central tower and every sister tower, from the
    # band under the bridges to their top.
    transfer = {r.mass for r in PLAN.regions if r.treatment and r.tags["course"] == "transfer"}
    sisters = {e.id for e in PLAN.elements if e.kind == "mass" and e.tags.get("ring") == 0} & {
        r.mass for r in PLAN.regions if r.mass.endswith("/section.0")
    }
    assert sisters and transfer == {f"{CENTRAL}/section.0", *sisters}
    assert all(
        r.floors == (datum - 1, datum + 2)
        for r in PLAN.regions
        if r.treatment and r.tags["course"] == "transfer"
    )
    lobbies = {r.mass.rsplit("/", 1)[0] for r in PLAN.regions if r.tags.get("course") == "lobby"}
    assert CENTRAL in lobbies and len(lobbies) > 1  # sister towers too


def test_varied_repetition_gives_tower_groups_their_own_band_rhythm():
    differ = 0
    for seed in range(10):
        plan = resolve(replace(spec_with(SPEC, "style.repetition", "varied"), seed=seed))
        rhythm = {}
        for r in plan.regions:
            if r.layer == "face" and "tower." in r.mass:
                rhythm.setdefault(r.mass.split("/")[1], set()).add(tuple(r.tags["rhythm"]))
        assert all(len(v) == 1 for v in rhythm.values())  # one per tower
        for tower, v in rhythm.items():
            if ".east." in tower:
                assert v == rhythm[tower.replace(".east.", ".west.")]  # twins alike
        differ += len({v.pop() for v in rhythm.values()}) > 1
    assert differ >= 5


def _luxury(plan, **where):
    leaves = [
        r for r in plan.regions if r.treatment and all(r.tags.get(k) == v for k, v in where.items())
    ]
    return sum(r.tags["grade"] == "luxury" for r in leaves) / len(leaves)


def test_portals_then_the_axis_take_the_luxury():
    portals = [r for r in PLAN.regions if r.treatment == "portal"]
    assert portals and all(r.tags["grade"] == "luxury" for r in portals)
    assert (
        _luxury(PLAN, column="axis") > _luxury(PLAN, column="edge") > _luxury(PLAN, column="flank")
    )
    assert _luxury(PLAN, course="capital") > _luxury(PLAN, course="run")


def test_luxury_follows_the_spec_and_the_hierarchy():
    def share(luxury):
        stats = layers(resolve(spec_with(SPEC, "program.luxury", luxury)))["luxury"]
        return stats["building"], stats["central"], stats["sister"]

    lean, rich = share(0.15), share(0.35)
    assert lean[0] < rich[0]
    assert 0.1 <= lean[0] <= 0.2 and 0.3 <= rich[0] <= 0.4
    assert rich[1] > rich[2]  # the central tower carries the most


def _regraded(plan, rid, grade):
    regions = tuple(
        replace(r, tags={**r.tags, "grade": grade}) if r.id == rid else r for r in plan.regions
    )
    return replace(plan, regions=regions)


def test_programmed_catches_an_ungraded_portal_and_a_lopsided_grading():
    portal = next(r.id for r in PLAN.regions if r.treatment == "portal")
    assert "programmed" in failures(measure(_regraded(PLAN, portal, "functional")))
    edge = next(
        r.id
        for r in PLAN.regions
        if r.treatment and r.tags["column"] == "edge" and r.tags["grade"] == "luxury"
    )
    assert failures(measure(_regraded(PLAN, edge, "functional"))) == ["programmed"]
    assert measure(replace(PLAN, style={**PLAN.style, "symmetry": "none"}))["checks"]["programmed"]


def test_banded_catches_a_lobby_off_the_rhythm():
    regions = tuple(
        replace(r, tags={**r.tags, "rhythm": [r.tags["rhythm"][0] + 1, *r.tags["rhythm"][1:]]})
        if r.id == f"{CENTRAL}/section.0/facade.south"
        else r
        for r in PLAN.regions
    )
    assert failures(measure(replace(PLAN, regions=regions))) == ["banded"]
