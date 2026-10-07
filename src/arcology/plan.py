"""Resolved plan: every element placed, identified and tagged.

Produced by the resolver and consumed by builders. Plain Python, no Blender.

Frames: a mass's translation is the centre of its base. A facade element's translation is
on the envelope plane, at the base centre of the bay (or portal) it fills, with its local
-Y pointing outward and +X running left to right as seen from outside. `rotation_z_deg`
turns that frame to its facade: south 0, east 90, north 180, west 270.

Repetition: an element with `array` stands for a grid of identical copies. Each copy has
its own stable identity (`instances`), e.g. ".../facade.south/bay.07/floor.012", which
doesn't depend on how the resolver split the grid into blocks.
"""

import hashlib
import itertools
import json
import math
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

from arcology.seeds import derive_seed, path_seed

PLAN_SCHEMA = "arcology-plan/0"
LODS = ("L0", "L1", "L2", "L3")

type Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Element:
    id: str  # stable path, e.g. "arcology/tower.central/section.2"
    kind: str  # "mass", "core", "pier", "window", "entrance", later "asset_slot", ...
    recipe: str  # builder recipe, e.g. "mass.box"
    params: dict  # recipe parameters, metres
    translation: Vec3
    extent: tuple[Vec3, Vec3]  # local bounding box (min, max) in the element's own frame
    floor: int  # floor index of the element's base
    seed: int
    rotation_z_deg: float = 0.0
    lod: tuple[str, ...] = LODS
    tags: dict = field(default_factory=dict)  # "role", "facade"; reserved: "program", "provision"
    # Repetition: {"prefix": id, "axes": [{"name", "start", "count", "step", "digits"}, ...]};
    # an axis may add "stride": copy i is named start + i * stride (default 1)
    array: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "recipe": self.recipe,
            "params": self.params,
            "transform": {
                "translation": list(self.translation),
                "rotation_z_deg": self.rotation_z_deg,
            },
            "extent": [list(self.extent[0]), list(self.extent[1])],
            "floor": self.floor,
            "lod": list(self.lod),
            "tags": self.tags,
            "seed": self.seed,
        }
        if self.array is not None:
            d["array"] = self.array
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Element":
        return cls(
            id=d["id"],
            kind=d["kind"],
            recipe=d["recipe"],
            params=d["params"],
            translation=tuple(d["transform"]["translation"]),
            rotation_z_deg=d["transform"]["rotation_z_deg"],
            extent=(tuple(d["extent"][0]), tuple(d["extent"][1])),
            floor=d["floor"],
            lod=tuple(d["lod"]),
            tags=d["tags"],
            seed=d["seed"],
            array=d.get("array"),
        )

    @property
    def count(self) -> int:
        """How many copies this element stands for."""
        return math.prod(a["count"] for a in self.array["axes"]) if self.array else 1


@dataclass(frozen=True)
class Region:
    """A node of a facade's layer tree (docs/LAYERS.md): a rectangle of whole bays and floors
    on one face of a mass. The face is the root; it splits into panels (columns of bays) and
    bands (runs of floors). A leaf has a treatment, and the elements filling it carry its id
    in their `regions` tag. Regions hold no geometry: builders ignore them; checks, reviews and
    later rules read them as targets."""

    id: str  # stable path, e.g. ".../facade.south/panel.010/band.021"
    layer: str  # "face", "panel" or "band"
    parent: str | None  # None for a face
    mass: str
    facade: str  # outline edge name
    bays: tuple[int, int]  # [first, end) along the face
    floors: tuple[int, int]  # [first, end), building floors
    treatment: str | None = None  # leaves only: "cells", "portal"
    # size_m, height_m; faces: facing, standing, luxury, rhythm; panels: column; bands:
    # course; leaves: column, course, role, grade ("luxury" or "functional")
    tags: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer,
            "parent": self.parent,
            "mass": self.mass,
            "facade": self.facade,
            "bays": list(self.bays),
            "floors": list(self.floors),
            "treatment": self.treatment,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Region":
        return cls(
            id=d["id"],
            layer=d["layer"],
            parent=d["parent"],
            mass=d["mass"],
            facade=d["facade"],
            bays=tuple(d["bays"]),
            floors=tuple(d["floors"]),
            treatment=d["treatment"],
            tags=d["tags"],
        )


