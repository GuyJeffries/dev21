import json
import re
from pathlib import Path

import pytest

from arcology.spec import SCHEMA, Spec, SpecError, load_spec, spec_from_dict, spec_to_dict

ROOT = Path(__file__).parents[1]


def test_schema_only_gives_all_defaults():
    assert spec_from_dict({"schema": SCHEMA}) == Spec()


def test_repo_default_spec_loads_and_round_trips():
    spec = load_spec(ROOT / "specs/default.json")
    assert spec_from_dict(spec_to_dict(spec)) == spec
    assert spec.primary_mass.tiers[1] == (5, 7)


def test_plan_document_example_spec_is_valid():
    plan_md = (ROOT / "docs/PLAN.md").read_text()
    section = plan_md[plan_md.index("### 6.1") :]
    example = re.search(r"```json\n(.*?)```", section, re.S).group(1)
    spec = spec_from_dict(json.loads(example))
    assert spec.central_tower.setbacks == (40, 70, 90)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "schema: missing"),
        ({"schema": "arcology-spec/9"}, "schema: expected one of arcology-spec/0"),
        ({"schema": SCHEMA, "colour": "red"}, "spec: unknown field(s): colour"),
        (
            {"schema": SCHEMA, "central_tower": {"heigth": 3}},
            "central_tower: unknown field(s): heigth",
        ),
        (
            {"schema": SCHEMA, "primary_mass": {"width": [500, "x"]}},
            "primary_mass.width[1]: expected a number",
        ),
        (
            {"schema": SCHEMA, "primary_mass": {"width": [600, 500]}},
            "range min 600 is greater than max 500",
        ),
        ({"schema": SCHEMA, "primary_mass": {"width": [1, 2, 3]}}, "a range is [min, max]"),
        (
            {"schema": SCHEMA, "central_tower": {"floors": 90.5}},
            "central_tower.floors: expected a whole number",
        ),
        ({"schema": SCHEMA, "primary_mass": {"tiers": []}}, "primary_mass.tiers: expected a list"),
        ({"schema": SCHEMA, "style": {"symmetry": "radial"}}, "style.symmetry: expected one of"),
        ({"schema": SCHEMA, "floor_height": 40}, "floor_height: 40 is outside 2..12"),
        ({"schema": SCHEMA, "seed": True}, "seed: expected a number"),
        ({"schema": SCHEMA, "facade": {"mullions": 9}}, "facade.mullions: 9 is outside 0..6"),
        (
            {"schema": SCHEMA, "facade": {"pier_width": [1, 0.5]}},
            "range min 1 is greater than max 0.5",
        ),
        (
            {"schema": SCHEMA, "facade": {"entrance_bays": 2.5}},
            "facade.entrance_bays: expected a whole",
        ),
        (
            {"schema": SCHEMA, "facade": {"pilaster_every": 13}},
            "facade.pilaster_every: 13 is outside 0..12",
        ),
        (
            {"schema": SCHEMA, "central_tower": {"corner_notch": [0, 7]}},
            "central_tower.corner_notch[1]: 7 is outside 0..6",
        ),
    ],
)
def test_invalid_specs_name_the_field(data, message):
    with pytest.raises(SpecError) as err:
        spec_from_dict(data)
    assert message in str(err.value)
