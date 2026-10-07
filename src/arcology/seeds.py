"""Per-element seeds derived from ID paths.

An element's seed comes from its parent's seed and its own name, so changing one part
of a building never reshuffles another part, and re-seeding a subtree only affects that
subtree. The hash is blake2b, never Python's hash() (randomised per process).
"""

import hashlib
import random


def derive_seed(parent: int, name: str) -> int:
    """Child seed for `name` under `parent`. 63 bits, so it fits a signed 64-bit int."""
    digest = hashlib.blake2b(f"{parent}/{name}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") >> 1


def path_seed(root: int, path: str) -> int:
    """Seed of the element at `path` (e.g. "arcology/tower.central/section.2")."""
    seed = root
    for part in path.split("/"):
        seed = derive_seed(seed, part)
    return seed


def rng(seed: int, name: str) -> random.Random:
    """A random stream for one named decision belonging to the element with `seed`."""
    return random.Random(derive_seed(seed, name))


# Fixed seeds rendered on every pull request, so before/after sheets are comparable.
GOLDEN_SEEDS = (11, 23, 37, 41, 53, 67, 71, 89, 97, 101, 113, 127)
