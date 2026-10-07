import statistics

import bpy

from assetgen import build_set, render_preview


def test_preview_renders_a_non_blank_image(tmp_path):
    path = tmp_path / "preview.png"
    render_preview(build_set(5, rocks=1, trees=1), path, seed=5, resolution=(160, 100), samples=4)
    img = bpy.data.images.load(str(path))
    assert tuple(img.size) == (160, 100)
    red = img.pixels[:][0::4]
    assert statistics.pstdev(red) > 0.02, "preview looks like a flat fill"
