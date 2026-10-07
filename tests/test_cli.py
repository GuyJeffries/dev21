import argparse
import json
from pathlib import Path

import pytest

from arcology.__main__ import main

SPEC = str(Path(__file__).parents[1] / "specs/default.json")


def test_resolve_then_build(tmp_path, capsys):
    plan = tmp_path / "plan.json"
    assert main(["resolve", SPEC, "--seed", "9", "-o", str(plan)]) == 0
    assert json.loads(plan.read_text())["seed"] == 9

    assert main(["build", str(plan), "-o", str(tmp_path / "lib"), "--lod", "L3"]) == 0
    manifest = json.loads((tmp_path / "lib/manifest.json").read_text())
    assert manifest["lod"] == "L3"
    placed = {r["id"].split("/")[1] for r in manifest["instances"]}  # podium and towers only
    assert placed >= {"podium", "tower.central"} and all(
        p.split(".")[0] in ("podium", "tower") for p in placed
    )
    assert f"{len(manifest['instances'])} instances" in capsys.readouterr().out


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


def test_sweep_rows_parse_numbers_and_words():
    from arcology.__main__ import _sweep

    assert _sweep("style.ornament_density=0,0.5,1") == ("style.ornament_density", [0, 0.5, 1])
    assert _sweep("style.hierarchy=strong,weak") == ("style.hierarchy", ["strong", "weak"])
    with pytest.raises(argparse.ArgumentTypeError):
        _sweep("style.hierarchy")


def test_sweep_with_a_bad_parameter_exits_2(capsys):
    assert main(["sweep", SPEC, "--set", "style.colour=red"]) == 2
    assert "unknown field 'colour'" in capsys.readouterr().err
