from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from arcology.facade import MINOR_SETBACK, pilaster_lines, progressions
from arcology.metrics import failures, measure
from arcology.plan import instances
from arcology.resolve import resolve
from arcology.rules import CENTRAL, outline, standing
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
PLAN = resolve(SPEC)


def _with(spec, section, **changes):
    return replace(spec, **{section: replace(getattr(spec, section), **changes)})


def _of(plan, kind, **tags):
    return [
        e
        for e in plan.elements
        if e.kind == kind and all(e.tags.get(k) == v for k, v in tags.items())
    ]


@pytest.mark.parametrize("k", range(0, 9))
@pytest.mark.parametrize("n", range(1, 41))
def test_pilasters_are_symmetric_and_every_k_lines(n, k):
    lines = sorted(pilaster_lines(n, k))
    assert set(lines) <= set(range(1, n))
    assert {n - line for line in lines} == set(lines)  # mirror about the facade's centre
    if k == 0:
        assert lines == []
        return
    gaps = [b - a for a, b in zip(lines, lines[1:], strict=False)]
    # Every gap is k bays, except one central group of k - 1 when parities differ.
    assert sorted(gaps) in ([k] * len(gaps), [k - 1] + [k] * (len(gaps) - 1))
    if lines:  # no run of more than k bays without a pilaster (ends are corners)
        assert lines[0] <= k and n - lines[-1] <= k


def test_progressions_cover_lines_exactly_with_a_common_stride():
    lines = {1, 2, 4, 5, 7, 8, 11, 14}
    runs = progressions(lines, 3)
    assert sorted(x for r in runs for x in r) == sorted(lines)
    assert all(r.step == 3 for r in runs)
    assert progressions(range(1, 10), 0) == [range(1, 10)]


def test_pilasters_stand_full_depth_and_minor_piers_stand_back():
    pilasters = [e for e in PLAN.elements if e.tags.get("order") == "pilaster"]
    piers = [e for e in PLAN.elements if e.tags.get("order") == "pier"]
    assert pilasters and piers
    assert all(e.extent[0][1] == 0.0 for e in pilasters)
    assert all(e.params["front"] == MINOR_SETBACK == e.extent[0][1] for e in piers)
    # Without pilasters every pier is the same full-depth strip.
    plain = resolve(_with(SPEC, "facade", pilaster_every=0))
    orders = {e.tags.get("order") for e in plain.elements if e.kind == "pier"}
    assert orders == {"pier", "corner"}
    assert all("front" not in e.params for e in plain.elements if e.kind == "pier")


@pytest.mark.parametrize("plan", [PLAN, resolve(replace(SPEC, seed=37))], ids=["default", "37"])
def test_every_bay_line_has_a_pier_on_every_floor_but_where_a_treatment_spans_it(plan):
    fh = plan.floor_height
    spans = defaultdict(list)  # face -> leaves that take the piers on their lines
    for r in plan.regions:
        if r.treatment and r.treatment not in ("cells", "rich"):
            spans[r.mass, r.facade].append(r)
    for face in {(r.mass, r.facade) for r in plan.regions if r.layer == "face"}:
        root = next(r for r in plan.regions if r.layer == "face" and (r.mass, r.facade) == face)
        covered, ids = defaultdict(list), []
        for e in plan.elements:
            if e.kind != "pier" or (e.tags["mass"], e.tags.get("facade")) != face:
                continue
            for c in instances(plan, e):
                ids.append(c.id)
                if e.tags["order"] != "back":  # a recess's back wall
                    covered[c.tags["pier"]] += range(
                        c.floor, c.floor + round(e.params["height"] / fh)
                    )
        assert len(set(ids)) == len(ids), face
        for line in range(1, root.bays[1]):
            blocked = {
                f for r in spans[face] if r.bays[0] < line < r.bays[1] for f in range(*r.floors)
            }
            assert sorted(covered[line]) == sorted(set(range(*root.floors)) - blocked), (face, line)


