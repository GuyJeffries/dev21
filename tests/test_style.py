"""Phase 4: every style setting changes the building the way its name says, and the
building stays inside the style envelope (no needle, slab, missing base or ornament noise)."""

from dataclasses import replace
from pathlib import Path
from statistics import median

import pytest

from arcology.metrics import _symmetric, failures, measure
from arcology.plan import instances
from arcology.resolve import resolve
from arcology.rules import CENTRAL, HIERARCHY
from arcology.spec import SpecError, load_spec, spec_with

SPEC = load_spec(Path(__file__).parents[1] / "specs/default.json")
SEEDS = range(20)
SETTINGS = [
    ("setback_strength", "medium"),
    ("setback_strength", "low"),
    ("hierarchy", "moderate"),
    ("hierarchy", "weak"),
    ("dominant_axis", "horizontal"),
    ("symmetry", "none"),
    ("repetition", "varied"),
    ("termination", "stepped"),
    ("termination", "flat"),
    ("ornament_density", 0.0),
    ("ornament_density", 1.0),
    ("contrast", 0.0),
    ("contrast", 1.0),
]


def _styled(**style):
    return replace(SPEC, style=replace(SPEC.style, **style))


def _plans(spec, seeds=SEEDS):
    return [resolve(replace(spec, seed=s)) for s in seeds]


def _towers(plan):
    towers: dict[str, list] = {}
    for e in plan.elements:
        if e.kind == "mass" and e.tags.get("role") == "tower":
            towers.setdefault(e.tags["tower"], []).append(e)
    return towers


@pytest.mark.parametrize(("name", "value"), SETTINGS)
def test_every_style_setting_stays_in_the_envelope(name, value):
    for plan in _plans(_styled(**{name: value})):
        assert failures(measure(plan)) == [], (name, value, plan.seed)


def test_extreme_style_mixes_stay_in_the_envelope():
    mixes = [
        {"hierarchy": "weak", "setback_strength": "low", "ornament_density": 1.0},
        {"dominant_axis": "horizontal", "symmetry": "none", "repetition": "varied"},
    ]
    for style in mixes:
        for plan in _plans(_styled(**style), range(15)):
            assert failures(measure(plan)) == [], (style, plan.seed)


def test_weaker_setbacks_taper_less():
    taper = {
        strength: median(
            measure(p)["style"]["taper"]
            for p in _plans(_styled(setback_strength=strength, contrast=0.0))  # massing only
        )
        for strength in ("high", "medium", "low")
    }
    assert taper["high"] < taper["medium"] < taper["low"]


def test_weaker_hierarchy_lifts_the_sister_towers_and_their_ornament():
    def summary(hierarchy):  # massing and ornament systems: no treatments (rich adds chevrons)
        ms = [measure(p) for p in _plans(_styled(hierarchy=hierarchy, contrast=0.0))]
        return (
            median(m["dominance"] for m in ms if m["dominance"]),
            median(m["ornament"].get("sister", 0) for m in ms),
            min(m["dominance"] for m in ms if m["dominance"]),
        )

    strong, moderate, weak = (summary(h) for h in ("strong", "moderate", "weak"))
    assert strong[0] > moderate[0] > weak[0]  # the central tower dominates less
    assert strong[1] < weak[1]  # sister towers carry more of the ornament
    assert weak[2] >= HIERARCHY["weak"].dominance  # but it still dominates


def test_no_symmetry_lets_twins_differ_and_leaves_odd_towers_unpaired():
    spec = _styled(symmetry="none")
    differ = 0
    for plan in _plans(spec):
        assert measure(plan)["checks"]["symmetric"]  # not required
        differ += not _symmetric(plan)
    assert differ >= len(SEEDS) // 2
    odd = resolve(replace(spec, secondary_towers=replace(spec.secondary_towers, count=3)))
    names = {t.rsplit("/", 1)[-1] for t in _towers(odd)} - {"tower.central"}
    assert names == {"tower.east.mid", "tower.west.mid", "tower.t1.east.north"}  # no axis tower


