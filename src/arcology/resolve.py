"""The grammar: spec -> resolved plan. Plain Python, no Blender.

Massing: a stepped podium and a central tower with setbacks (Phase 0), then secondary
towers beside it (Phase 2, compose.py); towers may have notched corners (Phase 3). Each
mass is then dressed with its facades (facade.py): corners, pilasters and piers, windows by
zone, portals, a cornice and ornament. Composition elements (crowns, bridges, transfer
bands, parapets) come last, from compose.py.

Every value drawn from a spec range comes from the owning element's seed (see seeds.py),
and every dimension sits on the grids: heights in whole floors, widths in whole bays.

Representation levels (docs/PLAN.md section 13): the envelope box is L3; the core it
wraps, the piers, corners and cornices are L0-L2; windows, portals and merlons are L0-L1.
"""

import math
from dataclasses import asdict

from arcology.compose import Tower, composition, secondary_towers
from arcology.facade import Portal, dress, entrance_size, facade_system, facade_variant
from arcology.plan import Element, Plan, Region
from arcology.rules import ROOT, SETBACK_STRENGTH, ResolveError, bays, mass, notch_for, sample
from arcology.seeds import derive_seed, path_seed
from arcology.spec import Spec

__all__ = ["ResolveError", "resolve", "sample"]


def _podium(spec: Spec) -> list[Element]:
    """Stepped podium: each tier steps in by the same whole number of bays per side. Every
    tier but the top may have the same notch cut from its corners; no deeper than a tier
    step, so each tier's corners clear the notches below and the top tier stays whole for
    the towers."""
    fh, bay = spec.floor_height, spec.facade.bay_width
    pid = f"{ROOT}/podium"
    ps = path_seed(spec.seed, pid)
    pm = spec.primary_mass
    base_w = bays(sample(pm.width, ps, "width"), bay)
    base_d = bays(sample(pm.depth, ps, "depth"), bay)
    inset = sample(pm.tier_inset, ps, "tier_inset")
    step_w, step_d = bays(inset * base_w, bay), bays(inset * base_d, bay)
    sizes = [(base_w - 2 * i * step_w, base_d - 2 * i * step_d) for i in range(len(pm.tiers))]
    for i, (w, d) in enumerate(sizes):
        if w < bay or d < bay:
            raise ResolveError(
                f"{pid}/tier.{i}: podium steps in to nothing; reduce tier_inset or tiers"
            )
    notch = 0.0
    if len(sizes) > 1:
        step = min(step_w, step_d)
        wanted = math.floor(sample(pm.corner_notch, ps, "corner_notch") * step / bay + 1e-9)
        notch = notch_for(wanted, bay, [step], min(sizes[-2]))
    tiers, floor = [], 0
    for i, (tier, (w, d)) in enumerate(zip(pm.tiers, sizes, strict=True)):
        ts = derive_seed(ps, f"tier.{i}")
        floors = sample(tier, ts, "floors", integer=True)
        cut = notch if i < len(sizes) - 1 else 0.0
        tiers.append(
            mass(f"{pid}/tier.{i}", ts, w, d, floor, floors, fh, {"role": "podium"}, notch=cut)
        )
        floor += floors
    return tiers


