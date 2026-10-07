"""Composition rules (Phase 2): secondary towers, bridges, transfer bands, crowns, parapets.

Plain Python. Secondary towers stand in rings, in mirror pairs (plus towers on the
north-south axis for odd counts) so the building stays bilaterally symmetric:

- Ring 0: sister towers beside the central tower's faces on the top podium tier, at most
  one per face so they can be substantial. They bridge to the central tower.
- Ring r (r >= 1): pavilion towers on the terrace r tiers down, beside the ends of the next
  tier's walls. They bridge into that wall.

Sizes come from the room the central tower and the podium leave; heights are a share of
the central tower's, falling off ring by ring; outer-ring pavilions fill their terrace
but stay squat and stand lower, so the building builds up towards the central spire.
Setbacks follow the central tower's rhythm.
The central building constrains the towers, never the reverse.

Ring 0's bridges, and the transfer bands under them, share one floor: a horizontal datum
tying the sister towers to the central tower. Every tower ends in a crown; only the central
tower takes the style's termination (a spire, by default), which keeps the hierarchy clear.
"""

import math
from dataclasses import dataclass

from arcology.plan import Element
from arcology.rules import (
    DETAIL,
    EVERY_LEVEL,
    ROOT,
    STRUCTURE,
    ResolveError,
    bays,
    box_extent,
    mass,
    rnd,
    sample,
)
from arcology.seeds import derive_seed, path_seed
from arcology.spec import Spec

TOWERS = f"{ROOT}/towers"

INNER = ("east.mid", "west.mid")
AXIS = {"north.mid": 0, "south.mid": 1}  # single towers, in the order they're used: rank


def _ring(r: int) -> list[tuple[str, str]]:
    """Mirror pairs on the terrace r tiers below the top, beside the next tier's wall ends."""
    return [
        (f"t{r}.east.north", f"t{r}.west.north"),
        (f"t{r}.east.south", f"t{r}.west.south"),
        (f"t{r}.north.east", f"t{r}.north.west"),
    ]


# Mirror pairs in the order they fill, per placement.
PAIRS = {
    "radial": [INNER, *_ring(1), *_ring(2)],
    "corners": [*_ring(1), INNER, *_ring(2)],
    "axial": [INNER, _ring(1)[2], _ring(1)[0], _ring(1)[1], *_ring(2)],
}
FACE_ROTATION = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}

RANK_FALLOFF = 0.12  # each rank (ring) of tower is this much shorter, as a share
PAVILION_SHARE = 0.45  # outer-ring pavilions are this share of a sister tower's height
PAVILION_SLENDERNESS = 3.0  # and at most this many times as tall as they are wide
SETBACK_AT = 0.72  # secondary towers step in once, this far up
BRIDGE_FLOORS = 2
BRIDGE_SLAB = 0.6
BRIDGE_FIN = 0.2  # bronze fins outside the bridge glazing
BRIDGE_KEEL = (0.8, 0.6)  # stepped keel under the deck: upper step, lower step
BAND_PROJECTION = 0.5
PARAPET_HEIGHT, PARAPET_THICKNESS = 1.2, 0.4
CROWN_TIER_FLOORS = 1.5


@dataclass(frozen=True)
class Slot:
    name: str
    ring: int  # 0: beside the central tower; r: on the terrace r tiers below the top
    side: str  # which face of its anchor it stands beside
    pos: int  # along that face: 0 centred, +1 the north or east end, -1 the south or west end

    @classmethod
    def parse(cls, name: str) -> "Slot":
        parts = name.split(".")
        ring = int(parts[0][1:]) if parts[0].startswith("t") else 0
        side, end = parts[-2:]
        return cls(
            name, ring, side, {"mid": 0, "north": 1, "east": 1, "south": -1, "west": -1}[end]
        )

    @property
    def rank(self) -> int:
        return AXIS.get(self.name, self.ring)


@dataclass(frozen=True)
class Tower:
    id: str
    slot: Slot | None  # None for the central tower
    sections: tuple[Element, ...]
    seed: int  # seed for decisions mirror twins must share (crowns)
    anchor: Element | None = None  # the mass it bridges to


