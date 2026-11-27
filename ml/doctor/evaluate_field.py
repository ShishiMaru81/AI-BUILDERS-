"""Evaluate a frozen Kaggle leaf classifier on an exploratory external manifest."""

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageOps

if __package__:
    from .train_kaggle import APPROVED_LABELS, PREPROCESSING, uncertainty_decisions, verify_image, write_json
else:
    from train_kaggle import APPROVED_LABELS, PREPROCESSING, uncertainty_decisions, verify_image, write_json


MANIFEST_FIELDS = (
    "path", "crop", "plant_part", "label", "source_id", "group_id", "sha256", "label_evidence",
)
PREDICTION_FIELDS = MANIFEST_FIELDS + (
    "truth_class", "raw_top_class", "raw_top_crop", "raw_score", "raw_threshold",
    "decision", "abstention_reason",
)
BASELINE_FIELDS = ("baseline_raw_top_class", "baseline_raw_score", "baseline_decision", "baseline_abstention_reason")
UNSUPPORTED = "__unsupported__"
UNCERTAIN = "uncertain"
BATCH_SIZE = 24


def load_bundle(bundle):
    metadata_bytes = (bundle / "model.json").read_bytes()
    metadata = json.loads(metadata_bytes)
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("Expected schema_version 1 in model.json")
    if metadata.get("output") != "joint_logits" or metadata.get("score_type") != "uncalibrated_joint_softmax":
        raise ValueError("Expected joint logits and uncalibrated joint softmax scores")
    if metadata.get("preprocessing") != PREPROCESSING:
        raise ValueError("Preprocessing does not match the trainer contract")
    if not isinstance(metadata.get("version"), str) or not metadata["version"].strip():
        raise ValueError("Model version is required")
    labels = metadata.get("labels")
    if not isinstance(labels, list) or len(labels) < 2:
        raise ValueError("Expected multiple crop-qualified leaf classes")
    for item in labels:
        if not isinstance(item, dict):
            raise ValueError("Each class needs a crop, plant_part, label and ID")
        crop, label = item.get("crop"), item.get("label")
        if (not isinstance(crop, str) or not isinstance(label, str)
                or item.get("plant_part") != "leaf" or label not in APPROVED_LABELS.get(crop, set())
                or item.get("id") != f"{crop}__{label}"):
            raise ValueError(f"Invalid crop-qualified leaf class: {item}")
    class_ids = [item["id"] for item in labels]
    if len(set(class_ids)) != len(class_ids) or class_ids != sorted(class_ids):
        raise ValueError("Class order must match the trainer's sorted, unique crop-qualified IDs")
    if {item["crop"] for item in labels} != set(APPROVED_LABELS):
        raise ValueError("Expected classes for both trained crops")
    thresholds = metadata.get("thresholds")
    if not isinstance(thresholds, dict) or thresholds.keys() != set(class_ids):
        raise ValueError("Thresholds must specify exactly the exported classes")
    for class_id, cutoff in thresholds.items():
        if cutoff is not None and (type(cutoff) not in (float, int) or not math.isfinite(cutoff)
                                   or not 0 <= cutoff <= 1):
            raise ValueError(f"Invalid threshold for {class_id}")
    artifact = metadata.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("path") != "model.ts":
        raise ValueError("The exported artifact must be model.ts")
    artifact_bytes = (bundle / "model.ts").read_bytes()
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    if artifact_sha256 != artifact.get("sha256"):
        raise ValueError("Artifact SHA-256 mismatch for model.ts")
    if artifact.get("size_bytes") != len(artifact_bytes):
        raise ValueError("Artifact size mismatch for model.ts")
    metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
    checksums = bundle / "SHA256SUMS"
    if checksums.is_file():
        relevant = {}
        for line in checksums.read_text(encoding="ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if match is None:
                raise ValueError("Invalid SHA256SUMS line")
            digest, filename = match.groups()
            if filename in ("model.ts", "model.json"):
                if filename in relevant:
                    raise ValueError(f"Duplicate SHA256SUMS entry for {filename}")
                relevant[filename] = digest
        if relevant != {"model.ts": artifact_sha256, "model.json": metadata_sha256}:
            raise ValueError("SHA256SUMS must match model.ts and model.json")
    return metadata, metadata_sha256, artifact_bytes


def internal_hashes(bundle, metadata):
    internal = bundle / "manifest.csv"
    if not internal.is_file():
        return None
    data = internal.read_bytes()
    if hashlib.sha256(data).hexdigest() != metadata.get("manifest_sha256"):
        raise ValueError("Internal manifest SHA-256 mismatch")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    if not reader.fieldnames or "sha256" not in reader.fieldnames:
        raise ValueError("Internal manifest requires a sha256 column")
    hashes = {row["sha256"] for row in reader}
    if not hashes or any(digest is None or re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in hashes):
        raise ValueError("Internal manifest contains invalid image hashes")
    return hashes


def load_field_manifest(root, data, class_ids, seen_internal):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Field image root must be a directory")
    rows, images = [], []
    existing_hashes, existing_paths = set(), set()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    if not reader.fieldnames or not set(MANIFEST_FIELDS).issubset(reader.fieldnames):
        raise ValueError(f"Field manifest requires columns: {', '.join(MANIFEST_FIELDS)}")
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("Field manifest contains duplicate column headings")
    for record in reader:
        try:
            if None in record or any(record[field] is None for field in reader.fieldnames):
                raise ValueError("Row does not match the CSV column count")
            row = {key: record[key].strip() for key in MANIFEST_FIELDS}
            if row["plant_part"] != "leaf":
                raise ValueError("plant_part must be leaf")
            if re.fullmatch(r"[a-z][a-z0-9_-]*", row["crop"]) is None:
                raise ValueError("crop must be a lowercase identifier")
            class_id = UNSUPPORTED if row["label"] == UNSUPPORTED else f"{row['crop']}__{row['label']}"
            if class_id != UNSUPPORTED and class_id not in class_ids:
                raise ValueError(f"Unknown field class {class_id}; use {UNSUPPORTED} for challenge rows")
            if not all(row[key] for key in ("source_id", "group_id", "label_evidence")):
                raise ValueError("source_id, group_id and label_evidence must be present")
            image = verify_image(root, row["path"], row["sha256"])
            if image in existing_paths:
                raise ValueError("Image path appears more than once")
            if row["sha256"] in existing_hashes:
                raise ValueError("Duplicate field image SHA-256")
            if seen_internal is not None and row["sha256"] in seen_internal:
                raise ValueError("Field image SHA-256 also appears in the internal manifest")
            existing_paths.add(image)
            existing_hashes.add(row["sha256"])
            rows.append({**row, "truth_class": class_id})
            images.append(image)
        except ValueError as exc:
            raise ValueError(f"Field manifest line {reader.line_num}: {exc}") from exc
    if not rows:
        raise ValueError("Field manifest contains no evaluation images")
    return rows, images


def model_predictions(artifact_bytes, metadata, rows, images):
    import torch
    from torchvision import transforms

    torch.set_num_threads(min(4, torch.get_num_threads()))
    model = torch.jit.load(io.BytesIO(artifact_bytes), map_location="cpu").eval()
    prep = metadata["preprocessing"]
    size = prep["image_size"]
    transform = transforms.Compose([
        transforms.Resize((size, size), interpolation=transforms.InterpolationMode.BILINEAR),
        transforms.ToTensor(),
        transforms.Normalize(prep["mean"], prep["std"]),
    ])
    class_ids = [entry["id"] for entry in metadata["labels"]]
    crops = [entry["crop"] for entry in metadata["labels"]]
    thresholds = [metadata["thresholds"][class_id] for class_id in class_ids]
    predictions = []
    with torch.inference_mode():
        for offset in range(0, len(rows), BATCH_SIZE):
            tensors = []
            for path in images[offset:offset + BATCH_SIZE]:
                with Image.open(path) as image:
                    tensors.append(transform(ImageOps.exif_transpose(image).convert(prep["color_mode"])))
            logits = model(torch.stack(tensors))
            if (not isinstance(logits, torch.Tensor) or logits.shape != (len(tensors), len(class_ids))
                    or not bool(torch.isfinite(logits).all())):
                raise ValueError("Model output does not match the ordered classes or has nonfinite logits")
            probabilities = logits.float().softmax(dim=1).numpy()
            winners = probabilities.argmax(axis=1)
            batch = rows[offset:offset + len(tensors)]
            accepted = uncertainty_decisions(probabilities, crops, [row["crop"] for row in batch], thresholds)
            for index, (row, winner, final) in enumerate(zip(batch, winners, accepted)):
                reason = ""
                if final < 0:
                    if crops[winner] != row["crop"]:
                        reason = "crop_mismatch"
                    elif thresholds[winner] is None:
                        reason = "class_disabled"
                    else:
                        reason = "below_threshold"
                predictions.append({
                    **row,
                    "raw_top_class": class_ids[winner],
                    "raw_top_crop": crops[winner],
                    "raw_score": float(probabilities[index, winner]),
                    "raw_threshold": thresholds[winner],
                    "decision": class_ids[final] if final >= 0 else UNCERTAIN,
                    "abstention_reason": reason,
                })
    return predictions


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def metrics(rows, class_ids, *, other_class=None):
    truth_classes = [*class_ids, UNSUPPORTED]
    decision_classes = [*class_ids, UNCERTAIN]
    if other_class is not None:
        decision_classes.insert(-1, other_class)
    confusion = Counter(
        (row["truth_class"], row["decision"] if row["decision"] in decision_classes else other_class)
        for row in rows
    )
    actual = Counter(row["truth_class"] for row in rows)
    predicted = Counter(row["decision"] for row in rows)
    groups = defaultdict(set)
    for row in rows:
        groups[row["truth_class"]].add(row["group_id"])
    per_class = {}
    for class_id in class_ids:
        true_positives = confusion[class_id, class_id]
        per_class[class_id] = {
            "images": actual[class_id],
            "groups": len(groups[class_id]),
            "predicted": predicted[class_id],
            "true_positives": true_positives,
            "precision": ratio(true_positives, predicted[class_id]),
            "recall": ratio(true_positives, actual[class_id]),
        }
    known_images = len(rows) - actual[UNSUPPORTED]
    accepted = len(rows) - predicted[UNCERTAIN]
    correct = sum(confusion[class_id, class_id] for class_id in class_ids)
    wrong_crop = sum(row["raw_top_crop"] not in ("", row["crop"]) for row in rows)
    unsupported_accepted = actual[UNSUPPORTED] - confusion[UNSUPPORTED, UNCERTAIN]
    disease_count = sum(confusion[UNSUPPORTED, class_id] for class_id in class_ids
                        if not class_id.endswith("__healthy"))
    return {
        "images": len(rows),
        "groups": len({row["group_id"] for row in rows}),
        "known_images": known_images,
        "accepted_images": accepted,
        "coverage": ratio(accepted, len(rows)),
        "abstention_rate": ratio(predicted[UNCERTAIN], len(rows)),
        "accuracy_known_images": ratio(correct, known_images),
        "accuracy_accepted_known_images": ratio(correct, accepted - unsupported_accepted),
        "raw_wrong_crop_images": wrong_crop,
        "raw_wrong_crop_rate": ratio(wrong_crop, sum(bool(row["raw_top_crop"]) for row in rows)),
        "abstention_reasons": dict(sorted(Counter(
            row["abstention_reason"] for row in rows if row["abstention_reason"]
        ).items())),
        "per_class": per_class,
        "confusion_rows": truth_classes,
        "confusion_columns": decision_classes,
        "confusion_matrix": [[confusion[truth, pred] for pred in decision_classes] for truth in truth_classes],
        "out_of_scope": {
            "images": actual[UNSUPPORTED],
            "groups": len(groups[UNSUPPORTED]),
            "accepted_images": unsupported_accepted,
            "acceptance_rate": ratio(unsupported_accepted, actual[UNSUPPORTED]),
            "named_disease_images": disease_count,
            "named_disease_rate": ratio(disease_count, actual[UNSUPPORTED]),
        },
    }


def breakdown(rows, key, class_ids, **kwargs):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[key]].append(row)
    return {name: metrics(group, class_ids, **kwargs) for name, group in sorted(grouped.items())}


