import csv
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


DOCTOR = Path(__file__).resolve().parents[1]
FIELDS = (
    "path", "source_id", "farm_id", "plant_id", "capture_date", "view",
    "crop", "plant_part", "proposed_label", "confirmed_label", "review_status",
    "reviewer_id", "diagnosis_basis", "permission",
)


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.fixture
def intake(tmp_path):
    root = tmp_path / "photos"
    root.mkdir()
    rows, farms = [], []
    for split in ("train", "val", "test"):
        farm = f"farm-{split}"
        farms.append({"farm_id": farm, "split": split})
        for crop in ("potato", "tomato"):
            name = f"{farm}-{crop}.png"
            rng = random.Random(name)
            image = Image.frombytes("RGB", (36, 32), rng.randbytes(36 * 32 * 3))
            exif = Image.Exif()
            exif[270] = "private original caption"
            image.save(root / name, exif=exif)
            rows.append(dict(
                path=name, source_id="fixture", farm_id=farm, plant_id=crop,
                capture_date="2026-11-27", view="closeup", crop=crop, plant_part="leaf",
                proposed_label="healthy", confirmed_label="healthy", review_status="confirmed",
                reviewer_id="reviewer-1", diagnosis_basis="test-only", permission="granted",
            ))
    (tmp_path / "sources.json").write_text(json.dumps([{
        "source_id": "fixture", "name": "Synthetic fixture", "version": "1",
        "url": "https://example.invalid", "license": "Test only", "attribution": "Generated",
    }]), encoding="utf-8")
    return tmp_path, root, rows, farms


def audit(intake, *, export=False):
    directory, root, rows, farms = intake
    write_csv(directory / "intake.csv", FIELDS, rows)
    write_csv(directory / "farms.csv", ("farm_id", "split"), farms)
    args = [
        sys.executable, str(DOCTOR / "prepare_field_v2.py"), "--root", str(root),
        "--intake", str(directory / "intake.csv"), "--sources", str(directory / "sources.json"),
        "--farm-splits", str(directory / "farms.csv"),
    ]
    if export:
        args.extend(["--output", str(directory / "v2")])
    return subprocess.run(args, capture_output=True, check=False, text=True)


def test_exports_separate_sets_without_context_or_metadata(intake):
    directory, root, rows, _ = intake
    rows.append({**rows[0], "path": "pending.png", "review_status": "pending"})
    rows.append({**rows[0], "path": "context.png", "view": "whole_plant"})
    rows.append({**rows[0], "path": "denied.png", "permission": "denied"})
    challenge = root / "challenge.png"
    image = Image.frombytes("RGB", (36, 32), random.Random(169).randbytes(36 * 32 * 3))
    image.save(challenge)
    rows.append({
        **rows[4], "path": challenge.name, "plant_id": "challenge",
        "confirmed_label": "__unsupported__",
    })
    result = audit(intake, export=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["excluded_by_reason"] == {
        "context_view": 1, "permission_not_granted": 1, "review_not_confirmed": 1,
    }
    dev = directory / "v2" / "development"
    holdout = directory / "v2" / "holdout"
    development_rows = read_csv(dev / "manifest.csv")
    holdout_rows = read_csv(holdout / "manifest.csv")
    assert len(development_rows) == 4
    assert len(holdout_rows) == 3
    assert {row["split"] for row in development_rows} == {"train", "val"}
    assert {row["farm_id"] for row in holdout_rows} == {"farm-test"}
    assert "__unsupported__" in {row["label"] for row in holdout_rows}
    assert {row["path"] for row in development_rows}.isdisjoint(row["path"] for row in holdout_rows)
    for part, entries in ((dev, development_rows), (holdout, holdout_rows)):
        for row in entries:
            with Image.open(part / row["path"]) as image:
                assert not image.getexif()

    validation = subprocess.run([
        sys.executable, str(DOCTOR / "train_kaggle.py"), "--root", str(dev),
        "--validate-only", "--skip-test",
    ], capture_output=True, check=False, text=True)
    assert validation.returncode == 0, validation.stderr
    assert json.loads(validation.stdout)["split_counts"]["test"]["images"] == 0


def test_conflicting_farm_assignment_refuses_export(intake):
    directory, _, _, farms = intake
    farms.append({"farm_id": farms[0]["farm_id"].upper(), "split": "test"})
    result = audit(intake, export=True)
    assert result.returncode != 0
    assert "Farm already assigned" in result.stderr
    assert not (directory / "v2").exists()


@pytest.mark.parametrize("kind", ["encoded", "pixels", "near"])
def test_copy_or_near_duplicate_on_another_farm_blocks_export(intake, kind):
    directory, root, rows, _ = intake
    original = root / rows[0]["path"]
    duplicate = root / rows[4]["path"]
    if kind == "encoded":
        duplicate.write_bytes(original.read_bytes())
    else:
        with Image.open(original) as image:
            clean = image.convert("RGB")
        if kind == "near":
            clean.putpixel((0, 0), (0, 0, 0))
        clean.save(duplicate)
    result = audit(intake, export=True)
    assert result.returncode != 0
    assert "duplicate" in result.stderr.lower()
    assert not (directory / "v2").exists()


def test_unsupported_review_cannot_be_a_development_label(intake):
    _, _, rows, _ = intake
    rows[0]["confirmed_label"] = "__unsupported__"
    result = audit(intake, export=True)
    assert result.returncode != 0
    assert "test only" in result.stderr


def test_empty_registered_intake_can_be_audited_without_emitting_a_dataset(intake):
    directory, _, rows, _ = intake
    rows.clear()
    result = audit(intake)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ready_for_development"] is False
    assert report["approved_closeups"] == 0
    assert not (directory / "v2").exists()
