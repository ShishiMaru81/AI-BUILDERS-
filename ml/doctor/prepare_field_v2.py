"""Audit reviewed AgroDoctor field photos and prepare separate development and holdout sets."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

from train_kaggle import (
    APPROVED_LABELS, MANIFEST_FIELDS, SPLITS, file_sha256, load_sources,
    validate_manifest,
)


INTAKE_FIELDS = (
    "path", "source_id", "farm_id", "plant_id", "capture_date", "view", "crop",
    "plant_part", "proposed_label", "confirmed_label", "review_status", "reviewer_id",
    "diagnosis_basis", "permission",
)
VIEWS = {"closeup", "whole_plant", "underside", "context"}
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}", re.IGNORECASE | re.ASCII)
UNSUPPORTED = "__unsupported__"
PILOT_TEST_TARGET = 30


def read_csv(path, fields):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or tuple(reader.fieldnames) != fields:
            raise ValueError(f"{path.name} expects the columns {', '.join(fields)} in that order")
        for record in reader:
            if None in record or any(value is None for value in record.values()):
                raise ValueError(f"{path.name} line {reader.line_num}: wrong number of columns")
            yield reader.line_num, {field: value.strip() for field, value in record.items()}


def coded_id(value, field):
    if not ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a nonempty short code using letters, numbers, _ or -")
    return value.lower()


def farm_assignments(path):
    farms = {}
    for line, row in read_csv(path, ("farm_id", "split")):
        farm = coded_id(row["farm_id"], "farm_id")
        if farm in farms:
            raise ValueError(f"{path.name} line {line}: Farm already assigned: {farm}")
        if row["split"] not in SPLITS:
            raise ValueError(f"{path.name} line {line}: split must be train, val or test")
        farms[farm] = row["split"]
    return farms


def read_rgb(path):
    with Image.open(path) as original:
        if original.format not in ("JPEG", "PNG", "WEBP") or getattr(original, "is_animated", False):
            raise ValueError("Expected a single-frame JPEG, PNG or WebP")
        return ImageOps.exif_transpose(original).convert("RGB")


def image_fingerprint(image):
    thumbnail = image.convert("L").resize((9, 8), Image.Resampling.BILINEAR).tobytes()
    dhash = 0
    for y in range(8):
        for x in range(8):
            offset = y * 9 + x
            dhash = (dhash << 1) | (thumbnail[offset] > thumbnail[offset + 1])
    digest = hashlib.sha256(f"{image.width}x{image.height}:".encode() + image.tobytes()).hexdigest()
    return digest, dhash


def check_closeups(root, intake, farms, sources):
    approved, excluded = [], Counter()
    plants, encoded_hashes, pixel_hashes, fingerprints = set(), set(), set(), []
    for line, row in read_csv(intake, INTAKE_FIELDS):
        try:
            if row["review_status"] not in ("confirmed", "pending", "rejected"):
                raise ValueError("review_status must be confirmed, pending or rejected")
            if row["permission"] not in ("granted", "pending", "denied"):
                raise ValueError("permission must be granted, pending or denied")
            if row["view"] not in VIEWS:
                raise ValueError(f"view must be one of {', '.join(sorted(VIEWS))}")
            if row["permission"] != "granted":
                excluded["permission_not_granted"] += 1
                continue
            if row["review_status"] != "confirmed":
                excluded["review_not_confirmed"] += 1
                continue
            if row["view"] != "closeup":
                excluded["context_view"] += 1
                continue

            farm = coded_id(row["farm_id"], "farm_id")
            plant = coded_id(row["plant_id"], "plant_id")
            reviewer = coded_id(row["reviewer_id"], "reviewer_id")
            if farm not in farms:
                raise ValueError(f"Assign the entire farm to a split first: {farm}")
            if row["source_id"] not in sources:
                raise ValueError("Unknown source_id")
            if date.fromisoformat(row["capture_date"]).isoformat() != row["capture_date"]:
                raise ValueError("capture_date must use YYYY-MM-DD")
            if row["plant_part"] != "leaf" or row["crop"] not in APPROVED_LABELS:
                raise ValueError("Select a tomato or potato leaf")
            label = row["confirmed_label"]
            if label == UNSUPPORTED:
                if farms[farm] != "test":
                    raise ValueError(f"{UNSUPPORTED} is for test only")
            elif label not in APPROVED_LABELS[row["crop"]]:
                raise ValueError(f"Unsupported confirmed_label for {row['crop']}: {label}")
            if not row["diagnosis_basis"]:
                raise ValueError("A confirmed label needs a diagnosis_basis")
            if (farm, plant) in plants:
                raise ValueError("Select one confirmed closeup per plant, across all sources")

            path = PurePosixPath(row["path"])
            if path.is_absolute() or ".." in path.parts or "\\" in row["path"] or ":" in row["path"] or not path.parts:
                raise ValueError("Use an image path relative to the photos directory with forward slashes")
            image_path = root.joinpath(*path.parts).resolve()
            if not image_path.is_relative_to(root) or not image_path.is_file():
                raise ValueError("Image must be a file inside the photos directory")
            encoded_hash = file_sha256(image_path)
            image = read_rgb(image_path)
            pixel_hash, dhash = image_fingerprint(image)
            if encoded_hash in encoded_hashes or pixel_hash in pixel_hashes:
                raise ValueError("Exact duplicate across plant records. Review both plant IDs")
            near_match = next((
                other_line for other, other_line in fingerprints if (other ^ dhash).bit_count() <= 4
            ), None)
            if near_match is not None:
                raise ValueError(f"Possible near-duplicate of line {near_match}. Review before export")
            encoded_hashes.add(encoded_hash)
            pixel_hashes.add(pixel_hash)
            fingerprints.append((dhash, line))
            plants.add((farm, plant))
            approved.append({
                "image_path": image_path,
                "pixel_hash": pixel_hash,
                "crop": row["crop"], "plant_part": "leaf", "label": label,
                "source_id": row["source_id"], "farm_id": farm, "plant_id": plant,
                "split": farms[farm], "group_id": f"{farm}/{plant}",
                "label_evidence": f"Reviewer {reviewer}. Basis: {row['diagnosis_basis']}",
            })
        except (ValueError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError(f"{intake.name} line {line}: {exc}") from exc
    return approved, excluded


def audit_summary(approved, excluded):
    counts = {split: Counter() for split in SPLITS}
    farms = {split: defaultdict(set) for split in SPLITS}
    for row in approved:
        label = f"{row['crop']}__{row['label']}"
        counts[row["split"]][label] += 1
        farms[row["split"]][label].add(row["farm_id"])
    known_test = {label for label in counts["test"] if not label.endswith(f"__{UNSUPPORTED}")}
    labels = set(counts["train"])
    ready = (
        {label.split("__", 1)[0] for label in labels} == set(APPROVED_LABELS)
        and labels == set(counts["val"]) == known_test
    )
    return {
        "approved_closeups": len(approved),
        "excluded_by_reason": dict(sorted(excluded.items())),
        "plants_by_split_and_class": {split: dict(sorted(values.items())) for split, values in counts.items()},
        "farms_by_split_and_class": {
            split: {label: len(ids) for label, ids in sorted(values.items())}
            for split, values in farms.items()
        },
        "ready_for_development": ready,
        "classes_below_pilot_test_target": sorted(label for label in labels if counts["test"][label] < PILOT_TEST_TARGET),
        "pilot_test_target_per_class": PILOT_TEST_TARGET,
    }


def export_sets(output, approved, sources, report):
    if not report["ready_for_development"]:
        raise ValueError("Export requires both crops and matching known classes in train, validation and holdout")
    if output.exists():
        raise ValueError("Choose a new output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="agrodoctor-field-", dir=output.parent) as scratch:
        stage = Path(scratch) / "set"
        for kind, splits in (("development", ("train", "val")), ("holdout", ("test",))):
            target = stage / kind
            (target / "images").mkdir(parents=True)
            subset = [row for row in approved if row["split"] in splits]
            source_ids = sorted({row["source_id"] for row in subset})
            (target / "sources.json").write_text(json.dumps(
                [sources[source_id] for source_id in source_ids], ensure_ascii=False, indent=2,
            ) + "\n", encoding="utf-8")
            with (target / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, MANIFEST_FIELDS)
                writer.writeheader()
                for row in subset:
                    image = read_rgb(row["image_path"])
                    if image_fingerprint(image)[0] != row["pixel_hash"]:
                        raise ValueError("A photo changed during export. Check the original and rerun the audit")
                    relative = f"images/{row['pixel_hash']}.png"
                    destination = target / relative
                    # A fresh pixel buffer preserves the photograph without its original metadata.
                    Image.frombytes("RGB", image.size, image.tobytes()).save(destination)
                    writer.writerow({
                        key: row[key] for key in MANIFEST_FIELDS if key not in ("path", "sha256")
                    } | {"path": relative, "sha256": file_sha256(destination)})
        dev = stage / "development"
        validate_manifest(dev, dev / "manifest.csv", dev / "sources.json", allow_no_test=True)
        (stage / "audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Private directory for the original photo paths")
    parser.add_argument("--intake", required=True, type=Path, help="Completed private intake CSV")
    parser.add_argument("--farm-splits", required=True, type=Path, help="Frozen farm_id,split assignments")
    parser.add_argument("--sources", required=True, type=Path, help="Source and permission records as a JSON array")
    parser.add_argument("--output", type=Path, help="New export directory. Omit to print the audit only")
    args = parser.parse_args()
    try:
        if not args.root.resolve(strict=True).is_dir():
            raise ValueError("--root must be a directory")
        sources = load_sources(args.sources)
        farms = farm_assignments(args.farm_splits)
        approved, excluded = check_closeups(args.root.resolve(), args.intake, farms, sources)
        report = audit_summary(approved, excluded)
        if args.output is not None:
            export_sets(args.output.resolve(), approved, sources, report)
        print(json.dumps(report, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, f"AgroDoctor field intake: {exc}\n")


if __name__ == "__main__":
    main()
