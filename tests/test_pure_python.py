import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_spec_resolver_metrics_and_elevations_run_without_blender(tmp_path):
    # Blocking bpy makes any import of it fail, proving the grammar stays portable.
    code = f"""
import sys
sys.modules["bpy"] = None
from arcology.__main__ import main
assert main(["resolve", r"{ROOT / "specs/default.json"}", "-o", r"{tmp_path / "plan.json"}"]) == 0
out = r"{tmp_path / "elevations"}"
assert main(["elevations", r"{ROOT / "specs/default.json"}", "--seeds", "1", "-o", out]) == 0
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path)
    assert (tmp_path / "plan.json").exists()
    assert (tmp_path / "elevations/elevation_sheet.jpg").exists()
