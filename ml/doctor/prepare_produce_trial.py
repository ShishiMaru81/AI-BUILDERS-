"""Build a public produce study with grouped splits and leaf challenge photos."""

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image, ImageOps

from prepare_field_v2 import image_fingerprint
from prepare_regional_leaf import records
from train_kaggle import MANIFEST_FIELDS


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def prepare(work):
    raw = work / "next-study"
    output = raw / "produce-manifests"
    output.mkdir(exist_ok=False)
    images = output / "images"
    images.mkdir()
    exclusions = Counter()
    seen = []

    def materialize(content, crop, label, source, group, *, part="produce"):
        try:
            with Image.open(io.BytesIO(content)) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                pixel, visual = image_fingerprint(image)
                image.thumbnail((640, 640), Image.Resampling.LANCZOS)
        except OSError:
            exclusions["unreadable_image"] += 1
            return None
        exact = hashlib.sha256(content).hexdigest()
        duplicate = next((row for bytes_hash, pixel_hash, view, row in seen if
                          bytes_hash == exact or pixel_hash == pixel or (visual ^ view).bit_count() <= 4), None)
        if duplicate is not None:
            reason = "possible_cross_label_duplicate" if (crop, label) != (duplicate["crop"], duplicate["label"]) else "duplicate"
            exclusions[reason] += 1
            if reason == "possible_cross_label_duplicate":
                duplicate["unresolved_duplicate"] = True
            return None
        target = images / f"{exact[:24]}.jpg"
        Image.frombytes("RGB", image.size, image.tobytes()).save(target, quality=93)
        row = dict(path=target.relative_to(output).as_posix(), crop=crop, label=label, plant_part=part,
                   source_id=source, group_id=group, farm_id="", plant_id="",
                   sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                   label_evidence="Source label collapsed to an appearance category; item and farm IDs unavailable.")
        seen.append((exact, pixel, visual, row))
        return row

    def add(entries, content, crop, label, source, group, role=None, *, part="produce"):
        row = materialize(content, crop, label, source, group, part=part)
        if row:
            row["split"] = role or ""
            entries.append(row)

    train_val, holdout, public = [], [], []
    with ZipFile(raw / "malaysian-produce.zip") as archive:
        for name in sorted(archive.namelist()):
            part = PurePosixPath(name)
            for crop in ("potato", "tomato"):
                if part.name.lower().startswith("fresh_fresh" + crop) and part.suffix.lower() == ".jpg":
                    add(holdout, archive.read(name), crop, "sound_appearance", "zenodo_20843858", "malaysia_fresh_session", "test")

    potato_folders = {"Healthy Potatoes": "sound_appearance", "Common Scab": "visible_damage",
                      "Black Scurf": "visible_damage", "Dry Rot": "visible_damage", "Pink Rot": "visible_damage"}
    with ZipFile(raw / "potato-bari.zip") as archive:
        for name in sorted(archive.namelist()):
            part = PurePosixPath(name)
            label = potato_folders.get(part.parent.name)
            if label and part.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                add(holdout, archive.read(name), "potato", label, "bari_reviewed_tuber", "bari_web_collection", "test")

    data = raw / "produce-public"
    index = json.loads((data / "archive-members.json").read_text(encoding="utf-8"))
    for record in index:
        relative = PurePosixPath(record["path"])
        crop, state, _ = relative.parts
        label = {"fresh": "sound_appearance", "rotten": "visible_damage"}[state]
        original = PurePosixPath(record["original"])
        group = original.stem.casefold().replace(" ", "")
        add(public, (data / relative).read_bytes(), crop, label, "mukhiddinov_2022", group)

    # Keep repeated filenames and their alternate encodings in one split.
    groups_by_label = defaultdict(lambda: defaultdict(list))
    for row in public:
        if not row.get("unresolved_duplicate"):
            groups_by_label[(row["crop"], row["label"])][row["group_id"]].append(row)
    for (crop, label), groups in sorted(groups_by_label.items()):
        keys = sorted(groups, key=lambda key: hashlib.sha256(f"2026/{key}".encode()).digest())
        validation = max(1, int(0.15 * len(keys)))
        for index, group in enumerate(keys):
            for row in groups[group]:
                row.update(split="val" if index < validation else "test" if index < 2 * validation else "train")
                (holdout if row["split"] == "test" else train_val).append(row)

    leaves = work / "data"
    grouped_leaves = defaultdict(list)
    for row in records(leaves / "manifest.csv"):
        grouped_leaves[(row["split"], row["crop"])].append(row)
    for (role, crop), samples in sorted(grouped_leaves.items()):
        sample_count = {"train": 72, "val": 26, "test": 38}[role]
        chosen = sorted(samples, key=lambda row: hashlib.sha256(row["path"].encode()).digest())[:sample_count]
        for row in chosen:
            add(holdout if role == "test" else train_val, (leaves / row["path"]).read_bytes(),
                crop, "out_of_scope", "plantvillage_leaf_challenge", row["group_id"], role, part="leaf")

    groups_across_splits = {}
    for row in train_val + holdout:
        current = (row["source_id"], row["group_id"])
        if groups_across_splits.setdefault(current, row["split"]) != row["split"]:
            raise ValueError("A capture group appeared in two splits")
    def publish(rows, name):
        usable = [{key: item for key, item in row.items() if key != "unresolved_duplicate"}
                  for row in rows if not row.get("unresolved_duplicate")]
        write(output / name, usable)
        return dict(Counter(f"{row['split']}/{row['source_id']}/{row['crop']}/{row['label']}" for row in usable))
    report = {"development": publish(train_val, "development.csv"), "holdout": publish(holdout, "holdout.csv"),
              "exclusions": dict(exclusions), "grouping": "Filename and image grouping. Farm or individual item identities unknown."}
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="Directory containing the AgroDoctor datasets")
    prepare(parser.parse_args().work)
