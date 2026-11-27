import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image


TRAINER = Path(__file__).resolve().parents[1] / "train_kaggle.py"
FIELDS = (
    "path", "crop", "plant_part", "label", "source_id", "farm_id", "plant_id",
    "group_id", "split", "sha256", "label_evidence",
)


@pytest.fixture
def manifest_fixture(tmp_path):
    rows = []
    for split in ("train", "val", "test"):
        for crop in ("potato", "tomato"):
            path = tmp_path / f"{split}-{crop}.png"
            Image.new("RGB", (16, 16), (len(rows) * 20, 30, 40)).save(path)
            rows.append(dict(
                path=path.name, crop=crop, plant_part="leaf", label="healthy", source_id="fixture",
                farm_id="farm1", plant_id=path.stem, group_id=path.stem, split=split,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), label_evidence="synthetic fixture",
            ))
    (tmp_path / "sources.json").write_text(json.dumps([{
        "source_id": "fixture", "name": "Fixture", "version": "1", "url": "https://example.invalid",
        "license": "Synthetic fixture", "attribution": "Generated for tests",
    }]), encoding="utf-8")
    return tmp_path, rows


def validate(root, rows):
    with (root / "manifest.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return subprocess.run(
        [sys.executable, str(TRAINER), "--root", str(root), "--validate-only"],
        check=False, capture_output=True, text=True,
    )


def test_validation_counts_crop_qualified_labels(manifest_fixture):
    root, rows = manifest_fixture
    result = validate(root, rows)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["split_counts"]["train"]["by_class"] == {"potato__healthy": 1, "tomato__healthy": 1}
    assert report["split_counts"]["val"]["by_source"] == {"fixture": 2}
    assert report["split_counts"]["test"]["groups"] == 2


@pytest.mark.parametrize(("replacements", "message"), [
    ({"label": "leafroll"}, "Unsupported label"),
    ({"plant_part": "tuber"}, "plant_part must be leaf"),
    ({"path": "../outside.png"}, "dataset root"),
    ({"sha256": "f" * 64}, "SHA-256 mismatch"),
    ({"source_id": "unknown"}, "Unknown source_id"),
])
def test_validation_rejects_invalid_manifest_rows(manifest_fixture, replacements, message):
    root, rows = manifest_fixture
    rows[1].update(replacements)
    result = validate(root, rows)
    assert result.returncode != 0
    assert message in result.stderr


def test_validation_rejects_non_image_with_matching_hash(manifest_fixture):
    root, rows = manifest_fixture
    payload = b"this is not an image"
    (root / rows[0]["path"]).write_bytes(payload)
    rows[0]["sha256"] = hashlib.sha256(payload).hexdigest()
    result = validate(root, rows)
    assert result.returncode != 0
    assert "Cannot decode image" in result.stderr


@pytest.mark.parametrize(("repeated_field", "message"), [
    ("group_id", "group_id crosses splits"),
    ("plant_id", "plant_id crosses splits"),
    ("sha256", "Exact image hash crosses splits"),
])
def test_validation_rejects_leakage(manifest_fixture, repeated_field, message):
    root, rows = manifest_fixture
    rows[2][repeated_field] = rows[0][repeated_field]
    if repeated_field == "sha256":
        (root / rows[2]["path"]).write_bytes((root / rows[0]["path"]).read_bytes())
    result = validate(root, rows)
    assert result.returncode != 0
    assert message in result.stderr


def test_unrestricted_joint_winner_must_match_reported_crop():
    import numpy as np

    from ml.doctor.train_kaggle import uncertainty_decisions

    probabilities = np.array([[0.44, 0.56], [0.65, 0.35], [0.57, 0.43], [0.15, 0.85]])
    decisions = uncertainty_decisions(
        probabilities, ["potato", "tomato"], ["potato"] * 3 + ["tomato"], [0.60, None],
    )
    assert decisions.tolist() == [-1, 0, -1, -1]


def test_threshold_selection_requires_independent_correct_validation_predictions():
    import numpy as np

    from ml.doctor.train_kaggle import select_thresholds

    probabilities = np.array([[0.8, 0.2]] * 5 + [[0.6, 0.4]] + [[0.1, 0.9]] * 5)
    expected = np.array([0] * 5 + [1] + [1] * 5)
    # Four tomato photos share one group. The five correct tomato predictions cover two groups.
    groups = [f"potato-{i}" for i in range(5)] + ["tomato-1"] * 5 + ["tomato-2"]
    thresholds, evidence = select_thresholds(probabilities, expected, groups, ["potato", "tomato"])
    assert thresholds == [0.50, None]
    assert evidence[0]["accepted_groups"] == 5


def test_synthetic_smoke_exports_cpu_artifact_and_reports_test_metrics(tmp_path):
    import torch

    root = tmp_path / "run"
    result = subprocess.run(
        [sys.executable, str(TRAINER), "--smoke", "--device", "cpu", "--unfreeze-blocks", "2", "--output", str(root)],
        check=False, capture_output=True, text=True, timeout=100,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    metadata = json.loads((root / "model.json").read_text(encoding="utf-8"))
    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    artifact = root / "model.ts"
    assert metadata["synthetic_smoke"] is True
    assert metadata["field_validated"] is False
    assert metadata["release_approved"] is False
    assert metadata["artifact"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert metrics["test"]["images"] == 6
    assert 0.0 <= metrics["test"]["selective"]["coverage"] <= 1.0
    assert set(metrics["test"]["selective"]["per_class"]) == {"potato__healthy", "tomato__healthy"}
    assert (root / "checkpoint.pt").stat().st_size > 0
    model = torch.jit.load(str(artifact), map_location="cpu")
    torch.set_num_threads(1)
    assert model(torch.zeros(2, 3, 224, 224)).shape == (2, 2)
    # CUDA cannot backpropagate through AdaptiveAvgPool2d in deterministic mode.
    assert "aten::adaptive_avg_pool2d" not in str(model.inlined_graph)