def evaluate_baseline(root, predictions, images, class_ids):
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from apps.api.app.doctor_models import CROPS, DoctorRegistry, crop_for_label

    registry = DoctorRegistry(root)
    # The public card can represent the configured cloud provider. Use the pinned local bundle.
    card = registry._bundle(CROPS["potato"]["model_id"])["card"]
    if not card["available"]:
        raise ValueError(f"Pinned PlantVillage baseline is unavailable: {card['artifact_error']}")
    baseline_ids = {
        label: f"{crop_for_label(label)}__{label.split('___', 1)[1].lower()}" for label in card["labels"]
    }
    common = [class_id for class_id in class_ids if class_id in baseline_ids.values()]
    candidate_rows, baseline_rows = [], []
    for candidate, path in zip(predictions, images):
        if candidate["truth_class"] not in common:
            continue
        with Image.open(path) as source:
            result = registry.infer(ImageOps.exif_transpose(source).convert("RGB"), candidate["crop"])["classification"]
        raw_label = result["alternatives"][0]["label"] if result["alternatives"] else ""
        baseline = {
            **candidate,
            "raw_top_class": baseline_ids.get(raw_label, ""),
            "raw_top_crop": crop_for_label(raw_label) or "",
            "raw_score": result["score"],
            "decision": UNCERTAIN if result["abstained"] else baseline_ids[result["top_label"]],
            "abstention_reason": result["rejection_reason"] or "",
        }
        candidate_rows.append(candidate)
        baseline_rows.append(baseline)
        for field in ("raw_top_class", "raw_score", "decision", "abstention_reason"):
            candidate[f"baseline_{field}"] = baseline[field]

    def summary(rows):
        other = "__other_named_class__"
        return {
            "overall": metrics(rows, common, other_class=other),
            "by_source": breakdown(rows, "source_id", common, other_class=other),
            "by_crop": breakdown(rows, "crop", common, other_class=other),
        }

    return {
        "scope": "Same exploratory photos with a ground-truth label shared exactly by both models",
        "baseline_model_version": card["version"],
        "baseline_artifact_sha256": card["artifact_sha256"],
        "shared_classes": common,
        "shared_images": len(baseline_rows),
        "shared_groups": len({row["group_id"] for row in baseline_rows}),
        "candidate": summary(candidate_rows),
        "baseline": summary(baseline_rows),
        "limitations": [
            "Baseline uses the existing local registry's preprocessing, photo-quality checks, and abstention policy.",
            "The Kaggle candidate uses its frozen model-level policy.",
            "The pinned baseline's image-level training provenance is unavailable for cross-source overlap checks.",
        ],
    }


