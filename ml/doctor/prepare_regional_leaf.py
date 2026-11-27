"""Prepare disjoint TOM2024 development regions and a reserved regional test."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps

from evaluate_field import MANIFEST_FIELDS
from prepare_field_v2 import image_fingerprint
from train_kaggle import file_sha256


def records(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def fingerprint(path):
    with Image.open(path) as photo:
        return image_fingerprint(ImageOps.exif_transpose(photo).convert("RGB"))


def prepare(catalog, images, references, output):
    existing_hashes, existing_pixels, existing_views = set(), set(), set()
    for reference in references:
        for row in records(reference):
            path = reference.parent / row["path"]
            digest = file_sha256(path)
            if digest != row["sha256"]:
                raise ValueError(f"Reference photo changed: {path}")
            pixel, view = fingerprint(path)
            existing_hashes.add(digest)
            existing_pixels.add(pixel)
            existing_views.add(view)

    groups, excluded = {"development": [], "reserved": []}, Counter()
    candidates = [row for row in records(catalog) if row["mapping_status"] == "source_label_verified_by_join"]
    # Process the reserved region first. Retain no matching development view.
    for row in sorted(candidates, key=lambda row: (row["region"] != "Plateau-Central", row["original_image_id"])):
        original_id = row["original_image_id"]
        if not original_id.isdecimal():
            raise ValueError(f"Unexpected original image id: {original_id}")
        split = "reserved" if row["region"] == "Plateau-Central" else "development"
        path = images / f"{original_id}.jpg"
        if not path.is_file():
            excluded[f"{split}: missing image"] += 1
            continue
        digest = file_sha256(path)
        pixel, view = fingerprint(path)
        if (digest in existing_hashes or pixel in existing_pixels
                or any((view ^ other).bit_count() <= 4 for other in existing_views)):
            excluded[f"{split}: exact or possible near duplicate"] += 1
            continue
        existing_hashes.add(digest)
        existing_pixels.add(pixel)
        existing_views.add(view)
        label = {"healthy_leaf": "healthy", "tomato_late_blight_d": "late_blight"}[row["matching_archive_folder"]]
        groups[split].append({
            "path": path.relative_to(output).as_posix(), "crop": "tomato", "plant_part": "leaf",
            "label": label, "source_id": "TOM2024-" + row["region"], "group_id": row["region"],
            "sha256": digest, "label_evidence": "TOM2024 portal ID joined to expert-reviewed deposit folder",
        })
    for split, rows in groups.items():
        if {row["label"] for row in rows} != {"healthy", "late_blight"}:
            raise ValueError(f"The {split} regions need usable images for both known labels.")
        with (output / f"tom2024-{split}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    report = {
        "source_catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "labels_by_partition": {split: dict(Counter(row["label"] for row in rows)) for split, rows in groups.items()},
        "exclusions": dict(excluded),
        "grouping": "Regions are disjoint. Farm and plant identities are unknown.",
    }
    (output / "tom2024-split-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--reference", action="append", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.catalog, args.images, args.reference, args.images.parent)
