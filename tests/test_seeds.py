from arcology.seeds import derive_seed, path_seed, rng


def test_seed_values_are_pinned():
    # Changing these silently changes every building ever generated; fail loudly instead.
    assert derive_seed(1, "arcology") == 6876335944355976868
    assert path_seed(42, "arcology/tower.central") == 2380284579366868374


def test_path_seed_chains_derive_seed():
    assert path_seed(7, "a/b/c") == derive_seed(derive_seed(derive_seed(7, "a"), "b"), "c")


def test_seeds_fit_signed_64_bit_and_differ_by_name():
    seeds = {derive_seed(s, name) for s in range(50) for name in ("width", "depth", "floors")}
    assert len(seeds) == 150
    assert all(0 <= s < 2**63 for s in seeds)


def test_rng_streams_are_independent_of_call_order():
    a = rng(5, "width").random()
    rng(5, "depth").random()
    assert rng(5, "width").random() == a
