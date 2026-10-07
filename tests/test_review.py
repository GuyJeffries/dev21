import json
from dataclasses import replace

from PIL import Image, ImageStat

from arcology.plan import element_bounds, plan_bounds
from arcology.resolve import resolve
from arcology.review import contact_sheet, detail_cameras, detail_sheet, shared_camera


def test_shared_camera_encloses_every_plan(spec):
    plans = [resolve(replace(spec, seed=s)) for s in (1, 2, 3)]
    camera = shared_camera(plans)
    for p in plans:
        lo, hi = plan_bounds(p)
        assert all(camera["lo"][i] <= lo[i] and hi[i] <= camera["hi"][i] for i in range(3))


def test_detail_cameras_frame_the_entrance(plan):
    camera = detail_cameras(plan)["entrance"]
    lo, hi = element_bounds(next(e for e in plan.elements if e.kind == "entrance"))
    assert all(camera["lo"][i] <= lo[i] and hi[i] <= camera["hi"][i] for i in range(3))


def test_contact_sheet_renders_tiles_and_metrics(spec, tmp_path):
    results = contact_sheet(spec, [4, 5], tmp_path, tile=(64, 48), cols=2, samples=1)
    sheet = Image.open(tmp_path / "contact_sheet.jpg")
    assert sheet.size == (128, 48 + 34)
    for seed in (4, 5):
        tile = Image.open(tmp_path / f"seed-{seed}/tile.png").convert("L")
        assert ImageStat.Stat(tile).stddev[0] > 5, "tile looks like a flat fill"
        assert (tmp_path / f"seed-{seed}/plan.json").exists()
    assert [r["seed"] for r in results] == [4, 5]
    assert json.loads((tmp_path / "metrics.json").read_text()) == results
    table = (tmp_path / "metrics.md").read_text().splitlines()
    assert table[0] == "### Contact sheet: 2 seeds, L2"
    assert [line.split("|")[1].strip() for line in table[4:]] == ["4", "5"]


def test_detail_sheet_renders_two_close_ups_per_seed(spec, tmp_path):
    detail_sheet(spec, [6], tmp_path, tile=(96, 64), samples=1)
    assert Image.open(tmp_path / "detail_sheet.jpg").size == (192, 64 + 34)
    for name in ("entrance", "tower_corner"):
        tile = Image.open(tmp_path / f"seed-6/{name}.png").convert("L")
        assert ImageStat.Stat(tile).stddev[0] > 5, name