def evaluate(bundle, root, manifest, output, *, baseline_root=None):
    metadata, metadata_sha256, artifact_bytes = load_bundle(bundle)
    class_ids = [row["id"] for row in metadata["labels"]]
    seen_internal = internal_hashes(bundle, metadata)
    manifest_data = manifest.read_bytes()
    rows, images = load_field_manifest(root, manifest_data, class_ids, seen_internal)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"Output directory must be empty: {output}")
    predictions = model_predictions(artifact_bytes, metadata, rows, images)

    report = {
        "schema_version": 1,
        "evaluation_type": "exploratory_external_field",
        "model_version": metadata["version"],
        "artifact_sha256": metadata["artifact"]["sha256"],
        "model_metadata_sha256": metadata_sha256,
        "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
        "internal_manifest_sha256": metadata.get("manifest_sha256"),
        "checked_internal_exact_hash_overlap": seen_internal is not None,
        "thresholds": metadata["thresholds"],
        "score_type": metadata["score_type"],
        "synthetic_smoke": metadata.get("synthetic_smoke", False),
        "field_validated": False,
        "release_approved": False,
        "overall": metrics(predictions, class_ids),
        "by_source": breakdown(predictions, "source_id", class_ids),
        "by_crop": breakdown(predictions, "crop", class_ids),
        "limitations": [
            "Photo-level metrics are descriptive of this manifest.",
            "Group counts describe manifest identifiers. Confirm capture provenance before treating groups as independent plants.",
            "Exact SHA-256 overlap checks do not detect transformed or near-duplicate images.",
            "The field sample is exploratory and cannot establish pilot eligibility or calibrated uncertainty.",
        ],
    }
    fields = PREDICTION_FIELDS
    if baseline_root is not None:
        report["baseline_comparison"] = evaluate_baseline(baseline_root, predictions, images, class_ids)
        fields += BASELINE_FIELDS
    output.mkdir(parents=True, exist_ok=True)
    with (output / "predictions.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(predictions)
    write_json(output / "metrics.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="Extracted Kaggle run directory")
    parser.add_argument("--root", required=True, type=Path, help="Root of the field image paths")
    parser.add_argument("--manifest", required=True, type=Path, help="Exploratory field manifest CSV")
    parser.add_argument("--output", required=True, type=Path, help="New or empty evaluation output directory")
    parser.add_argument("--baseline-root", type=Path, help="Optional directory containing the pinned plantvillage bundle")
    args = parser.parse_args()
    try:
        report = evaluate(args.bundle, args.root, args.manifest, args.output, baseline_root=args.baseline_root)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Field evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "exploratory_metrics_written", "images": report["overall"]["images"],
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
