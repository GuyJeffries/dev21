"""Shared fixtures.

bpy has one global scene and build_set() resets it, so fixtures hand out plain
data (paths, manifests), never live Blender objects a later test could wipe.
"""

import pytest

from assetgen import build_set, export_set

SEED = 42


@pytest.fixture(scope="session")
def exported(tmp_path_factory):
    out = tmp_path_factory.mktemp("assets")
    return out, export_set(build_set(SEED), out, SEED)
