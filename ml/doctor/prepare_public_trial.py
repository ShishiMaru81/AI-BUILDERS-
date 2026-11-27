"""Build a nine-label public-data research trial from the frozen AgroDoctor baseline."""

import argparse
import csv
import hashlib
import io
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageOps

from prepare_field_v2 import image_fingerprint
from train_kaggle import MANIFEST_FIELDS, file_sha256, validate_manifest


TOMATO_LABELS = {
    "bacterial spot": "bacterial_spot", "bacteiral spot": "bacterial_spot",
    "early blight": "early_blight", "healthy": "healthy", "late blight": "late_blight",
    "leaf mold": "leaf_mold",
}
POTATO_LABELS = {"healthy": "healthy", "late blight": "late_blight"}
SOURCES = (
    ("hossain_tomato_2025", "Hossain et al. Tomato leaf diseases", "93h9p62kg4",
     "tomato", "train", "93h9p62kg4-1.zip", TOMATO_LABELS),
    ("holeta_potato_2020", "Tilahun Potato Leaf (Healthy and Late Blight)", "v4w72bsts5",
     "potato", "train", "holeta-audit/Local", POTATO_LABELS),
    ("rachin_tomato_2025", "Rachin et al. Tomato Leaf Disease Classification Dataset", "jttrv2w27r",
     "tomato", "external", "jttrv2w27r-1.zip", TOMATO_LABELS),
)


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_manifest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def decode(content):
    with Image.open(io.BytesIO(content)) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def photos(root, relative, labels):
    path = root / relative
    if path.suffix == ".zip":
        with ZipFile(path) as archive:
            for item in sorted(archive.namelist()):
                label = labels.get(Path(item).parent.name.casefold())
                if label and item.lower().endswith((".jpg", ".jpeg", ".png")):
                    yield item, label, archive.read(item)
    else:
        for item in sorted(path.rglob("*")):
            label = labels.get(item.parent.name.casefold())
            if label and item.suffix.lower() in (".jpg", ".jpeg", ".png"):
                yield item.relative_to(path).as_posix(), label, item.read_bytes()


def prepared(work, output):
    baseline = work / "data"
    baseline_rows = read_rows(baseline / "manifest.csv")
    field = work / "field-eval-inputs"
    historical = read_rows(field / "field_manifest.csv")
    source_records = json.loads((baseline / "sources.json").read_text(encoding="utf-8"))
    byte_hashes, pixel_hashes, fingerprints = set(), set(), set()
    # Existing test and historical exploratory photos remain outside the added training sources.
    for root, rows in ((baseline, baseline_rows), (field, historical)):
        for row in rows:
            data = (root / row["path"]).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != row["sha256"]:
                raise ValueError(f"Frozen photo checksum mismatch: {row['path']}")
            byte_hashes.add(digest)
            pixel, difference = image_fingerprint(decode(data))
            pixel_hashes.add(pixel)
            fingerprints.add(difference)

    train_root = output / "data"
    outside = output / "external"
    for directory in (train_root, outside):
        directory.mkdir(parents=True)
    for row in baseline_rows:
        dest = train_root / row["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline / row["path"], dest)

    counts = defaultdict(Counter)
    excluded = defaultdict(Counter)
    staged_rows = {}
    for source, title, doi, crop, split, path, labels in sorted(SOURCES, key=lambda spec: spec[4]):
        # Reserve the external cohort first so every close match is excluded from training.
        local = list(photos(work / "v2-sources" / crop, path, labels))
        source_records.append({
            "source_id": source, "name": title, "version": "1", "license": "CC BY 4.0",
            "url": f"https://data.mendeley.com/datasets/{doi}/1", "attribution": title,
        })
        categories = defaultdict(set)
        for _, label, raw in local:
            categories[hashlib.sha256(raw).hexdigest()].add(label)
        target = train_root if split == "train" else outside
        images = target / "public" / source
        images.mkdir(parents=True)
        rows = staged_rows[source] = []
        for position, (_, label, raw) in enumerate(local):
            digest = hashlib.sha256(raw).hexdigest()
            if len(categories[digest]) > 1:
                excluded[source]["conflicting_exact_label"] += 1
                continue
            image = decode(raw)
            pixel, difference = image_fingerprint(image)
            if digest in byte_hashes or pixel in pixel_hashes:
                excluded[source]["exact_match"] += 1
                continue
            if any((difference ^ saved).bit_count() <= 4 for saved in fingerprints):
                excluded[source]["possible_near_duplicate"] += 1
                continue
            byte_hashes.add(digest)
            pixel_hashes.add(pixel)
            fingerprints.add(difference)
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            filename = images / f"{position:04d}.jpg"
            Image.frombytes("RGB", image.size, image.tobytes()).save(filename, quality=94)
            rows.append({
                "path": filename.relative_to(target).as_posix(), "crop": crop, "plant_part": "leaf",
                "label": label, "source_id": source, "farm_id": "", "plant_id": "",
                "group_id": source, "split": "test" if split == "external" else "train",
                "sha256": file_sha256(filename),
                "label_evidence": "Depositor folder label. Source cohort only. Per-plant independence is unknown.",
            })
            counts[source][label] += 1
        if not rows:
            raise ValueError(f"No usable images in {source}")
    development_ids = {source for source, _, _, _, split, _, _ in SOURCES if split == "train"}
    training_rows = baseline_rows + [row for source in sorted(development_ids) for row in staged_rows[source]]
    test_rows = [row for source in sorted(staged_rows.keys() - development_ids) for row in staged_rows[source]]
    write_manifest(train_root / "manifest.csv", training_rows)
    write_manifest(outside / "manifest.csv", test_rows)
    external_ids = {row["source_id"] for row in test_rows}
    for target, keep_external in ((train_root, False), (outside, True)):
        records = [record for record in source_records if (record["source_id"] in external_ids) == keep_external]
        (target / "sources.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    _, summary = validate_manifest(train_root, train_root / "manifest.csv", train_root / "sources.json")
    summary["public_images_by_source_label"] = counts
    summary["public_photo_exclusions"] = excluded
    summary["external_manifest_sha256"] = file_sha256(outside / "manifest.csv")
    summary["public_grouping"] = "One cohort per deposit. Farm and plant independence are unknown."
    (output / "audit.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="Existing AgroDoctor Kaggle source directory")
    parser.add_argument("--output", type=Path, required=True, help="New directory for this trial")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Trial directory already exists. Choose a new directory.")
    print(json.dumps(prepared(args.work, args.output), indent=2))


if __name__ == "__main__":
    main()
