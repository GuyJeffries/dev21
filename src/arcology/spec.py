"""Arcology specification, schema v0: what the user edits, and the source of truth.

Fields marked "range" accept a number or [min, max]. The resolver draws a value inside
the range from the owning element's seed, so a spec describes a family of buildings and
the seed picks one member.

Loading is strict: unknown fields are errors (a typo must not be silently ignored),
missing fields take the defaults below, and `schema` must name this version.
"""

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

SCHEMA = "arcology-spec/0"

type Range = float | tuple[float, float]
type IntRange = int | tuple[int, int]


class SpecError(ValueError):
    """The spec doesn't match schema v0. The message names the offending field."""


def _number(*, integer=False, lo=None, hi=None):
    def check(v, path):
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise SpecError(f"{path}: expected a number, got {v!r}")
        if integer and not isinstance(v, int):
            raise SpecError(f"{path}: expected a whole number, got {v!r}")
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise SpecError(f"{path}: {v} is outside {lo}..{hi}")
        return v

    return check


def _range(*, integer=False, lo=None, hi=None):
    number = _number(integer=integer, lo=lo, hi=hi)

    def check(v, path):
        if isinstance(v, list | tuple):
            if len(v) != 2:
                raise SpecError(f"{path}: a range is [min, max], got {v!r}")
            a, b = number(v[0], f"{path}[0]"), number(v[1], f"{path}[1]")
            if a > b:
                raise SpecError(f"{path}: range min {a} is greater than max {b}")
            return (a, b)
        return number(v, path)

    return check


def _choice(*options):
    def check(v, path):
        if v not in options:
            raise SpecError(f"{path}: expected one of {', '.join(options)}, got {v!r}")
        return v

    return check


def _list(item, *, min_len=1):
    def check(v, path):
        if not isinstance(v, list | tuple) or len(v) < min_len:
            raise SpecError(f"{path}: expected a list of at least {min_len} item(s), got {v!r}")
        return tuple(item(x, f"{path}[{i}]") for i, x in enumerate(v))

    return check


def _f(default, check):
    return field(default=default, metadata={"check": check})


def _section(cls):
    return field(default_factory=cls, metadata={"section": cls})


@dataclass(frozen=True)
class Style:
    """The visual grammar's settings (docs/PLAN.md section 11). Each scales rules rather than
    picking assets; the tables they index live in rules.py and facade.py."""

    # Mirror twins share every decision; "none" lets them differ and leaves odd towers unpaired.
    symmetry: str = _f("bilateral", _choice("bilateral", "none"))
    # Vertical: continuous piers and pilasters. Horizontal: stone spandrel bands and glass ribbons.
    dominant_axis: str = _f("vertical", _choice("vertical", "horizontal"))
    # How far the central tower dominates: secondary heights and sizes, ornament spread.
    hierarchy: str = _f("strong", _choice("strong", "moderate", "weak"))
    ornament_density: float = _f(0.65, _number(lo=0, hi=1))  # the central tower's
    # How hard towers step back: the setback inset, and below that, fewer setbacks.
    setback_strength: str = _f("high", _choice("high", "medium", "low"))
    # Regular: one facade for the building. Varied: each tower group draws its own.
    repetition: str = _f("regular", _choice("regular", "varied"))
    termination: str = _f("stepped", _choice("stepped", "spire", "flat"))  # the central tower
    # How many luxury places take an exception (a treatment, docs/LAYERS.md), and how coarse:
    # 0 none, 1 every kind of place, favouring cuts (openings, recesses) over ornament.
    contrast: float = _f(0.5, _number(lo=0, hi=1))


@dataclass(frozen=True)
class PrimaryMass:
    form: str = _f("stepped_podium", _choice("stepped_podium"))
    width: Range = _f((480.0, 640.0), _range(lo=24))  # metres
    depth: Range = _f((480.0, 640.0), _range(lo=24))  # metres
    # Floors per tier, bottom first.
    tiers: tuple[IntRange, ...] = _f((6, (5, 7), (4, 6), (3, 5)), _list(_range(integer=True, lo=1)))
    # Fraction of the base width (and depth) each tier steps in, per side.
    tier_inset: Range = _f((0.05, 0.09), _range(lo=0, hi=0.24))
    # Share of the tier step cut from each corner of every tier but the top (re-entrant
    # corners stepping up the podium), in whole bays.
    corner_notch: Range = _f(0.0, _range(lo=0, hi=1))


@dataclass(frozen=True)
class CentralTower:
    width: Range = _f((90.0, 140.0), _range(lo=12))  # metres
    depth: Range = _f((90.0, 140.0), _range(lo=12))  # metres
    floors: IntRange = _f((90, 120), _range(integer=True, lo=2))  # above the podium
    # Floor of each setback, counted from the tower's base.
    setbacks: tuple[IntRange, ...] = _f(
        ((38, 46), (60, 70), (78, 88)), _list(_range(integer=True, lo=1), min_len=0)
    )
    # Fraction of the current width (and depth) removed per side at each setback.
    setback_inset: Range = _f((0.06, 0.12), _range(lo=0, hi=0.24))
    # Bays cut from every corner (re-entrant corners); never deeper than the setbacks.
    corner_notch: IntRange = _f(0, _range(integer=True, lo=0, hi=6))


