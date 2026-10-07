import json
from pathlib import Path

from arcology.__main__ import main

SPEC = str(Path(__file__).parents[1] / "specs/default.json")


def test_resolve_then_build(tmp_path, capsys):
    plan = tmp_path / "plan.json"
    assert main(["resolve", SPEC, "--seed", "9", "-o", str(plan)]) == 0
    assert json.loads(plan.read_text())["seed"] == 9

    assert main(["build", str(plan), "-o", str(tmp_path / "lib"), "--lod", "L3"]) == 0
    manifest = json.loads((tmp_path / "lib/manifest.json").read_text())
    assert manifest["lod"] == "L3"
    assert len(manifest["instances"]) == 8  # the envelope boxes
    assert "8 unique elements, 8 instances" in capsys.readouterr().out


def test_resolve_prints_plan_json_without_out(capsys):
    assert main(["resolve", SPEC]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "arcology-plan/0"


def test_bad_spec_reports_the_field_and_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "arcology-spec/0", "central_tower": {"floor": 3}}))
    assert main(["resolve", str(bad)]) == 2
    assert "central_tower: unknown field(s): floor" in capsys.readouterr().err


def test_impossible_building_exits_2(tmp_path, capsys):
    bad = tmp_path / "wide.json"
    bad.write_text(json.dumps({"schema": "arcology-spec/0", "central_tower": {"width": 900}}))
    assert main(["resolve", str(bad)]) == 2
    assert "doesn't fit" in capsys.readouterr().err
