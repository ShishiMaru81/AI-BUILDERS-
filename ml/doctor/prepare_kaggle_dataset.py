"""Prepare the pinned PlantVillage tomato/potato RGB baseline without training."""

import argparse
import csv
import hashlib
import io
import json
import shutil
import ssl
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from PIL import Image, __version__ as pillow_version


HF_REVISION = "9e97599868962bd0079b8db4b7f1efa9185fa1e7"
GITHUB_REVISION = "7f7ecc7e1eaca78107e3affe7cb5abd9427e139a"
HF_REPOSITORY = "https://huggingface.co/datasets/mohanty/PlantVillage"
GITHUB_REPOSITORY = "https://github.com/spMohanty/PlantVillage-Dataset"
SOURCE_ID = "plantvillage_original_rgb"
DEFAULT_WORK = Path("work/agrodoctor-kaggle")
METADATA_HASHES = {
    "README.md": "9fbe34695a3f05583f47345e5174383226ecee9e7af9e21d979307771b2362fb",
    "leaf_grouping/leaf-map.json": "3b4b253683c6911744959a3870a92509b1faa1ee34e9f8585e21d0fe6337a25b",
    "splits/color_train.txt": "c43e0205b321d1c929116f5df1842348ac1e5c4861306e081416785d3c439dbd",
    "splits/color_test.txt": "7a7257dcb5f9456feae6ae81248d29c28f45dc4cd41a00c13a5c5c198c5f2f8b",
}
LABELS = {
    "Potato___Early_blight": ("potato", "early_blight"),
    "Potato___Late_blight": ("potato", "late_blight"),
    "Potato___healthy": ("potato", "healthy"),
    "Tomato___Bacterial_spot": ("tomato", "bacterial_spot"),
    "Tomato___Early_blight": ("tomato", "early_blight"),
    "Tomato___Late_blight": ("tomato", "late_blight"),
    "Tomato___Leaf_Mold": ("tomato", "leaf_mold"),
    "Tomato___Septoria_leaf_spot": ("tomato", "septoria_leaf_spot"),
    "Tomato___healthy": ("tomato", "healthy"),
}
MANIFEST_FIELDS = (
    "path", "crop", "plant_part", "label", "source_id", "farm_id", "plant_id",
    "group_id", "split", "sha256", "label_evidence",
)


@dataclass(frozen=True)
class Candidate:
    path: str
    source_label: str
    leaf_id: str
    split: str


@dataclass(frozen=True)
class Inspected:
    candidate: Candidate
    cache_path: Path
    sha256: str
    pixel_sha256: str
    dhash: int


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def fetch_public(url, context):
    for attempt in range(4):
        try:
            with urlopen(url, timeout=30, context=context) as response:
                return response.read()
        except (URLError, TimeoutError, OSError):
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def cache_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False)
    partial = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        for attempt in range(4):
            try:
                partial.replace(path)
                break
            except PermissionError:
                # Windows can briefly lock the destination while another run writes it.
                try:
                    if path.read_bytes() == content:
                        break
                except (FileNotFoundError, PermissionError):
                    pass
                if attempt == 3:
                    raise
                time.sleep(0.05)
    finally:
        partial.unlink(missing_ok=True)


def load_metadata(cache, context):
    metadata = {}
    for relative_path, expected_hash in METADATA_HASHES.items():
        name = PurePosixPath(relative_path).name
        local_path = cache / ("source-card.md" if name == "README.md" else name)
        content = local_path.read_bytes() if local_path.is_file() else None
        if content is None or sha256(content) != expected_hash:
            url = f"{HF_REPOSITORY}/resolve/{HF_REVISION}/{relative_path}"
            content = fetch_public(url, context)
            if sha256(content) != expected_hash:
                raise ValueError(f"SHA-256 mismatch for author metadata {relative_path}")
            cache_bytes(local_path, content)
        metadata[relative_path] = content
    return metadata


def resolve_leaf_id(filename, source_label, leaf_map):
    # Match the author's basename normalization, then require one class-qualified ID.
    identifier = filename.replace("_final_masked", "").split("___")[-1].split("copy")[0]
    for extension in (".jpg", ".JPG", ".png", ".PNG"):
        identifier = identifier.replace(extension, "")
    matches = {
        leaf_id for leaf_id in leaf_map.get(identifier.strip().lower(), [])
        if leaf_id.startswith(f"{source_label}:::")
    }
    return next(iter(matches)) if len(matches) == 1 else None


