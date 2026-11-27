"""Add the authored PLD training and validation folds plus a TOM2024 development region."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image, ImageOps

from prepare_field_v2 import image_fingerprint
from prepare_regional_leaf import fingerprint, records
from train_kaggle import MANIFEST_FIELDS


def prepare(root):
    study = root / "next-study"
    developed = records(study / "leaf-development.csv")
    reserved = []
    for name in ("tom2024-reserved.csv", "pakistan-potato-test.csv"):
        for row in records(study / name):
            reserved.append({**row, "path": (study / row["path"]).relative_to(root).as_posix()})
    exact = {row["sha256"] for row in developed + reserved}
    pixels, views = set(), set()
    for row in developed + reserved:
        pixel, view = fingerprint(root / row["path"])
        pixels.add(pixel)
        views.add(view)

    for row in developed:
        if row["source_id"] == "TOM2024-Centre-Ouest":
            row["split"] = "train"

    photo_output = study / "leaf-domain-photos"
    photo_output.mkdir(exist_ok=False)
    mapping = {"Healthy": "healthy", "Early_Blight": "early_blight", "Late_Blight": "late_blight"}
    totals, excluded = Counter(), Counter()
    with ZipFile(study / "pakistan-potato-leaf.zip") as archive:
        entries = sorted(archive.namelist(), key=lambda name: ("Validation" not in PurePosixPath(name).parts,
                                                               hashlib.sha256(name.encode()).digest()))
        for filename in entries:
            path = PurePosixPath(filename)
            role = "val" if "Validation" in path.parts else "train" if "Training" in path.parts else None
            label = mapping.get(path.parent.name)
            if not role or not label or path.suffix.casefold() not in {".jpg", ".jpeg", ".png"}:
                continue
            limit = 120 if role == "val" else 340
            if totals[role, label] >= limit:
                continue
            content = archive.read(filename)
            digest = hashlib.sha256(content).hexdigest()
            with Image.open(io.BytesIO(content)) as image:
                pixel, view = image_fingerprint(ImageOps.exif_transpose(image).convert("RGB"))
            if digest in exact or pixel in pixels or any((view ^ other).bit_count() <= 4 for other in views):
                excluded[role] += 1
                continue
            exact.add(digest)
            pixels.add(pixel)
            views.add(view)
            target = photo_output / f"{digest[:24]}{path.suffix.casefold()}"
            target.write_bytes(content)
            cohort = f"pakistan_pld_{role}"
            developed.append({
                "path": target.relative_to(root).as_posix(), "crop": "potato", "plant_part": "leaf",
                "label": label, "source_id": cohort, "group_id": cohort, "farm_id": "", "plant_id": "",
                "split": role, "sha256": digest, "label_evidence": "PLD author folder label; farm and plant IDs unavailable.",
            })
            totals[role, label] += 1
    if len(totals) != 6:
        raise ValueError("The added PLD folds did not contain all expected classes")
    with (study / "leaf-domain-development.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(developed)
    report = {
        "new_development_photos": {f"{role}/{label}": count for (role, label), count in sorted(totals.items())},
        "possible_duplicates_excluded": dict(excluded),
        "reserved": ["TOM2024 Plateau-Central", "PLD Testing fold after overlap screening"],
        "grouping_limits": "PLD test comes from the same collection as its author training folds. Site and plant IDs are unavailable.",
    }
    (study / "leaf-domain-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    prepare(parser.parse_args().work)
