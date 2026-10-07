"""Shared fixtures. Blender keeps one global scene and build/assemble/render reset it, so
fixtures hand out plain data (plans, paths, manifests), never live bpy objects."""

from dataclasses import replace
from pathlib import Path

import pytest

from arcology.resolve import resolve
from arcology.spec import load_spec

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="session")
def spec():
    return load_spec(ROOT / "specs/default.json")


@pytest.fixture(scope="session")
def plan(spec):
    return resolve(replace(spec, seed=3))


@pytest.fixture(scope="session")
def built(plan, tmp_path_factory):
    from arcology.build import build_library

    out = tmp_path_factory.mktemp("library")
    return out, build_library(plan, out, "L2")