def _central(spec: Spec, top_tier: Element) -> tuple[Tower, float]:
    """Central tower on the top tier, with a bay of terrace on every side, stepping in at
    each setback floor. Returns the tower and its setback inset, which secondary towers share."""
    fh, bay = spec.floor_height, spec.facade.bay_width
    cid = f"{ROOT}/tower.central"
    cs = path_seed(spec.seed, cid)
    ct = spec.central_tower
    top_w, top_d = top_tier.params["width"], top_tier.params["depth"]
    base_floor = top_tier.floor + round(top_tier.params["height"] / fh)
    w = bays(sample(ct.width, cs, "width"), bay)
    d = bays(sample(ct.depth, cs, "depth"), bay)
    floors = sample(ct.floors, cs, "floors", integer=True)
    strength = SETBACK_STRENGTH[spec.style.setback_strength]
    inset = sample(ct.setback_inset, cs, "setback_inset") * strength.inset
    setbacks = [
        sample(s, derive_seed(cs, f"setback.{k}"), "floor", integer=True)
        for k, s in enumerate(ct.setbacks)
    ]
    if setbacks != sorted(set(setbacks)) or any(not 0 < s < floors for s in setbacks):
        raise ResolveError(
            f"{cid}: setbacks {setbacks} must rise strictly between floor 1 and {floors - 1}"
        )
    setbacks = setbacks[:: strength.every]
    if w > top_w - 2 * bay or d > top_d - 2 * bay:
        raise ResolveError(
            f"{cid}: a {w:g} x {d:g} m tower doesn't fit on the {top_w:g} x {top_d:g} m "
            "top podium tier with a bay of terrace on each side"
        )
    marks = [0, *setbacks, floors]
    sizes, steps = [], []
    for k in range(len(marks) - 1):
        if k:
            sw, sd = bays(inset * w, bay), bays(inset * d, bay)
            w, d = w - 2 * sw, d - 2 * sd
            steps += [sw, sd]
            if w < bay or d < bay:
                raise ResolveError(
                    f"{cid}/section.{k}: tower steps in to nothing; reduce setback_inset"
                )
        sizes.append((w, d))
    wanted = sample(ct.corner_notch, cs, "corner_notch", integer=True)
    notch = notch_for(wanted, bay, steps, min(min(sz) for sz in sizes))
    sections = []
    for k, (w, d) in enumerate(sizes):
        sseed = derive_seed(cs, f"section.{k}")
        start, count = base_floor + marks[k], marks[k + 1] - marks[k]
        tags = {"role": "tower", "tower": cid, "stands_on": top_tier.id}
        sections.append(
            mass(f"{cid}/section.{k}", sseed, w, d, start, count, fh, tags, notch=notch)
        )
    return Tower(cid, None, tuple(sections), cs), inset


def resolve(spec: Spec) -> Plan:
    """Massing first (podium, central tower, secondary towers), then facades, then the
    composition elements tying the towers together. Later steps read earlier decisions but
    never change them."""
    podium = _podium(spec)
    central, inset = _central(spec, podium[-1])
    towers = secondary_towers(spec, podium, central.sections, inset)

    fac = facade_system(spec)
    entrance = entrance_size(spec, podium[0], fac)
    portals = {podium[0].id: (Portal("entrance", "south", *entrance),)}
    # A door at the foot of each tower's outer faces, onto the terrace it stands on.
    portals[central.sections[0].id] = tuple(
        Portal("door", side, None, 1) for side in ("south", "north")
    )
    for t in towers:
        portals[t.sections[0].id] = (Portal("door", t.slot.side, None, 1),)
    # Varied repetition: each tower group (twins together) has its own facade; the podium
    # and central tower keep the building's.
    facades = {}
    if spec.style.repetition == "varied":
        for t in towers:
            facades |= {s.id: facade_variant(spec, fac, t.seed) for s in t.sections}
    tops = {t.sections[-1].id for t in (central, *towers)}
    masses = [*podium, *central.sections, *(s for t in towers for s in t.sections)]
    elements: list[Element] = []
    regions: list[Region] = []
    for m in masses:
        elements.append(m)
        dressed, tree = dress(
            m,
            facades.get(m.id, fac),
            portals=portals.get(m.id, ()),
            base=entrance[1] if m is podium[0] else 0,
            parapet=m.id not in tops,
        )
        elements += dressed
        regions += tree
    elements.extend(composition(spec, podium, central, towers))
    return Plan(
        seed=spec.seed,
        floor_height=spec.floor_height,
        bay_width=spec.facade.bay_width,
        elements=tuple(elements),
        style=asdict(spec.style),
        regions=tuple(regions),
    )