def read_groups(split_paths, leaf_map):
    groups = defaultdict(lambda: defaultdict(list))
    inventory = defaultdict(Counter)
    observed_paths = set()
    observed_leaves = {}
    for fold in ("train", "test"):
        for line in split_paths[fold]:
            path = line.strip()
            if not path:
                continue
            parts = path.split("/")
            if len(parts) != 4 or parts[:2] != ["raw", "color"]:
                raise ValueError(f"Invalid author color path {path!r}")
            _, _, source_label, filename = parts
            if source_label not in LABELS:
                continue
            if "\\" in filename or ":" in filename or Path(filename).suffix.lower() not in (".jpg", ".jpeg", ".png"):
                raise ValueError(f"Unsupported author image filename {filename!r}")
            if path in observed_paths:
                raise ValueError(f"Repeated path in official folds: {path}")
            observed_paths.add(path)
            counts = inventory[(fold, source_label)]
            counts["original_images"] += 1
            leaf_id = resolve_leaf_id(filename, source_label, leaf_map)
            if leaf_id is None:
                counts["unresolved_images"] += 1
                continue
            if observed_leaves.setdefault(leaf_id, fold) != fold:
                raise ValueError(f"Leaf {leaf_id!r} occurs in both official folds")
            groups[(fold, source_label)][leaf_id].append(path)
            counts["mapped_images"] += 1
    return groups, inventory


def seeded_order(value, seed):
    return sha256(f"{seed}:{value}".encode("utf-8"))