@dataclass(frozen=True)
class SecondaryTowers:
    """Towers on the top podium tier, in lanes beside the central tower's faces.

    They come in mirror pairs, plus towers on the north-south axis for odd counts;
    `placement` sets which lane positions fill first. Each is bridged to the central tower.
    """

    count: IntRange = _f(0, _range(integer=True, lo=0, hi=9))
    placement: str = _f("radial", _choice("radial", "axial", "corners"))
    # Height above the podium as a share of the central tower's; later pairs step down.
    height_ratio: Range = _f((0.4, 0.7), _range(lo=0.05, hi=1))
    size: Range = _f((0.7, 1.0), _range(lo=0.1, hi=1))  # share of the room their lane allows
    gap: IntRange = _f((1, 3), _range(integer=True, lo=1, hi=10))  # bays from the central tower
    # Where the bridges and transfer band sit, as a share of the lowest base section's floors.
    bridge_level: Range = _f((0.45, 0.75), _range(lo=0.05, hi=0.95))
    # Bays cut from every corner, as for the central tower.
    corner_notch: IntRange = _f(0, _range(integer=True, lo=0, hi=4))


@dataclass(frozen=True)
class Facade:
    bay_width: float = _f(6.0, _number(lo=1, hi=30))  # the horizontal grid, for massing too
    window: str = _f("deco_tall", _choice("deco_tall"))
    # Glazed share of each bay and floor; the rest is stone frame and spandrel.
    density: Range = _f((0.6, 0.9), _range(lo=0, hi=1))
    pier_width: Range = _f((0.8, 1.2), _range(lo=0.2, hi=3))  # piers stand on every bay line
    # Every k-th bay line carries a full-depth pilaster, set out symmetrically from the
    # facade's centre; the piers between stand back. 0: every pier the same.
    pilaster_every: IntRange = _f((2, 4), _range(integer=True, lo=0, hi=12))
    pier_depth: float = _f(0.45, _number(lo=0.05, hi=2))  # how far piers stand proud
    window_recess: float = _f(0.3, _number(lo=0.05, hi=1.5))  # glazing set back in the frame
    mullions: IntRange = _f((1, 3), _range(integer=True, lo=0, hi=6))
    # Main entrance, centred on the podium's south facade.
    entrance_bays: IntRange = _f((3, 5), _range(integer=True, lo=1, hi=15))
    entrance_floors: IntRange = _f((2, 3), _range(integer=True, lo=1, hi=10))
    # Band rhythm (docs/LAYERS.md): shafts break into runs of this many floors between sky
    # lobbies this many floors tall, on one rhythm anchored at the transfer floor.
    band_run: IntRange = _f((8, 15), _range(integer=True, lo=4, hi=60))
    lobby_floors: IntRange = _f((1, 2), _range(integer=True, lo=1, hi=4))
    # The treatments luxury places may take (docs/LAYERS.md section 4); fewer for a plainer
    # family, one at a time for the what-if sheet.
    treatments: tuple[str, ...] = _f(
        ("field", "opening", "recess", "giant", "rich"),
        _list(_choice("field", "opening", "recess", "giant", "rich"), min_len=0),
    )


@dataclass(frozen=True)
class Program:
    """The programme split (docs/LAYERS.md): every facade region is luxury or functional.
    Composition places the luxury (axis, base, seams, then higher floors), and exceptions
    will go there; the functional rest stays calm, the ground the contrast reads against."""

    # Share of the facade area that is luxury, before each mass's standing scales it.
    luxury: Range = _f((0.15, 0.35), _range(lo=0, hi=1))


@dataclass(frozen=True)
class Spec:
    schema: str = _f(SCHEMA, _choice(SCHEMA))
    seed: int = _f(0, _number(integer=True, lo=0))
    units: str = _f("m", _choice("m"))
    floor_height: float = _f(4.0, _number(lo=2, hi=12))
    style: Style = _section(Style)
    primary_mass: PrimaryMass = _section(PrimaryMass)
    central_tower: CentralTower = _section(CentralTower)
    secondary_towers: SecondaryTowers = _section(SecondaryTowers)
    facade: Facade = _section(Facade)
    program: Program = _section(Program)


def _load(cls, data, path):
    if not isinstance(data, dict):
        raise SpecError(f"{path or 'spec'}: expected an object, got {data!r}")
    known = {f.name: f for f in fields(cls)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise SpecError(f"{path or 'spec'}: unknown field(s): {', '.join(unknown)}")
    values = {}
    for name, value in data.items():
        meta = known[name].metadata
        sub = f"{path}.{name}" if path else name
        if "section" in meta:
            values[name] = _load(meta["section"], value, sub)
        else:
            values[name] = meta["check"](value, sub)
    return cls(**values)


def spec_from_dict(data: dict) -> Spec:
    if isinstance(data, dict) and "schema" not in data:
        raise SpecError(f"schema: missing; expected {SCHEMA!r}")
    return _load(Spec, data, "")


def spec_to_dict(spec: Spec) -> dict:
    return json.loads(json.dumps(asdict(spec)))  # tuples -> lists, as written in JSON


def spec_with(spec: Spec, path: str, value) -> Spec:
    """`spec` with the field at a dotted path ("style.hierarchy") set to `value`, validated
    as if loaded from JSON."""
    data = spec_to_dict(spec)
    *parents, name = path.split(".")
    node = data
    for part in parents:
        if not isinstance(node.get(part), dict):
            raise SpecError(f"{path}: {part!r} is not a section")
        node = node[part]
    if name not in node:
        raise SpecError(f"{path}: unknown field {name!r}")
    node[name] = value
    return spec_from_dict(data)


def load_spec(path: str | Path) -> Spec:
    return spec_from_dict(json.loads(Path(path).read_text()))