def test_varied_repetition_gives_tower_groups_their_own_facades_twins_alike():
    def facades(plan):
        out: dict[str, set] = {}
        for e in plan.elements:
            if e.kind == "window" and e.tags["zone"] == "shaft" and not e.params.get("chevrons"):
                tower = plan.element(e.tags["mass"]).tags.get("tower", "podium")
                out.setdefault(tower, set()).add((e.params["sill"], e.params["mullions"]))
        return out

    varied = 0
    for plan in _plans(_styled(repetition="varied")):
        f = facades(plan)
        assert f["podium"] == f[CENTRAL]  # the main composition keeps the building's facade
        for tower, kinds in f.items():
            if ".east." in tower:
                assert kinds == f[tower.replace(".east.", ".west.")], tower
        varied += len({frozenset(k) for k in f.values()}) > 1
    assert varied >= len(SEEDS) // 2
    regular = facades(resolve(replace(SPEC, seed=11)))
    assert len({frozenset(k) for k in regular.values()}) == 1


def test_horizontal_axis_bands_the_shaft():
    plan = resolve(replace(_styled(dominant_axis="horizontal"), seed=11))
    recipes = {e.recipe for e in plan.elements}
    assert "pier.fluted" not in recipes and "merlon.stepped" not in recipes  # no pilasters
    assert {"window.deco_band", "pier.banded", "window.channel_banded"} <= recipes
    shaft = [e for e in plan.elements if e.kind == "window" and e.tags["zone"] == "shaft"]
    assert {e.recipe for e in shaft} == {"window.deco_band"}
    # Every banded pier carries one band per shaft floor it rises through, aligned with the
    # spandrels of the windows beside it; sky lobbies break the bands.
    lobbies = 0
    for pier in (e for e in plan.elements if e.recipe == "pier.banded"):
        lobbies += len(pier.params["bands"]) > 1
        floors = {
            pier.floor + first + k for first, count in pier.params["bands"] for k in range(count)
        }
        beside = {
            c.floor
            for e in shaft
            if e.tags["mass"] == pier.tags["mass"] and e.tags["facade"] == pier.tags["facade"]
            for c in instances(plan, e)
        }
        assert floors <= beside, pier.id
        assert pier.params["sill"] == shaft[0].params["sill"]
    assert lobbies


def test_spec_with_sets_a_dotted_path_and_validates():
    assert spec_with(SPEC, "style.hierarchy", "weak").style.hierarchy == "weak"
    assert spec_with(SPEC, "secondary_towers.count", 3).secondary_towers.count == 3
    with pytest.raises(SpecError, match="style.hierarchy: expected one of"):
        spec_with(SPEC, "style.hierarchy", "loose")
    with pytest.raises(SpecError, match="unknown field 'colour'"):
        spec_with(SPEC, "style.colour", "red")
    with pytest.raises(SpecError, match="'floor_height' is not a section"):
        spec_with(SPEC, "floor_height.x", 1)


def _with(section, **changes):
    return replace(SPEC, **{section: replace(getattr(SPEC, section), **changes)})


@pytest.mark.parametrize(
    ("drift", "check"),
    [
        (_with("central_tower", setbacks=()), "tapered"),  # a slab: no setbacks
        (_with("central_tower", floors=40, setbacks=(20, 30)), "proportioned"),  # a stub
        (  # a needle
            _with("central_tower", width=48, depth=48, floors=120, setbacks=(60, 90)),
            "proportioned",
        ),
        (  # no base to stand on
            replace(
                _with("primary_mass", tiers=(4,)), facade=replace(SPEC.facade, entrance_floors=2)
            ),
            "grounded",
        ),
    ],
)
def test_each_style_check_catches_its_drift(drift, check):
    assert failures(measure(resolve(drift))) == [check]


def test_an_oversized_spire_is_not_restrained():
    plan = resolve(SPEC)
    crown = plan.element(f"{CENTRAL}/crown")
    big = replace(crown, params={**crown.params, "spire_height": 400.0})
    elements = tuple(big if e is crown else e for e in plan.elements)
    assert failures(measure(replace(plan, elements=elements))) == ["restrained"]
