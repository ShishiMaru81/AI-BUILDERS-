import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import torch
from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "evaluate_field.py"
FIELDS = ("path", "crop", "plant_part", "label", "source_id", "group_id", "sha256", "label_evidence")
CLASSES = ("potato__early_blight", "potato__healthy", "potato__leafroll", "tomato__late_blight")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ColorLogits(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer("logits", torch.tensor([
            [4., 0., 0., 0.], [0.3, 0., 0., 0.], [0., 0., 0., 4.], [0., 0., 4., 0.],
            [4., 0., 0., 0.], [0., 0., 0., 4.], [4., 0., 0., 0.], [0., 4., 0., 0.],
        ]))

    def forward(self, images):
        red = (images[:, 0, 0, 0] * 0.229 + 0.485) * 255
        return self.logits[(red / 32).round().long()]


@pytest.fixture
def run_fixture(tmp_path):
    root = tmp_path / "images"
    root.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    artifact = bundle / "model.ts"
    model = ColorLogits().eval()
    torch.jit.trace(model, torch.zeros((1, 3, 224, 224))).save(str(artifact))
    metadata = {
        "schema_version": 1,
        "version": "synthetic-fixture",
        "artifact": {"path": "model.ts", "sha256": sha256(artifact), "size_bytes": artifact.stat().st_size},
        "preprocessing": {
            "image_size": 224, "color_mode": "RGB", "resize": "square", "interpolation": "bilinear",
            "scale": 255.0, "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
            "exif_transpose": True,
        },
        "output": "joint_logits",
        "score_type": "uncalibrated_joint_softmax",
        "labels": [
            dict(id=class_id, plant_part="leaf", crop=crop, label=label)
            for class_id in CLASSES
            for crop, label in [class_id.split("__")]
        ],
        "thresholds": dict(zip(CLASSES, [0.75, 0.75, None, 0.75])),
        "synthetic_smoke": True,
    }
    (bundle / "model.json").write_text(json.dumps(metadata), encoding="utf-8")
    rows = []
    examples = [
        ("potato", "early_blight", "first", "plant-a"),
        ("potato", "early_blight", "first", "plant-a"),
        ("potato", "early_blight", "first", "plant-b"),
        ("potato", "leafroll", "first", "plant-c"),
        ("potato", "__unsupported__", "first", "challenge-a"),
        ("tomato", "late_blight", "second", "plant-d"),
        ("wheat", "__unsupported__", "second", "challenge-b"),
        ("potato", "__unsupported__", "first", "challenge-c"),
    ]
    for index, (crop, label, source, group) in enumerate(examples):
        path = root / f"{index}.png"
        Image.new("RGB", (16, 18), (32 * index, 30, 40)).save(path)
        rows.append(dict(path=path.name, crop=crop, plant_part="leaf", label=label, source_id=source,
                         group_id=group, sha256=sha256(path), label_evidence="synthetic fixture"))
    return root, bundle, rows, metadata


def write_manifest(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_cli_reports_field_abstention_and_out_of_scope_false_alarms(run_fixture, tmp_path):
    root, bundle, rows, _ = run_fixture
    manifest = tmp_path / "field.csv"
    output = tmp_path / "output"
    write_manifest(manifest, rows)
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--bundle", str(bundle), "--root", str(root),
        "--manifest", str(manifest), "--output", str(output),
    ], capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr

    report = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert report["manifest_sha256"] == sha256(manifest)
    assert report["field_validated"] is False
    assert report["release_approved"] is False
    assert report["synthetic_smoke"] is True
    metrics = report["overall"]
    assert metrics["images"] == 8
    assert metrics["groups"] == 7
    assert metrics["coverage"] == 0.5
    assert metrics["raw_wrong_crop_images"] == 2
    assert metrics["out_of_scope"]["images"] == 3
    assert metrics["out_of_scope"]["named_disease_rate"] == pytest.approx(1 / 3)
    assert metrics["out_of_scope"]["accepted_images"] == 2
    assert metrics["per_class"]["potato__early_blight"]["precision"] == 0.5
    assert metrics["per_class"]["potato__early_blight"]["recall"] == pytest.approx(1 / 3)
    assert metrics["per_class"]["potato__early_blight"]["groups"] == 2
    assert metrics["per_class"]["potato__healthy"]["recall"] is None
    assert metrics["confusion_rows"] == [*CLASSES, "__unsupported__"]
    assert metrics["confusion_columns"] == [*CLASSES, "uncertain"]
    assert metrics["confusion_matrix"][0] == [1, 0, 0, 0, 2]
    assert metrics["confusion_matrix"][-1] == [1, 1, 0, 0, 1]
    assert report["by_source"]["second"]["images"] == 2
    assert report["by_crop"]["potato"]["images"] == 6

    with (output / "predictions.csv").open(encoding="utf-8", newline="") as stream:
        predictions = list(csv.DictReader(stream))
    assert [row["abstention_reason"] for row in predictions] == [
        "", "below_threshold", "crop_mismatch", "class_disabled", "", "", "crop_mismatch", "",
    ]
    assert predictions[2]["raw_top_class"] == "tomato__late_blight"
    assert predictions[2]["raw_top_crop"] == "tomato"
    assert float(predictions[2]["raw_score"]) == pytest.approx(0.9479149)
    assert predictions[2]["decision"] == "uncertain"


@pytest.mark.parametrize(("changed", "message"), [
    ("unsafe_path", "relative to the dataset root"),
    ("image_hash", "SHA-256 mismatch"),
    ("model_hash", "Artifact SHA-256 mismatch"),
    ("label_order", "Class order must match"),
    ("seen_image", "also appears in the internal manifest"),
    ("duplicate", "Duplicate field image SHA-256"),
])
def test_evaluation_rejects_untrustworthy_inputs(run_fixture, tmp_path, changed, message):
    from ml.doctor.evaluate_field import evaluate

    root, bundle, rows, metadata = run_fixture
    if changed == "unsafe_path":
        rows[0]["path"] = "../0.png"
    elif changed == "image_hash":
        rows[0]["sha256"] = "1" * 64
    elif changed == "model_hash":
        metadata["artifact"]["sha256"] = "1" * 64
    elif changed == "label_order":
        metadata["labels"].reverse()
    elif changed == "seen_image":
        internal = bundle / "manifest.csv"
        write_manifest(internal, rows[:1])
        metadata["manifest_sha256"] = sha256(internal)
    elif changed == "duplicate":
        (root / "copy.png").write_bytes((root / rows[0]["path"]).read_bytes())
        rows[1].update(path="copy.png", sha256=rows[0]["sha256"])
    (bundle / "model.json").write_text(json.dumps(metadata), encoding="utf-8")
    manifest = tmp_path / "field.csv"
    write_manifest(manifest, rows)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match=message):
        evaluate(bundle, root, manifest, output)
    assert not output.exists()


def test_shared_label_metrics_count_other_named_predictions_as_wrong():
    from ml.doctor.evaluate_field import metrics

    rows = [
        dict(truth_class="potato__early_blight", decision="potato__leafroll", raw_top_crop="potato",
             crop="potato", group_id="1", abstention_reason=""),
        dict(truth_class="potato__early_blight", decision="potato__early_blight", raw_top_crop="potato",
             crop="potato", group_id="2", abstention_reason=""),
    ]
    summary = metrics(rows, ["potato__early_blight"], other_class="__other_named_class__")
    assert summary["confusion_matrix"][0] == [1, 1, 0]
    assert summary["per_class"]["potato__early_blight"]["recall"] == .5
    assert summary["accuracy_accepted_known_images"] == .5
    assert summary["coverage"] == 1.0
