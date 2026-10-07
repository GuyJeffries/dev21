import json
from dataclasses import replace
from pathlib import Path

import pytest

from arcology.metrics import failures, measure
from arcology.plan import Plan
from arcology.resolve import ResolveError, resolve
from arcology.spec import load_spec

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
TOWER = "arcology/tower.central"


def _with(spec, section, **changes):
    return replace(spec, **{section: replace(getattr(spec, section), **changes)})


def test_same_spec_gives_identical_plan_json():
    assert resolve(SPEC).to_json() == resolve(SPEC).to_json()


def test_seed_picks_different_buildings():
    plans = {resolve(replace(SPEC, seed=s)).to_json() for s in range(20)}
    assert len(plans) == 20


def test_element_ids_are_stable_paths():
    ids = [e.id for e in resolve(SPEC).elements]
    assert ids == [f"arcology/podium/tier.{i}" for i in range(4)] + [
        f"{TOWER}/section.{k}" for k in range(4)
    ]


def _tower(plan):
    return [e for e in plan.elements if e.id.startswith(TOWER)]


def test_changing_the_podium_does_not_reshuffle_the_tower():
    before = resolve(SPEC)
    after = resolve(_with(SPEC, "primary_mass", tiers=(9, 9, 9)))  # fewer, taller tiers
    for old, new in zip(_tower(before), _tower(after), strict=True):
        assert (new.id, new.seed, new.params) == (old.id, old.seed, old.params)
        assert new.translation[2] != old.translation[2]  # it only moves to the new podium top


def test_changing_the_tower_does_not_touch_the_podium():
    before = resolve(SPEC)
    after = resolve(_with(SPEC, "central_tower", floors=(130, 140), setback_inset=0.1))
    podium = [e for e in before.elements if e not in _tower(before)]
    assert [e for e in after.elements if e not in _tower(after)] == podium
    assert _tower(after) != _tower(before)


def test_fixed_values_are_used_exactly():
    spec = _with(SPEC, "central_tower", width=120, depth=96, floors=100, setbacks=(40, 70, 90))
    plan = resolve(spec)
    base = plan.element(f"{TOWER}/section.0")
    assert (base.params["width"], base.params["depth"]) == (120, 96)
    assert measure(plan)["tower_floors"] == 100


@pytest.mark.parametrize("seed", range(200))
def test_default_spec_always_resolves_to_a_valid_building(seed):
    m = measure(resolve(replace(SPEC, seed=seed)))
    assert failures(m) == []
    assert 400 <= m["height_m"] <= 600


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
        ("central_tower", {"setback_inset": 0.24, "setbacks": tuple(range(5, 80, 5))}, "steps in"),
    ],
)
def test_impossible_buildings_raise_with_the_element_named(section, changes, message):
    with pytest.raises(ResolveError, match=message):
        resolve(_with(SPEC, section, **changes))
