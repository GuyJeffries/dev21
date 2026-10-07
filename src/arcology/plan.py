"""Resolved plan: every element placed, identified and tagged.

Produced by the resolver and consumed by builders. An element's translation is the
centre of its base, so library meshes are built centred in X/Y with their base on z=0.
Plain Python, no Blender.
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

PLAN_SCHEMA = "arcology-plan/0"
LODS = ("L0", "L1", "L2", "L3")


@dataclass(frozen=True)
class Element:
    id: str  # stable path, e.g. "arcology/tower.central/section.2"
    kind: str  # "mass", later "window", "door", "asset_slot", ...
    recipe: str  # builder recipe, e.g. "mass.box"
    params: dict  # recipe parameters, metres
    translation: tuple[float, float, float]  # base centre
    floor: int  # floor index of the element's base
    seed: int
    rotation_z_deg: float = 0.0
    lod: tuple[str, ...] = LODS
    tags: dict = field(default_factory=dict)  # "role"; reserved: "program", "provision"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "recipe": self.recipe,
            "params": self.params,
            "transform": {
                "translation": list(self.translation),
                "rotation_z_deg": self.rotation_z_deg,
            },
            "floor": self.floor,
            "lod": list(self.lod),
            "tags": self.tags,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Element":
        return cls(
            id=d["id"],
            kind=d["kind"],
            recipe=d["recipe"],
            params=d["params"],
            translation=tuple(d["transform"]["translation"]),
            rotation_z_deg=d["transform"]["rotation_z_deg"],
            floor=d["floor"],
            lod=tuple(d["lod"]),
            tags=d["tags"],
            seed=d["seed"],
        )


@dataclass(frozen=True)
class Plan:
    seed: int
    floor_height: float
    bay_width: float
    elements: tuple[Element, ...]
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
            "elements": [e.to_dict() for e in self.elements],
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
            units=d["units"],
        )

    @classmethod
    def load(cls, path: str | Path) -> "Plan":
        return cls.from_dict(json.loads(Path(path).read_text()))


def element_bounds(e: Element) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Axis-aligned bounds of a base-centred element with width/depth/height params."""
    w, d, h = e.params["width"], e.params["depth"], e.params["height"]
    a = math.radians(e.rotation_z_deg)
    hx = abs(w / 2 * math.cos(a)) + abs(d / 2 * math.sin(a))
    hy = abs(w / 2 * math.sin(a)) + abs(d / 2 * math.cos(a))
    x, y, z = e.translation
    return (x - hx, y - hy, z), (x + hx, y + hy, z + h)


def plan_bounds(plan: Plan) -> tuple[tuple[float, ...], tuple[float, ...]]:
    boxes = [element_bounds(e) for e in plan.elements]
    lo = tuple(min(b[0][i] for b in boxes) for i in range(3))
    hi = tuple(max(b[1][i] for b in boxes) for i in range(3))
    return lo, hi
