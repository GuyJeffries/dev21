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


def test_detail_cameras_frame_the_entrance_setback_and_crown(plan):
    cameras = detail_cameras(plan)
    for name, kind in (("entrance", "entrance"), ("crown", "crown")):
        target = next(
            e
            for e in plan.elements
            if e.kind == kind and "central" in e.tags.get("tower", "central")
        )
        lo, hi = element_bounds(target)
        assert all(
            cameras[name]["lo"][i] <= lo[i] and hi[i] <= cameras[name]["hi"][i] for i in range(3)
        ), name
    # The setback view looks at the top of the base section, where its cornice runs.
    cornice = plan.element("arcology/tower.central/section.0/cornice")
    lo, hi = element_bounds(cornice)
    assert cameras["setback"]["lo"][2] < hi[2] < cameras["setback"]["hi"][2]


def test_contact_camera_includes_the_spire(spec):
    plan = resolve(replace(spec, seed=11))
    camera = shared_camera([plan])
    spire_top = max(element_bounds(e)[1][2] for e in plan.elements if e.kind == "crown")
    assert camera["hi"][2] >= spire_top > plan_bounds(plan)[1][2]


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


def test_detail_sheet_renders_four_close_ups_per_seed(spec, tmp_path):
    detail_sheet(spec, [6], tmp_path, tile=(96, 64), samples=1)
    assert Image.open(tmp_path / "detail_sheet.jpg").size == (384, 64 + 34)
    for name in ("entrance", "cluster", "setback", "crown"):
        tile = Image.open(tmp_path / f"seed-6/{name}.png").convert("L")
        assert ImageStat.Stat(tile).stddev[0] > 5, name
