import json
from dataclasses import replace
from pathlib import Path

import pytest

from arcology.metrics import failures, measure
from arcology.plan import Plan
from arcology.resolve import ResolveError, resolve
from arcology.rules import outline
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
TOWER = "arcology/tower.central"


def _with(spec, section, **changes):
    return replace(spec, **{section: replace(getattr(spec, section), **changes)})


def _under(plan, prefix):
    return [e for e in plan.elements if e.id.startswith(prefix)]


def _identity(e):
    return e.id, e.seed, e.params, e.count


def test_same_spec_gives_identical_plan_json():
    assert resolve(SPEC).to_json() == resolve(SPEC).to_json()


def test_seed_picks_different_buildings():
    plans = {resolve(replace(SPEC, seed=s)).to_json() for s in range(20)}
    assert len(plans) == 20


def test_mass_ids_are_stable_paths():
    ids = [e.id for e in resolve(SPEC).elements if e.kind == "mass"]
    assert ids[:8] == [f"arcology/podium/tier.{i}" for i in range(4)] + [
        f"{TOWER}/section.{k}" for k in range(4)
    ]
    assert all(i.startswith("arcology/tower.") and "/section." in i for i in ids[8:])


def test_every_mass_is_dressed_round_its_outline():
    plan = resolve(_with(SPEC, "central_tower", corner_notch=1))
    for mass in (e for e in plan.elements if e.kind == "mass"):
        kids = {e.id.removeprefix(mass.id + "/") for e in _under(plan, mass.id + "/")}
        edges = outline(mass.params["width"], mass.params["depth"], mass.params.get("notch", 0))
        assert {"core", "cornice"} <= kids
        assert {f"corner.{e.corner}" for e in edges} <= kids
        glazed = {
            w.tags["facade"]
            for w in plan.elements
            if w.kind == "window" and w.tags["mass"] == mass.id
        }
        assert glazed == {e.name for e in edges}, mass.id
    notched = plan.element(f"{TOWER}/section.0")
    assert notched.recipe == "mass.notched" and notched.params["notch"] == plan.bay_width


def test_changing_the_podium_does_not_reshuffle_the_tower():
    before = resolve(SPEC)
    after = resolve(_with(SPEC, "primary_mass", tiers=(9, 9, 9)))  # fewer, taller tiers
    tower_before, tower_after = _under(before, TOWER), _under(after, TOWER)
    assert [_identity(e) for e in tower_after] == [_identity(e) for e in tower_before]
    for old, new in zip(tower_before, tower_after, strict=True):
        assert new.translation[2] != old.translation[2]  # it only moves to the new podium top


def test_changing_the_tower_does_not_touch_the_podium():
    before = resolve(SPEC)
    after = resolve(_with(SPEC, "central_tower", floors=(130, 140), setback_inset=0.1))
    assert _under(after, "arcology/podium") == _under(before, "arcology/podium")
    assert _under(after, TOWER) != _under(before, TOWER)


def test_changing_the_facade_does_not_touch_the_massing():
    before = resolve(SPEC)
    after = resolve(_with(SPEC, "facade", density=0.2, pier_width=1.4, mullions=0))
    masses = [e for e in before.elements if e.kind == "mass"]
    assert [e for e in after.elements if e.kind == "mass"] == masses
    assert after != before


def test_fixed_values_are_used_exactly():
    spec = _with(SPEC, "central_tower", width=120, depth=96, floors=100, setbacks=(40, 70, 90))
    plan = resolve(spec)
    base = plan.element(f"{TOWER}/section.0")
    assert (base.params["width"], base.params["depth"]) == (120, 96)
    assert measure(plan)["tower_floors"] == 100


def test_entrance_is_centred_on_the_podium_south_face():
    plan = resolve(_with(SPEC, "facade", entrance_bays=5, entrance_floors=3))
    entrance = next(e for e in plan.elements if e.kind == "entrance")
    assert (entrance.tags["mass"], entrance.tags["facade"]) == ("arcology/podium/tier.0", "south")
    bays = round(plan.element("arcology/podium/tier.0").params["width"] / plan.bay_width)
    b0, b1 = entrance.tags["bays"]
    assert b0 == bays - b1  # same number of bays either side
    assert entrance.tags["floors"] == [0, 3]
    assert entrance.translation[0] == 0


@pytest.mark.parametrize("seed", range(200))
def test_default_spec_always_resolves_to_a_valid_building(seed):
    m = measure(resolve(replace(SPEC, seed=seed)))
    assert failures(m) == []
    assert 400 <= m["height_m"] <= 600
    assert m["windows"] > 5000


def test_plan_round_trips_through_json():
    plan = resolve(SPEC)
    assert Plan.from_dict(json.loads(plan.to_json())) == plan


@pytest.mark.parametrize(
    ("section", "changes", "message"),
    [
        ("central_tower", {"width": 400}, "doesn't fit on the"),
        ("central_tower", {"setbacks": (50, 40)}, "must rise strictly"),
        ("central_tower", {"floors": 30, "setbacks": (10, 20, 30)}, "must rise strictly"),
        ("primary_mass", {"tier_inset": 0.24, "tiers": (2, 2, 2, 2, 2)}, "steps in to nothing"),
        (
            "central_tower",
            {"setback_inset": 0.24, "setbacks": tuple(range(5, 80, 5))},
            "steps in",
        ),
        ("facade", {"pier_width": 3.0}, "leave no room in a bay"),
        ("facade", {"entrance_floors": 6}, "as tall as the 6-floor tier"),
    ],
)
def test_impossible_buildings_raise_with_the_element_named(section, changes, message):
    with pytest.raises(ResolveError, match=message):
        resolve(_with(SPEC, section, **changes))


def test_entrance_too_wide_for_its_facade_is_named():
    narrow = _with(SPEC, "primary_mass", width=60)  # 10 bays wide
    narrow = _with(narrow, "central_tower", width=12, depth=12, setbacks=())
    narrow = _with(narrow, "facade", entrance_bays=15)
    narrow = _with(narrow, "secondary_towers", count=0)
    with pytest.raises(ResolveError, match="tier.0/facade.south/entrance: .* won't fit"):
        resolve(narrow)
