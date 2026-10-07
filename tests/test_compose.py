from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from arcology.compose import PAIRS, PAVILION_SLENDERNESS
from arcology.metrics import failures, measure
from arcology.resolve import ResolveError, resolve
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
CENTRAL = "arcology/tower.central"


def _towers(spec, **changes):
    return replace(spec, secondary_towers=replace(spec.secondary_towers, **changes))


def _secondaries(plan):
    towers: dict[str, list] = {}
    for e in plan.elements:
        if e.kind == "mass" and e.tags.get("role") == "tower" and e.tags["tower"] != CENTRAL:
            towers.setdefault(e.tags["tower"], []).append(e)
    return towers


def test_no_secondary_towers_means_no_bridges_or_bands():
    plan = resolve(_towers(SPEC, count=0))
    kinds = Counter(e.kind for e in plan.elements)
    assert kinds["bridge"] == kinds["band"] == 0
    assert kinds["crown"] == 1
    assert failures(measure(plan)) == []


@pytest.mark.parametrize("placement", sorted(PAIRS))
@pytest.mark.parametrize("count", range(10))
def test_every_count_and_placement_resolves_valid(count, placement):
    # A broad podium so every ring has room.
    spec = replace(
        SPEC, primary_mass=replace(SPEC.primary_mass, width=640, depth=640, tier_inset=0.09)
    )
    plan = resolve(_towers(spec, count=count, placement=placement))
    assert len(_secondaries(plan)) == count
    assert failures(measure(plan)) == []


@pytest.mark.parametrize("seed", range(40))
def test_secondary_towers_come_in_mirror_twins(seed):
    plan = resolve(replace(SPEC, seed=seed))
    by_place = {
        (round(s[0].translation[0], 3), round(s[0].translation[1], 3)): s
        for s in _secondaries(plan).values()
    }
    for (x, y), sections in by_place.items():
        twin = by_place[(round(-x, 3), y)]
        assert [s.params for s in twin] == [s.params for s in sections]


def test_secondary_towers_never_change_the_podium_or_central_massing():
    def massing(plan):
        return [
            e for e in plan.elements if e.kind == "mass" and e.tags.get("tower", CENTRAL) == CENTRAL
        ]

    base = massing(resolve(_towers(SPEC, count=0)))
    for count in (2, 5, 9):
        for placement in sorted(PAIRS):
            assert massing(resolve(_towers(SPEC, count=count, placement=placement, gap=1))) == base


@pytest.mark.parametrize("seed", range(40))
def test_pavilions_are_squat_and_lower_than_sister_towers(seed):
    plan = resolve(replace(SPEC, seed=seed))
    sister_tops, pavilion_tops = [], []
    for tid, sections in _secondaries(plan).items():
        top = max(s.translation[2] + s.params["height"] for s in sections)
        if ".t" in tid:  # outer-ring pavilion
            height = sum(s.params["height"] for s in sections)
            assert height <= PAVILION_SLENDERNESS * sections[0].params["width"] + plan.floor_height
            pavilion_tops.append(top)
        else:
            sister_tops.append(top)
    if sister_tops and pavilion_tops:
        assert max(pavilion_tops) < min(sister_tops)


@pytest.mark.parametrize("seed", range(40))
def test_sister_tower_bridges_share_one_floor_with_bands_below(seed):
    plan = resolve(replace(SPEC, seed=seed))
    inner = [e for e in plan.elements if e.kind == "bridge" and e.tags["from"].startswith(CENTRAL)]
    if not inner:
        return
    floors = {b.floor for b in inner}
    assert len(floors) == 1
    bands = [e for e in plan.elements if e.kind == "band"]
    assert {b.floor for b in bands} == {floors.pop() - 1}
    assert len(bands) == len(inner) + 1  # each sister tower and the central tower


@pytest.mark.parametrize(
    ("termination", "recipe", "spire"),
    [
        ("spire", "crown.stepped", True),
        ("stepped", "crown.stepped", False),
        ("flat", "parapet.ring", False),
    ],
)
def test_only_the_central_tower_takes_the_termination(termination, recipe, spire):
    plan = resolve(replace(SPEC, style=replace(SPEC.style, termination=termination)))
    crowns = {e.tags["tower"]: e for e in plan.elements if e.kind == "crown"}
    assert crowns[CENTRAL].recipe == recipe
    assert (crowns[CENTRAL].params.get("spire_height", 0) > 0) == spire
    others = [c for t, c in crowns.items() if t != CENTRAL]
    assert others and all(
        c.recipe == "crown.stepped" and c.params["spire_height"] == 0 for c in others
    )


def test_too_many_towers_for_the_room_is_named():
    cramped = replace(
        SPEC, primary_mass=replace(SPEC.primary_mass, width=300, depth=300, tiers=(6,))
    )
    with pytest.raises(ResolveError, match="arcology/towers: no room for 9 towers"):
        resolve(_towers(cramped, count=9))


def test_pavilions_beside_notched_tiers_bridge_into_the_main_face():
    # A central tower too broad for sister towers pushes pavilions out to the second ring,
    # beside a tier with notched corners: they must line up with its main face.
    spec = replace(
        SPEC,
        primary_mass=replace(
            SPEC.primary_mass, width=640, depth=640, tier_inset=0.09, corner_notch=1.0
        ),
        central_tower=replace(SPEC.central_tower, width=258, depth=258),
    )
    plan = resolve(_towers(spec, count=8, placement="corners"))
    anchors = [plan.element(b.tags["from"]) for b in plan.elements if b.kind == "bridge"]
    assert any(a.params.get("notch") for a in anchors)
    # So broad a central tower is too squat for the style envelope; every other check holds.
    assert failures(measure(plan)) == ["proportioned"]
