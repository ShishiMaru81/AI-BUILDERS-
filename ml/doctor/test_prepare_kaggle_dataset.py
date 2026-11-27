from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from prepare_kaggle_dataset import cache_bytes, choose_candidates, exclude_duplicates, read_groups


def source_path(name):
    return f"raw/color/Potato___healthy/id___{name}.JPG"


def test_group_resolution_and_validation_only_use_official_training_leaves():
    label = "Potato___healthy"
    paths = {
        "train": [source_path(name) for name in ("A", "A copy", "B", "C", "D", "unknown")]
        + [source_path("unknown").replace(".JPG", ".jpeg")],
        "test": [source_path("E")],
    }
    leaf_map = {name.lower(): [f"{label}:::{name}"] for name in "ABCDE"}
    leaf_map["unknown"] = [f"{label}:::F", f"{label}:::G"]

    groups, inventory = read_groups(paths, leaf_map)
    candidates = choose_candidates(groups, seed=42)

    assert inventory[("train", label)]["unresolved_images"] == 2
    assert {item.split for item in candidates if item.leaf_id == f"{label}:::E"} == {"test"}
    assert all(item.leaf_id != f"{label}:::F" for item in candidates)
    assert sum(item.split == "val" for item in candidates) == 1
    assert all(
        len({item.split for item in candidates if item.leaf_id == leaf_id}) == 1
        for leaf_id in {item.leaf_id for item in candidates}
    )


def test_official_cross_split_group_fails_closed():
    paths = {"train": [source_path("a")], "test": [source_path("b")]}
    leaf_map = {name: ["Potato___healthy:::1"] for name in "ab"}
    with pytest.raises(ValueError, match="both official folds"):
        read_groups(paths, leaf_map)


def test_duplicates_cannot_appear_under_two_groups_or_splits():
    def inspected(name, split, leaf_id, sha256, pixel_sha256, dhash):
        return SimpleNamespace(
            candidate=SimpleNamespace(path=name, split=split, leaf_id=leaf_id),
            sha256=sha256,
            pixel_sha256=pixel_sha256,
            dhash=dhash,
        )

    test = inspected("held-out", "test", "A", "same-file", "same-pixels", 0)
    exact_file = inspected("encoded", "train", "B", "same-file", "other-b", 31)
    exact_pixels = inspected("decoded", "train", "C", "other-file", "same-pixels", 255)
    near = inspected("near", "val", "D", "other-d", "other-d", 3)
    retained = inspected("distinct", "train", "E", "other-e", "other-e", 1023)
    kept, rejected = exclude_duplicates([exact_file, exact_pixels, near, test, retained])

    assert kept == [test, retained]
    assert {row["reason"] for row in rejected} == {"encoded_exact", "decoded_exact", "dhash_near"}


def test_concurrent_runs_can_cache_the_same_pinned_bytes(tmp_path):
    path = tmp_path / "photo.jpg"
    contents = b"downloaded image bytes"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: cache_bytes(path, contents), range(32)))

    assert path.read_bytes() == contents
    assert list(tmp_path.iterdir()) == [path]
