import random

import pytest

from assetgen import TRI_BUDGET, build_set, mesh_stats, scatter
from assetgen.generators import ROCK_SINK

SEEDS = [1, 42, 1234]


def _signature(objs):
    return [(ob.name, tuple(round(c, 5) for v in ob.data.vertices for c in v.co)) for ob in objs]


def test_same_seed_gives_identical_geometry():
    first = _signature(build_set(7))
    assert _signature(build_set(7)) == first
    assert _signature(build_set(8)) != first


def test_counts_follow_arguments():
    names = [ob.name for ob in build_set(1, rocks=2, trees=3)]
    assert names == ["rock_0", "rock_1", "tree_0", "tree_1", "tree_2"]


@pytest.mark.parametrize("seed", SEEDS)
def test_assets_are_built_at_the_origin(seed):
    for ob in build_set(seed):
        stats = mesh_stats(ob)
        lo, hi = stats["bounds_min"], stats["bounds_max"]
        assert tuple(ob.location) == (0, 0, 0), ob.name
        for axis in (0, 1):
            assert lo[axis] + hi[axis] == pytest.approx(0, abs=1e-3), f"{ob.name} axis {axis}"
        height = hi[2] - lo[2]
        base = -ROCK_SINK * height if ob.name.startswith("rock") else 0.0
        assert lo[2] == pytest.approx(base, abs=1e-3), ob.name


@pytest.mark.parametrize("seed", SEEDS)
def test_triangle_budgets(seed):
    for ob in build_set(seed):
        kind = ob.name.split("_")[0]
        assert mesh_stats(ob)["tris"] <= TRI_BUDGET[kind], ob.name


def test_scatter_is_deterministic_spaced_and_bounded():
    pts = scatter(random.Random(3), 9, extent=4.0, min_dist=2.0)
    assert pts == scatter(random.Random(3), 9, extent=4.0, min_dist=2.0)
    assert len(pts) == 9
    assert all(abs(c) <= 4.0 for p in pts for c in p)
    assert all((a - b).length >= 2.0 for i, a in enumerate(pts) for b in pts[i + 1 :])


def test_scatter_rejects_impossible_layouts():
    with pytest.raises(ValueError, match="could not place"):
        scatter(random.Random(0), 50, extent=1.0, min_dist=2.0, max_tries=10)