def _groups(count: int, placement: str, available) -> list[tuple[str, ...]]:
    """Slot groups for `count` towers: an axis tower first if the count is odd, then pairs.
    Groups whose ring has no room are skipped."""
    groups: list[tuple[str, ...]] = []
    axis = [a for a in AXIS if available(Slot.parse(a))]
    if count % 2 and axis:
        groups.append((axis.pop(0),))
    for pair in PAIRS[placement]:
        if count - sum(map(len, groups)) >= 2 and available(Slot.parse(pair[0])):
            groups.append(pair)
    while sum(map(len, groups)) < count and axis:
        groups.append((axis.pop(0),))
    if sum(map(len, groups)) != count:
        raise ResolveError(
            f"{TOWERS}: no room for {count} towers ({placement}); "
            "reduce the count or widen the podium"
        )
    return groups


def secondary_towers(spec: Spec, podium: list[Element], central: tuple[Element, ...], inset: float):
    """Secondary towers in rings around the central tower (see the module docstring)."""
    st, fh, bay = spec.secondary_towers, spec.floor_height, spec.facade.bay_width
    ts = path_seed(spec.seed, TOWERS)
    count = sample(st.count, ts, "count", integer=True)
    if count == 0:
        return []
    base, top = central[0], podium[-1]
    cw, cd = base.params["width"], base.params["depth"]
    share = sample(st.size, ts, "size")

    def fit(room: float) -> float:
        """Share of the room in whole bays; never below 2 bays if the room allows 2."""
        if room < 2 * bay:
            return 0.0
        return max(2 * bay, math.floor(share * room / bay + 1e-9) * bay)

    # Ring 0: the widest gap (up to the drawn one) that still leaves room for a 2-bay tower.
    inner_size, gap = 0.0, 0.0
    for g in range(sample(st.gap, ts, "gap", integer=True), 0, -1):
        room = min(
            top.params["width"] / 2 - bay - cw / 2 - g * bay,
            top.params["depth"] / 2 - bay - cd / 2 - g * bay,
            min(cw, cd) - 2 * bay,
        )
        if fit(room) >= 2 * bay:
            inner_size, gap = fit(room), g * bay
            break
    # Outer rings: the terrace between two tiers, less a bay of margin each side.
    terrace = [
        (podium[k].params["width"] - podium[k + 1].params["width"]) / 2
        for k in range(len(podium) - 1)
    ] + [
        (podium[k].params["depth"] - podium[k + 1].params["depth"]) / 2
        for k in range(len(podium) - 1)
    ]
    # Pavilions fill their terrace (less the margins), whatever the size share.
    outer_room = min(terrace) - 2 * bay if terrace else 0.0
    outer_size = math.floor(outer_room / bay + 1e-9) * bay if outer_room >= 2 * bay else 0.0

    def available(slot: Slot) -> bool:
        if slot.ring == 0:
            return inner_size >= 2 * bay
        return slot.ring < len(podium) and outer_size >= 2 * bay

    central_floors = sum(round(s.params["height"] / fh) for s in central)
    towers = []
    for group in _groups(count, st.placement, available):
        slot0 = Slot.parse(group[0])
        gseed = derive_seed(ts, group[0])
        ratio = sample(st.height_ratio, gseed, "height_ratio") * (1 - RANK_FALLOFF * slot0.rank)
        floors = max(4, round(ratio * central_floors))
        if slot0.ring:  # pavilions: lower, and never more than PAVILION_SLENDERNESS x wide
            cap = round(PAVILION_SLENDERNESS * outer_size / fh)
            floors = max(4, min(round(ratio * PAVILION_SHARE * central_floors), cap))
        for name in group:
            slot = Slot.parse(name)
            if slot.ring == 0:
                anchor, stands_on, size, offset = base, top, inner_size, gap
            else:
                k = len(podium) - 1 - slot.ring
                anchor, stands_on, size = podium[k + 1], podium[k], outer_size
                offset = None  # centred on the terrace
            towers.append(_tower(spec, slot, gseed, size, floors, anchor, stands_on, offset, inset))
    return towers


