import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_spec_resolver_and_metrics_run_without_blender(tmp_path):
    # Blocking bpy makes any import of it fail, proving the grammar stays portable.
    code = f"""
import sys
sys.modules["bpy"] = None
from arcology.__main__ import main
assert main(["resolve", r"{ROOT / "specs/default.json"}", "-o", r"{tmp_path / "plan.json"}"]) == 0
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path)
    assert (tmp_path / "plan.json").exists()