@dataclass(frozen=True)
class Plan:
    seed: int
    floor_height: float
    bay_width: float
    elements: tuple[Element, ...]
    style: dict = field(default_factory=dict)  # the spec's style section, which checks read
    regions: tuple[Region, ...] = ()  # every facade's layer tree, parents before children
    schema: str = PLAN_SCHEMA
    units: str = "m"

    def element(self, element_id: str) -> Element:
        return next(e for e in self.elements if e.id == element_id)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "units": self.units,
            "seed": self.seed,
            "floor_height": self.floor_height,
            "bay_width": self.bay_width,
            "style": self.style,
            "elements": [e.to_dict() for e in self.elements],
            "regions": [r.to_dict() for r in self.regions],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2) + "\n"

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        if d.get("schema") != PLAN_SCHEMA:
            raise ValueError(f"expected plan schema {PLAN_SCHEMA!r}, got {d.get('schema')!r}")
        return cls(
            seed=d["seed"],
            floor_height=d["floor_height"],
            bay_width=d["bay_width"],
            elements=tuple(Element.from_dict(e) for e in d["elements"]),
            style=d.get("style", {}),
            regions=tuple(Region.from_dict(r) for r in d.get("regions", [])),
            units=d["units"],
        )

    @classmethod
    def load(cls, path: str | Path) -> "Plan":
        return cls.from_dict(json.loads(Path(path).read_text()))


def element_key(e: Element, lod: str) -> str:
    """Library key: identical (recipe, params, LOD) share one mesh."""
    blob = json.dumps({"recipe": e.recipe, "params": e.params, "lod": lod}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def instances(plan: Plan, e: Element) -> Iterator[Element]:
    """The concrete elements `e` stands for: itself, or every copy of its array.

    Copies get ids from the array's prefix plus their grid position, seeds derived from
    those ids, the grid position as tags, and their own floor when an axis is "floor".
    """
    if e.array is None:
        yield e
        return
    prefix, axes = e.array["prefix"], e.array["axes"]
    prefix_seed = path_seed(plan.seed, prefix)
    for index in itertools.product(*(range(a["count"]) for a in axes)):
        positions = [a["start"] + i * a.get("stride", 1) for a, i in zip(axes, index, strict=True)]
        names = [f"{a['name']}.{p:0{a['digits']}d}" for a, p in zip(axes, positions, strict=True)]
        seed = prefix_seed
        for name in names:
            seed = derive_seed(seed, name)
        offset = [sum(i * a["step"][k] for a, i in zip(axes, index, strict=True)) for k in range(3)]
        grid = {a["name"]: p for a, p in zip(axes, positions, strict=True)}
        yield replace(
            e,
            id="/".join([prefix, *names]),
            translation=tuple(round(e.translation[k] + offset[k], 4) for k in range(3)),
            floor=grid.get("floor", e.floor),
            seed=seed,
            tags={**e.tags, **grid},
            array=None,
        )


def element_bounds(e: Element) -> tuple[Vec3, Vec3]:
    """World-space axis-aligned bounds of an element, covering every copy of an array."""
    a = math.radians(e.rotation_z_deg)
    c, s = math.cos(a), math.sin(a)
    (x0, y0, z0), (x1, y1, z1) = e.extent
    corners = [(x * c - y * s, x * s + y * c) for x in (x0, x1) for y in (y0, y1)]
    lo = [min(p[0] for p in corners), min(p[1] for p in corners), z0]
    hi = [max(p[0] for p in corners), max(p[1] for p in corners), z1]
    for axis in e.array["axes"] if e.array else []:
        for k in range(3):
            reach = (axis["count"] - 1) * axis["step"][k]
            lo[k] += min(0, reach)
            hi[k] += max(0, reach)
    return (
        tuple(round(lo[k] + e.translation[k], 4) for k in range(3)),
        tuple(round(hi[k] + e.translation[k], 4) for k in range(3)),
    )


def plan_bounds(plan: Plan) -> tuple[Vec3, Vec3]:
    """Bounds of the building's envelope (its masses)."""
    boxes = [element_bounds(e) for e in plan.elements if e.kind == "mass"]
    lo = tuple(min(b[0][i] for b in boxes) for i in range(3))
    hi = tuple(max(b[1][i] for b in boxes) for i in range(3))
    return lo, hi