def test_zones_base_on_the_ground_tier_capital_at_every_top():
    tier0 = PLAN.element("arcology/podium/tier.0")
    entrance = next(e for e in PLAN.elements if e.kind == "entrance")
    base = _of(PLAN, "window", zone="base")
    assert base and {e.tags["mass"] for e in base} == {tier0.id}
    assert {c.floor for e in base for c in instances(PLAN, e)} == set(
        range(*entrance.tags["floors"])
    )
    for m in (e for e in PLAN.elements if e.kind == "mass"):
        top = m.floor + round(m.params["height"] / PLAN.floor_height)
        capital = {
            c.floor
            for e in _of(PLAN, "window", zone="capital", mass=m.id)
            for c in instances(PLAN, e)
        }
        assert capital and max(capital) == top - 1, m.id
        assert capital == set(range(min(capital), top)), m.id


def test_capitals_are_deeper_on_richer_masses():
    # More ornament, more capital floors, on the same massing.
    def capital_floors(plan):
        out = defaultdict(set)
        for e in _of(plan, "window", zone="capital"):
            out[e.tags["mass"]] |= {c.floor for c in instances(plan, e)}
        return {m: len(f) for m, f in out.items()}

    lean = capital_floors(resolve(replace(SPEC, style=replace(SPEC.style, ornament_density=0))))
    rich = capital_floors(resolve(replace(SPEC, style=replace(SPEC.style, ornament_density=1))))
    assert all(rich[m] >= lean[m] for m in lean)
    assert sum(rich.values()) > sum(lean.values())


def test_doors_at_the_foot_of_every_tower_outer_face():
    doors = {f"{e.tags['mass']}/facade.{e.tags['facade']}": e for e in _of(PLAN, "door")}
    expected = {f"{CENTRAL}/section.0/facade.south", f"{CENTRAL}/section.0/facade.north"}
    for m in (e for e in PLAN.elements if e.kind == "mass" and e.id.endswith("/section.0")):
        if m.tags["tower"] != CENTRAL:
            side = m.tags["tower"].rsplit(".", 2)[-2]  # tower.east.mid -> east
            expected.add(f"{m.id}/facade.{side}")
    assert doors.keys() == expected
    for face, door in doors.items():
        mass = PLAN.element(face.rsplit("/", 1)[0])
        assert door.floor == mass.floor and door.tags["floors"] == [mass.floor, mass.floor + 1]
        edge = next(
            e
            for e in outline(
                mass.params["width"], mass.params["depth"], mass.params.get("notch", 0)
            )
            if face.endswith(f"facade.{e.name}")
        )
        n = round(edge.length / PLAN.bay_width)
        b0, b1 = door.tags["bays"]
        assert b1 - b0 == 2 - n % 2 and b0 == n - b1  # one bay or two, centred


def test_ornament_follows_standing():
    rich = {
        standing(PLAN.element(e.tags["mass"]))
        for e in PLAN.elements
        if e.params.get("flutes") or e.kind == "merlon"
    }
    assert rich == {"central"}  # at the default density only the central tower is fluted
    chevrons = {
        standing(PLAN.element(e.tags["mass"])): e.params.get("chevrons", 0)
        for e in _of(PLAN, "window", zone="capital")
    }
    assert chevrons["central"] == 2 and chevrons["podium"] == chevrons["sister"] == 1
    cornices = {
        standing(PLAN.element(e.tags["mass"])): len(e.params["rings"]) for e in _of(PLAN, "cornice")
    }
    assert cornices["central"] > cornices["sister"]


def test_no_ornament_at_zero_density_and_merlons_only_over_parapets():
    bare = resolve(replace(SPEC, style=replace(SPEC.style, ornament_density=0.0)))
    assert not _of(bare, "merlon")
    assert not any(e.params.get("chevrons") or e.params.get("flutes") for e in bare.elements)
    assert failures(measure(bare)) == []
    parapets = {e.id.removesuffix("/parapet") for e in _of(PLAN, "parapet")}
    merlons = {e.tags["mass"] for e in _of(PLAN, "merlon")}
    assert merlons and merlons <= parapets


def test_low_walls_take_single_floor_pavilion_bridges():
    spec = _with(SPEC, "primary_mass", width=640, depth=640, tier_inset=0.09, tiers=(6, 6, 6, 3))
    spec = _with(spec, "secondary_towers", count=2, placement="corners")
    plan = resolve(spec)
    bridges = _of(plan, "bridge")
    assert bridges and all(b.params["height"] == plan.floor_height for b in bridges)
    assert failures(measure(plan)) == []