def _tower(spec, slot, gseed, size, floors, anchor, stands_on, gap, inset) -> Tower:
    """A tower beside `anchor`'s `slot.side` face, standing on `stands_on`'s roof."""
    fh, bay = spec.floor_height, spec.facade.bay_width
    tid = f"{ROOT}/tower.{slot.name}"
    seed = path_seed(spec.seed, tid)
    aw, ad = anchor.params["width"], anchor.params["depth"]
    if gap is None:  # centred on the terrace between `stands_on` and `anchor`
        out_x = (stands_on.params["width"] - aw) / 4 - size / 2
        out_y = (stands_on.params["depth"] - ad) / 4 - size / 2
    else:
        out_x = out_y = gap
    if slot.side in ("east", "west"):
        x = (1 if slot.side == "east" else -1) * (aw / 2 + out_x + size / 2)
        y = slot.pos * (ad / 2 - size / 2)
    else:
        x = slot.pos * (aw / 2 - size / 2)
        y = (1 if slot.side == "north" else -1) * (ad / 2 + out_y + size / 2)
    step = bays(inset * size, bay)
    marks = [0, floors]
    if floors >= 10 and size - 2 * step >= bay:
        marks = [0, round(SETBACK_AT * floors), floors]
    base_floor = stands_on.floor + round(stands_on.params["height"] / fh)
    tags = {"role": "tower", "tower": tid, "rank": slot.rank, "stands_on": stands_on.id}
    sections, w = [], size
    for k in range(len(marks) - 1):
        if k:
            w -= 2 * step
        start, count = base_floor + marks[k], marks[k + 1] - marks[k]
        sseed = derive_seed(seed, f"section.{k}")
        sections.append(mass(f"{tid}/section.{k}", sseed, w, w, start, count, fh, tags, x, y))
    return Tower(tid, slot, tuple(sections), gseed, anchor)


def _crown(spec: Spec, tower: Tower) -> Element:
    fh = spec.floor_height
    top = tower.sections[-1]
    W, D, H = top.params["width"], top.params["depth"], top.params["height"]
    x, y, z = top.translation
    central = tower.slot is None
    termination = spec.style.termination if central else "stepped"
    cseed = derive_seed(tower.seed, "crown")
    common = {
        "id": f"{tower.id}/crown",
        "kind": "crown",
        "translation": (x, y, rnd(z + H)),
        "floor": top.floor + round(H / fh),
        "seed": cseed,
        "lod": EVERY_LEVEL,
        "tags": {"role": "crown", "tower": tower.id},
    }
    if termination == "flat":
        t = PARAPET_THICKNESS
        params = {
            "width": W,
            "depth": D,
            "inner_width": rnd(W - 2 * t),
            "inner_depth": rnd(D - 2 * t),
            "height": PARAPET_HEIGHT,
        }
        return Element(
            recipe="parapet.ring", params=params, extent=box_extent(W, D, PARAPET_HEIGHT), **common
        )
    tiers = sample((3, 4) if central else (2, 3), cseed, "tiers", integer=True)
    tier_height = rnd(CROWN_TIER_FLOORS * fh)
    step = rnd(min(W, D) / (2 * (tiers + 1.5)))
    tower_height = sum(s.params["height"] for s in tower.sections)
    spire = (
        rnd(sample((0.12, 0.2), cseed, "spire") * tower_height) if termination == "spire" else 0.0
    )
    params = {
        "width": W,
        "depth": D,
        "tiers": tiers,
        "tier_height": tier_height,
        "step": step,
        "spire_height": spire,
        "spire_width": rnd(max(1.0, min(W, D) * 0.04)),
    }
    extent = (
        (rnd(-W / 2 + step), rnd(-D / 2 + step), 0.0),
        (rnd(W / 2 - step), rnd(D / 2 - step), rnd(tiers * tier_height + spire)),
    )
    return Element(recipe="crown.stepped", params=params, extent=extent, **common)


def _band(spec: Spec, tower: Tower, floor: int) -> Element:
    """A stone band course round the tower, one floor tall, just under the bridges."""
    base, p, fh = tower.sections[0], BAND_PROJECTION, spec.floor_height
    W, D = base.params["width"], base.params["depth"]
    x, y, _ = base.translation
    params = {
        "width": rnd(W + 2 * p),
        "depth": rnd(D + 2 * p),
        "inner_width": W,
        "inner_depth": D,
        "height": rnd(fh),
    }
    return Element(
        id=f"{tower.id}/band",
        kind="band",
        recipe="band.ring",
        params=params,
        translation=(x, y, rnd(floor * fh)),
        extent=box_extent(W + 2 * p, D + 2 * p, fh),
        floor=floor,
        seed=derive_seed(tower.seed, "band"),
        lod=STRUCTURE,
        tags={"role": "band", "tower": tower.id},
    )