def choose_candidates(groups, seed):
    candidates = []
    for (fold, source_label), leaves in sorted(groups.items()):
        ranked_leaves = sorted(leaves, key=lambda leaf: seeded_order(leaf, seed))
        validation_count = max(1, len(leaves) // 5) if fold == "train" and len(leaves) > 1 else 0
        for index, leaf_id in enumerate(ranked_leaves):
            split = "val" if index < validation_count else fold
            view_limit = 2 if split == "train" else 1
            paths = sorted(leaves[leaf_id], key=lambda path: seeded_order(path, seed))
            candidates.extend(Candidate(path, source_label, leaf_id, split) for path in paths[:view_limit])
    return candidates


def image_hashes(content):
    with Image.open(io.BytesIO(content)) as source:
        if source.format not in ("JPEG", "PNG"):
            raise ValueError(f"Expected an original JPEG or PNG, got {source.format}")
        rgb = source.convert("RGB")
        pixels = bytes(rgb.convert("L").resize((9, 8), Image.Resampling.BILINEAR).getdata())
        dhash = 0
        for y in range(8):
            for x in range(8):
                dhash = (dhash << 1) | (pixels[y * 9 + x] > pixels[y * 9 + x + 1])
        pixel_sha = sha256(f"{rgb.width}x{rgb.height}:".encode() + rgb.tobytes())
    return sha256(content), pixel_sha, dhash


def get_image(candidate, cache, context):
    cache_path = cache / candidate.path
    if cache_path.is_file():
        try:
            return Inspected(candidate, cache_path, *image_hashes(cache_path.read_bytes()))
        except (OSError, ValueError):
            pass  # Replace an incomplete or damaged cached image from the pinned source.
    image_url = (
        "https://raw.githubusercontent.com/spMohanty/PlantVillage-Dataset/"
        f"{GITHUB_REVISION}/{quote(candidate.path, safe='/')}"
    )
    content = fetch_public(image_url, context)
    checksums = image_hashes(content)
    cache_bytes(cache_path, content)
    return Inspected(candidate, cache_path, *checksums)


def exclude_duplicates(inspected):
    priority = {"test": 0, "val": 1, "train": 2}
    kept = []
    excluded = []
    byte_matches = {}
    pixel_matches = {}
    for item in sorted(inspected, key=lambda row: (priority[row.candidate.split], row.candidate.path)):
        match = byte_matches.get(item.sha256)
        reason = "encoded_exact"
        if match is None:
            match = pixel_matches.get(item.pixel_sha256)
            reason = "decoded_exact"
        if match is None:
            match = next((
                accepted for accepted in kept
                if item.candidate.leaf_id != accepted.candidate.leaf_id
                and (item.dhash ^ accepted.dhash).bit_count() <= 4
            ), None)
            reason = "dhash_near"
        if match is not None:
            excluded.append({
                "path": item.candidate.path,
                "split": item.candidate.split,
                "leaf_id": item.candidate.leaf_id,
                "matched_path": match.candidate.path,
                "matched_split": match.candidate.split,
                "matched_leaf_id": match.candidate.leaf_id,
                "reason": reason,
            })
        else:
            byte_matches[item.sha256] = item
            pixel_matches[item.pixel_sha256] = item
            kept.append(item)
    return kept, excluded


def source_record():
    return {
        "source_id": SOURCE_ID,
        "name": "PlantVillage original RGB (AgroDoctor tomato and potato leaf subset)",
        "version": HF_REVISION,
        "url": f"{HF_REPOSITORY}/tree/{HF_REVISION}",
        "license": "CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "license_note": "The original data paper states that the authors intend the same license to apply to algorithms trained on these images.",
        "attribution": "Sharada P. Mohanty, David P. Hughes and Marcel Salathé (2016). DOI: 10.3389/fpls.2016.01419.",
        "paper_url": "https://doi.org/10.3389/fpls.2016.01419",
        "collection_protocol_url": "https://arxiv.org/abs/1511.08060",
        "image_repository": f"{GITHUB_REPOSITORY}/tree/{GITHUB_REVISION}/raw/color",
        "image_revision": GITHUB_REVISION,
        "metadata_sha256": METADATA_HASHES,
        "acquisition": "U.S. agricultural research stations. Detached leaves photographed outdoors against paper backgrounds.",
        "label_provenance": "Original disease categories assigned by expert plant pathologists using standard phenotyping, as documented by the dataset authors.",
        "official_color_inventory": {"train": 43596, "test": 10709},
        "farm_and_plant_ids": "Unavailable. Group IDs identify source leaves, and distinct leaves may derive from the same plant.",
        "independent_field_validation": False,
    }


def write_json(path, content):
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_dataset(output, metadata, groups, inventory, kept, excluded, seed):
    accepted = defaultdict(list)
    for item in kept:
        candidate = item.candidate
        accepted[(candidate.split, candidate.source_label)].append(candidate.leaf_id)
    for source_label in LABELS:
        for split in ("train", "val", "test"):
            if not accepted[(split, source_label)]:
                raise ValueError(f"No prepared images for {source_label} in {split}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="plantvillage-", dir=output.parent) as staging:
        dataset_root = Path(staging) / "data"
        dataset_root.mkdir()
        with (dataset_root / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
            writer.writeheader()
            for item in kept:
                candidate = item.candidate
                crop, label = LABELS[candidate.source_label]
                path = PurePosixPath("images", *PurePosixPath(candidate.path).parts[2:])
                local_path = dataset_root / path
                local_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item.cache_path, local_path)
                writer.writerow({
                    "path": path.as_posix(),
                    "crop": crop,
                    "plant_part": "leaf",
                    "label": label,
                    "source_id": SOURCE_ID,
                    "farm_id": "",
                    "plant_id": "",
                    "group_id": f"{SOURCE_ID}:{candidate.leaf_id}",
                    "split": candidate.split,
                    "sha256": item.sha256,
                    "label_evidence": f"PlantVillage original class {candidate.source_label}. Source leaf {candidate.leaf_id}.",
                })
        (dataset_root / "source-card.md").write_bytes(metadata["README.md"])
        write_json(dataset_root / "sources.json", [source_record()])
        write_json(dataset_root / "dataset_summary.json", {
            "profile": "plantvillage_tomato_potato_leaf_baseline",
            "seed": seed,
            "pillow_version": pillow_version,
            "manifest_sha256": sha256((dataset_root / "manifest.csv").read_bytes()),
            "official_split_policy": (
                "Official test groups remain test. About one fifth of official train groups per class are validation. "
                "Up to two original views per training group and one per validation/test group. "
                "Rows without an unambiguous original class-qualified leaf ID are excluded."
            ),
            "duplicate_policy": (
                "Exact encoded and decoded RGB checks across all selected images. Difference hash Hamming "
                "distance at most four between distinct recorded groups, prioritized test, validation, then train. "
                "This heuristic can exclude visually similar independent photos or miss harder near-duplicates."
            ),
            "official_target_inventory": [
                {"official_split": fold, "source_label": label, "mapped_leaf_groups": len(groups[(fold, label)]),
                 **{key: inventory[(fold, label)][key] for key in ("original_images", "mapped_images", "unresolved_images")}}
                for fold, label in sorted(inventory)
            ],
            "selected": [
                {"split": split, "crop": LABELS[label][0], "label": LABELS[label][1],
                 "images": len(leaves), "leaf_groups": len(set(leaves))}
                for (split, label), leaves in sorted(accepted.items())
            ],
            "excluded_duplicates": excluded,
        })
        if output.exists():
            raise FileExistsError(f"Output already exists: {output}. Choose a new --out directory.")
        dataset_root.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default=DEFAULT_WORK / "source-cache", type=Path)
    parser.add_argument("--out", default=DEFAULT_WORK / "data", type=Path)
    parser.add_argument("--workers", default=16, type=int)
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.out.exists():
        parser.error(f"output already exists: {args.out}. Choose a new --out directory")

    context = ssl.create_default_context()
    metadata = load_metadata(args.cache, context)
    split_paths = {
        fold: metadata[f"splits/color_{fold}.txt"].decode("utf-8").splitlines()
        for fold in ("train", "test")
    }
    groups, inventory = read_groups(split_paths, json.loads(metadata["leaf_grouping/leaf-map.json"]))
    candidates = choose_candidates(groups, args.seed)
    print(f"Inspecting {len(candidates)} original photos from {sum(map(len, groups.values()))} leaf groups", flush=True)
    inspected = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for image in pool.map(lambda candidate: get_image(candidate, args.cache, context), candidates):
            inspected.append(image)
            if len(inspected) % 200 == 0:
                print(f"Inspected {len(inspected)}/{len(candidates)}", flush=True)
    kept, excluded = exclude_duplicates(inspected)
    write_dataset(args.out, metadata, groups, inventory, kept, excluded, args.seed)
    print(f"Prepared {len(kept)} images; excluded {len(excluded)} duplicates or near-duplicates")
    print(f"Manifest: {args.out / 'manifest.csv'}")


if __name__ == "__main__":
    main()