def _bridge(spec: Spec, tower: Tower, floor: int) -> Element:
    """An enclosed gallery straight across the gap from `tower`'s anchor to `tower`."""
    fh, bay = spec.floor_height, spec.facade.bay_width
    a, s, side = tower.anchor, tower.sections[0], tower.slot.side
    sx, sy, _ = s.translation
    half = s.params["width"] / 2
    if side in ("east", "west"):
        sign = 1 if side == "east" else -1
        origin, span = (sign * a.params["width"] / 2, sy), abs(sx) - half - a.params["width"] / 2
    else:
        sign = 1 if side == "north" else -1
        origin, span = (sx, sign * a.params["depth"] / 2), abs(sy) - half - a.params["depth"] / 2
    width = max(bay, min(2 * bay, s.params["width"] - bay))
    height = BRIDGE_FLOORS * fh
    params = {
        "span": rnd(span),
        "width": rnd(width),
        "height": rnd(height),
        "slab": BRIDGE_SLAB,
        "fin": BRIDGE_FIN,
        "keel": list(BRIDGE_KEEL),
        "band": BAND_PROJECTION,
    }
    eid = f"{ROOT}/bridge.{tower.slot.name}"
    return Element(
        id=eid,
        kind="bridge",
        recipe="bridge.gallery",
        params=params,
        translation=(rnd(origin[0]), rnd(origin[1]), rnd(floor * fh)),
        rotation_z_deg=FACE_ROTATION[side],
        extent=(
            (rnd(-width / 2 - BRIDGE_FIN), rnd(-span), rnd(-sum(BRIDGE_KEEL))),
            (rnd(width / 2 + BRIDGE_FIN), 0.0, rnd(height)),
        ),
        floor=floor,
        seed=path_seed(spec.seed, eid),
        lod=STRUCTURE,
        tags={"role": "bridge", "from": a.id, "to": s.id},
    )


def _parapet(m: Element, fh: float) -> Element:
    """A low wall round the edge of a roof terrace."""
    W, D, H = m.params["width"], m.params["depth"], m.params["height"]
    x, y, z = m.translation
    t = PARAPET_THICKNESS
    params = {
        "width": W,
        "depth": D,
        "inner_width": rnd(W - 2 * t),
        "inner_depth": rnd(D - 2 * t),
        "height": PARAPET_HEIGHT,
    }
    return Element(
        id=f"{m.id}/parapet",
        kind="parapet",
        recipe="parapet.ring",
        params=params,
        translation=(x, y, rnd(z + H)),
        extent=box_extent(W, D, PARAPET_HEIGHT),
        floor=m.floor + round(H / fh),
        seed=derive_seed(m.seed, "parapet"),
        lod=DETAIL,
        tags={"role": "parapet"},
    )


def composition(spec: Spec, podium, central: Tower, towers: list[Tower]) -> list[Element]:
    """Crowns and parapets; with secondary towers, their bridges and transfer bands."""
    fh = spec.floor_height
    everyone = [central, *towers]
    out = [_crown(spec, t) for t in everyone]
    tops = {t.sections[-1].id for t in everyone}
    for m in [*podium, *(s for t in everyone for s in t.sections)]:
        if m.id not in tops:
            out.append(_parapet(m, fh))

    # Ring 0: every bridge to the central tower on one shared floor, with a band below.
    inner = [t for t in towers if t.slot.ring == 0]
    if inner:
        cluster = [central, *inner]
        lowest = min(round(t.sections[0].params["height"] / fh) for t in cluster)
        if lowest < BRIDGE_FLOORS + 1:
            raise ResolveError(f"{TOWERS}: {lowest}-floor base sections are too short for bridges")
        level = sample(
            spec.secondary_towers.bridge_level, path_seed(spec.seed, TOWERS), "bridge_level"
        )
        datum = central.sections[0].floor + min(
            lowest - BRIDGE_FLOORS, max(1, round(level * lowest))
        )
        out += [_band(spec, t, datum - 1) for t in cluster]
        out += [_bridge(spec, t, datum) for t in inner]

    # Outer rings: into the wall of the tier above, halfway up it (and at least a floor up,
    # so the keel clears the terrace).
    for t in towers:
        if t.slot.ring:
            wall = round(t.anchor.params["height"] / fh)
            if wall < BRIDGE_FLOORS + 1:
                raise ResolveError(f"{t.anchor.id}: {wall} floors is too low to bridge into")
            out.append(_bridge(spec, t, t.anchor.floor + max(1, (wall - BRIDGE_FLOORS) // 2)))
    return out
