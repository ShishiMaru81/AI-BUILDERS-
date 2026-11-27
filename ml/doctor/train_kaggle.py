"""Train and export a research-only tomato and potato leaf classifier.

Preassigned training and validation splits live under the dataset root. A test
split may stay offline with --skip-test. The CPU artifact accepts normalized
NCHW RGB tensors and returns joint logits over the ordered classes.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import random
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps, UnidentifiedImageError, __version__ as pillow_version


SPLITS = ("train", "val", "test")
APPROVED_LABELS = {
    "potato": {"healthy", "early_blight", "late_blight", "leafroll"},
    "tomato": {"healthy", "early_blight", "late_blight", "septoria_leaf_spot", "leaf_mold", "bacterial_spot"},
}
MANIFEST_FIELDS = (
    "path", "crop", "plant_part", "label", "source_id", "farm_id", "plant_id",
    "group_id", "split", "sha256", "label_evidence",
)
SOURCE_FIELDS = ("source_id", "name", "version", "url", "license", "attribution")
PREPROCESSING = {
    "image_size": 224,
    "color_mode": "RGB",
    "resize": "square",
    "interpolation": "bilinear",
    "scale": 255.0,
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "exif_transpose": True,
}
MIN_VALIDATION_PRECISION = 0.85
MIN_VALIDATION_GROUPS = 5
THRESHOLD_GRID = [step / 100 for step in range(50, 101, 5)]


@dataclass(frozen=True)
class LeafImage:
    path: Path
    crop: str
    label: str
    source_id: str
    farm_id: str
    plant_id: str
    group_id: str
    split: str
    sha256: str

    @property
    def class_id(self):
        return f"{self.crop}__{self.label}"


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_sources(path):
    sources = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources.json must be a nonempty list of source records")
    indexed = {}
    for record in sources:
        if not isinstance(record, dict) or any(
            not isinstance(record.get(field), str) or not record[field].strip() for field in SOURCE_FIELDS
        ):
            raise ValueError(f"Each source needs nonempty strings for {', '.join(SOURCE_FIELDS)}")
        source_id = record["source_id"].strip()
        if source_id in indexed:
            raise ValueError(f"Duplicate sources.json source_id: {source_id}")
        indexed[source_id] = record
    return indexed


def verify_image(root, relative, digest):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative or ":" in relative or not path.parts:
        raise ValueError("Expected an image path relative to the dataset root using forward slashes")
    resolved = root.joinpath(*path.parts).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Image path escapes the dataset root")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("sha256 must contain 64 lowercase hexadecimal characters")
    if not resolved.is_file():
        raise ValueError(f"Image file does not exist: {relative}")
    data = resolved.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch for {relative}")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "is_animated", False):
                raise ValueError("Image must contain one frame")
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Cannot decode image: {relative}") from exc
    return resolved


def split_summary(rows):
    planted = {(row.source_id, row.farm_id, row.plant_id) for row in rows if row.plant_id}
    farms = {(row.source_id, row.farm_id) for row in rows if row.farm_id}
    return {
        "images": len(rows),
        "unique_sha256": len({row.sha256 for row in rows}),
        "groups": len({row.group_id for row in rows}),
        "known_plants": len(planted),
        "known_farms": len(farms),
        "by_class": dict(sorted(Counter(row.class_id for row in rows).items())),
        "groups_by_class": {
            class_id: len({row.group_id for row in rows if row.class_id == class_id})
            for class_id in sorted({row.class_id for row in rows})
        },
        "by_source": dict(sorted(Counter(row.source_id for row in rows).items())),
    }


def validate_manifest(root, manifest, source_file, *, allow_no_test=False):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Dataset root must be a directory")
    sources = load_sources(source_file)
    grouped = {split: [] for split in SPLITS}
    seen_paths, group_splits, plant_splits, image_assignments = set(), {}, {}, {}
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not set(MANIFEST_FIELDS).issubset(reader.fieldnames):
            raise ValueError(f"manifest.csv requires columns: {', '.join(MANIFEST_FIELDS)}")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("manifest.csv contains duplicate column headings")
        for record in reader:
            try:
                if None in record or any(record[field] is None for field in MANIFEST_FIELDS):
                    raise ValueError("Row does not match the CSV column count")
                row = {field: record[field].strip() for field in MANIFEST_FIELDS}
                if row["plant_part"] != "leaf":
                    raise ValueError("plant_part must be leaf")
                if row["label"] not in APPROVED_LABELS.get(row["crop"], set()):
                    raise ValueError(f"Unsupported label '{row['label']}' for crop '{row['crop']}'")
                if row["source_id"] not in sources:
                    raise ValueError(f"Unknown source_id: {row['source_id']}")
                if row["split"] not in grouped:
                    raise ValueError(f"split must be one of {', '.join(SPLITS)}")
                if not row["group_id"] or not row["label_evidence"]:
                    raise ValueError("group_id and label_evidence must be present")
                path = verify_image(root, row["path"], row["sha256"])
                leaf = LeafImage(
                    path, row["crop"], row["label"], row["source_id"], row["farm_id"],
                    row["plant_id"], row["group_id"], row["split"], row["sha256"],
                )
                previous = image_assignments.setdefault(leaf.sha256, (leaf.split, leaf.class_id))
                if previous[0] != leaf.split:
                    raise ValueError("Exact image hash crosses splits")
                if previous[1] != leaf.class_id:
                    raise ValueError("Exact image hash has conflicting labels")
                if path in seen_paths:
                    raise ValueError("Image path appears more than once")
                seen_paths.add(path)
                if group_splits.setdefault(leaf.group_id, leaf.split) != leaf.split:
                    raise ValueError(f"group_id crosses splits: {leaf.group_id}")
                if leaf.plant_id:
                    plant = (leaf.source_id, leaf.farm_id, leaf.plant_id)
                    if plant_splits.setdefault(plant, leaf.split) != leaf.split:
                        raise ValueError(f"plant_id crosses splits: {leaf.plant_id}")
                grouped[leaf.split].append(leaf)
            except ValueError as exc:
                raise ValueError(f"Manifest line {reader.line_num}: {exc}") from exc

    split_counts = {split: split_summary(grouped[split]) for split in SPLITS}
    vocabulary = split_counts["train"]["by_class"].keys()
    if len(vocabulary) < 2 or {row.crop for row in grouped["train"]} != set(APPROVED_LABELS):
        raise ValueError("train must contain classes for both tomato and potato")
    for split in ("val", "test"):
        if split == "test" and allow_no_test and not grouped[split]:
            continue
        if split_counts[split]["by_class"].keys() != vocabulary:
            raise ValueError(f"{split} must contain the same crop-qualified classes as train")
    labels = [
        {"id": class_id, "crop": crop, "plant_part": "leaf", "label": label}
        for class_id in sorted(vocabulary)
        for crop, label in [class_id.split("__", 1)]
    ]
    return grouped, {
        "status": "manifest_valid",
        "labels": labels,
        "images": sum(counts["images"] for counts in split_counts.values()),
        "split_counts": split_counts,
        "manifest_sha256": file_sha256(manifest),
        "sources_sha256": file_sha256(source_file),
        "grouping_scope": "Declared groups, source/farm-scoped plant IDs and exact file hashes checked. "
        "Near-duplicate review and source permissions require independent records.",
    }


def uncertainty_decisions(probabilities, label_crops, claimed_crops, thresholds):
    import numpy as np

    predicted = probabilities.argmax(axis=1)
    confidence = probabilities[np.arange(len(predicted)), predicted]
    cutoff = np.array([threshold if threshold is not None else np.inf for threshold in thresholds])
    crop_matches = np.asarray(label_crops)[predicted] == np.asarray(claimed_crops)
    return np.where(crop_matches & (confidence >= cutoff[predicted]), predicted, -1)


def select_thresholds(probabilities, expected, groups, label_crops):
    import numpy as np

    predicted = probabilities.argmax(axis=1)
    confidence = probabilities[np.arange(len(predicted)), predicted]
    crops = np.asarray(label_crops)
    crop_matches = crops[predicted] == crops[expected]
    groups = np.asarray(groups)
    thresholds, evidence = [], []
    for class_index in range(len(crops)):
        eligible = (predicted == class_index) & crop_matches
        chosen, details = None, {"accepted_images": 0, "accepted_groups": 0, "precision": None}
        for candidate in THRESHOLD_GRID:
            accepted = eligible & (confidence >= candidate)
            independent_groups = len(np.unique(groups[accepted]))
            if independent_groups < MIN_VALIDATION_GROUPS:
                continue
            precision = float(np.mean(expected[accepted] == class_index))
            if precision >= MIN_VALIDATION_PRECISION:
                chosen = candidate
                details = {"accepted_images": int(accepted.sum()), "accepted_groups": independent_groups,
                           "precision": precision}
                break
        thresholds.append(chosen)
        evidence.append(details)
    return thresholds, evidence


def classification_metrics(expected, predictions, class_ids, groups, *, allow_abstention=False):
    import numpy as np

    label_count = len(class_ids)
    confusion = np.zeros((label_count, label_count + int(allow_abstention)), dtype=int)
    np.add.at(confusion, (expected, predictions), 1)
    support = confusion.sum(axis=1)
    predicted_counts = confusion.sum(axis=0)
    per_class = {}
    for index, class_id in enumerate(class_ids):
        true_positives = int(confusion[index, index])
        samples, predicted = int(support[index]), int(predicted_counts[index])
        per_class[class_id] = {
            "images": samples,
            "groups": len({group for group, truth in zip(groups, expected) if truth == index}),
            "predicted": predicted,
            "true_positives": true_positives,
            "precision": true_positives / predicted if predicted else None,
            "recall": true_positives / samples,
            "f1": 2 * true_positives / (samples + predicted),
        }
    accepted = int((predictions >= 0).sum())
    correct = int((predictions == expected).sum())
    return {
        "accuracy_all_images": correct / len(expected),
        "accuracy_accepted": correct / accepted if accepted else None,
        "macro_f1": sum(item["f1"] for item in per_class.values()) / label_count,
        "coverage": accepted / len(expected),
        "abstention_rate": 1 - accepted / len(expected),
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
        "confusion_rows": class_ids,
        "confusion_columns": class_ids + (["uncertain"] if allow_abstention else []),
    }


def split_metrics(expected, probabilities, rows, labels, thresholds):
    import numpy as np

    class_ids = [label["id"] for label in labels]
    label_crops = [label["crop"] for label in labels]
    claimed_crops = [row.crop for row in rows]
    groups = [row.group_id for row in rows]
    raw_predictions = probabilities.argmax(axis=1)
    accepted = uncertainty_decisions(probabilities, label_crops, claimed_crops, thresholds)
    wrong_crop = np.asarray(label_crops)[raw_predictions] != np.asarray(claimed_crops)
    return {
        "images": len(rows),
        "groups": len(set(groups)),
        "raw_wrong_crop_images": int(wrong_crop.sum()),
        "raw_wrong_crop_rate": float(wrong_crop.mean()),
        "raw": classification_metrics(expected, raw_predictions, class_ids, groups),
        "selective": classification_metrics(expected, accepted, class_ids, groups, allow_abstention=True),
    }


class LeafImages:
    def __init__(self, rows, label_indices, transform):
        self.rows = rows
        self.label_indices = label_indices
        self.transform = transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(row.path) as source:
            image = self.transform(ImageOps.exif_transpose(source).convert("RGB"))
        return image, self.label_indices[row.class_id]


def predict(model, loader, device):
    import torch

    model.eval()
    targets, probabilities = [], []
    with torch.inference_mode():
        for images, labels in loader:
            targets.append(labels)
            probabilities.append(model(images.to(device)).softmax(dim=1).cpu())
    return torch.cat(targets).numpy(), torch.cat(probabilities).numpy()


def write_json(path, content):
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def training_model(label_count, local_weights, smoke):
    import torch
    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

    class GlobalAveragePool(torch.nn.Module):
        def forward(self, images):
            return images.mean(dim=(-2, -1), keepdim=True)

    default_weights = MobileNet_V3_Small_Weights.DEFAULT
    if smoke:
        model = mobilenet_v3_small(weights=None)
        initialization = {"name": "random_synthetic_smoke"}
    elif local_weights:
        model = mobilenet_v3_small(weights=None)
        model.load_state_dict(torch.load(local_weights, map_location="cpu", weights_only=True))
        initialization = {"name": local_weights.name, "sha256": file_sha256(local_weights)}
    else:
        model = mobilenet_v3_small(weights=default_weights)
        filename = default_weights.url.rsplit("/", 1)[-1]
        cached = Path(torch.hub.get_dir()) / "checkpoints" / filename
        initialization = {"name": default_weights.name, "url": default_weights.url, "sha256": file_sha256(cached)}
    # A 1×1 adaptive average pool equals a spatial mean. The mean also supports
    # deterministic CUDA backpropagation when the final feature blocks are unfrozen.
    for layer in list(model.modules()):
        if isinstance(getattr(layer, "avgpool", None), torch.nn.AdaptiveAvgPool2d) and layer.avgpool.output_size == 1:
            layer.avgpool = GlobalAveragePool()
    model.classifier[-1] = torch.nn.Linear(model.classifier[-1].in_features, label_count)
    return model, initialization


def train(args, grouped, summary, manifest, source_file):
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import numpy as np
    import torch
    import torchvision
    from torchvision import transforms

    started = time.perf_counter()
    use_cuda = args.device != "cpu" and torch.cuda.is_available()
    if args.device == "cuda" and not use_cuda:
        raise ValueError("CUDA was requested but is unavailable. Enable a Kaggle GPU accelerator or use --device cpu.")
    device = torch.device("cuda" if use_cuda else "cpu")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.set_num_threads(min(4, torch.get_num_threads()))

    labels = summary["labels"]
    class_ids = [row["id"] for row in labels]
    label_indices = {class_id: index for index, class_id in enumerate(class_ids)}
    class_counts = summary["split_counts"]["train"]["by_class"]
    class_weights = np.array([1 / math.sqrt(class_counts[class_id]) for class_id in class_ids])
    class_weights /= class_weights.mean()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"Output directory is not empty. Use a new run directory: {output}")
    run_path = output / "run.json"
    run = {
        "seed": args.seed,
        "device": str(device),
        "device_name": torch.cuda.get_device_name() if use_cuda else platform.processor() or "CPU",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "unfreeze_blocks": args.unfreeze_blocks,
        "architecture": "mobilenet_v3_small",
        "learning_rate": args.learning_rate,
        "training_augmentation": {"horizontal_flip_probability": 0.5},
        "class_weighting": {"method": "inverse square root of training class frequency", "weights": dict(zip(class_ids, class_weights.tolist()))},
        "versions": {"python": platform.python_version(), "torch": torch.__version__, "torchvision": torchvision.__version__,
                     "numpy": np.__version__, "pillow": pillow_version, "cuda": torch.version.cuda},
        "code_sha256": file_sha256(Path(__file__)),
        "manifest_sha256": summary["manifest_sha256"],
        "sources_sha256": summary["sources_sha256"],
        "deterministic_algorithms": True,
        "synthetic_smoke": args.smoke,
        "skip_test": args.skip_test,
        "field_validated": False,
    }
    with run_path.open("x", encoding="utf-8") as stream:
        json.dump(run, stream, indent=2)
        stream.write("\n")
    shutil.copyfile(manifest, output / "manifest.csv")
    shutil.copyfile(source_file, output / "sources.json")

    size = PREPROCESSING["image_size"]
    resize = transforms.Resize((size, size), interpolation=transforms.InterpolationMode.BILINEAR)
    normalize = [transforms.ToTensor(), transforms.Normalize(PREPROCESSING["mean"], PREPROCESSING["std"])]
    train_transform = transforms.Compose([resize, transforms.RandomHorizontalFlip(), *normalize])
    eval_transform = transforms.Compose([resize, *normalize])
    loaders = {
        split: torch.utils.data.DataLoader(
            LeafImages(grouped[split], label_indices, train_transform if split == "train" else eval_transform),
            batch_size=args.batch_size, shuffle=split == "train", num_workers=args.workers,
            pin_memory=use_cuda, generator=torch.Generator().manual_seed(args.seed),
        )
        for split in SPLITS if split != "test" or not args.skip_test
    }

    model, initialization = training_model(len(labels), args.pretrained_weights, args.smoke)
    run["initialization"] = initialization
    write_json(run_path, run)
    model.features.requires_grad_(False)
    if args.unfreeze_blocks:
        model.features[-args.unfreeze_blocks:].requires_grad_(True)
    model.to(device)
    optimizer = torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad),
                                 lr=args.learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(class_weights, dtype=torch.float32, device=device))

    best_score = -1.0
    best_epoch = 0
    checkpoint_path = output / "checkpoint.pt"
    with (output / "epochs.jsonl").open("w", encoding="utf-8") as epochs_log:
        for epoch in range(1, args.epochs + 1):
            epoch_started = time.perf_counter()
            model.train()
            model.features.eval()  # Keep pretrained BatchNorm statistics fixed, including for small last batches.
            running_loss = torch.zeros((), device=device)
            for images, targets in loaders["train"]:
                optimizer.zero_grad(set_to_none=True)
                loss = loss_fn(model(images.to(device)), targets.to(device))
                loss.backward()
                optimizer.step()
                running_loss += loss.detach()
            train_loss = float(running_loss.item()) / len(loaders["train"])
            if not math.isfinite(train_loss):
                raise ValueError(f"Training loss is non-finite at epoch {epoch}")
            train_seconds = time.perf_counter() - epoch_started
            expected, probabilities = predict(model, loaders["val"], device)
            validation = classification_metrics(
                expected, probabilities.argmax(axis=1), class_ids, [row.group_id for row in grouped["val"]],
            )
            row = {
                "epoch": epoch, "train_mean_batch_loss": train_loss, "train_seconds": train_seconds,
                "train_images_per_second": len(grouped["train"]) / train_seconds,
                "elapsed_seconds": time.perf_counter() - epoch_started,
                "validation_macro_f1": validation["macro_f1"], "validation_per_class": validation["per_class"],
            }
            if validation["macro_f1"] > best_score:
                best_score, best_epoch = validation["macro_f1"], epoch
                staged = output / "checkpoint.tmp"
                torch.save({"model_state_dict": model.state_dict(), "optimizer_state_dict": optimizer.state_dict(),
                            "epoch": epoch, "validation_macro_f1": best_score, "labels": labels,
                            "seed": args.seed, "manifest_sha256": summary["manifest_sha256"]}, staged)
                staged.replace(checkpoint_path)
            line = json.dumps(row, allow_nan=False)
            epochs_log.write(line + "\n")
            epochs_log.flush()
            print(line, flush=True)

    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    del checkpoint
    expected, probabilities = predict(model, loaders["val"], device)
    thresholds, evidence = select_thresholds(
        probabilities, expected, [row.group_id for row in grouped["val"]], [label["crop"] for label in labels],
    )
    report = {
        "best_epoch": best_epoch,
        "checkpoint_selection": "highest validation raw macro-F1; earliest epoch breaks ties",
        "split_counts": summary["split_counts"],
        "validation": split_metrics(expected, probabilities, grouped["val"], labels, thresholds),
        "test": None,
        "synthetic_smoke": args.smoke,
        "field_metrics": None,
    }
    if not args.skip_test:
        expected, probabilities = predict(model, loaders["test"], device)
        report["test"] = split_metrics(expected, probabilities, grouped["test"], labels, thresholds)

    artifact = output / "model.ts"
    cpu_model = model.cpu().eval()
    reference = torch.linspace(-1, 1, 3 * size * size, dtype=torch.float32).reshape(1, 3, size, size)
    with torch.no_grad():
        torch.jit.trace(cpu_model, reference).save(str(artifact))
        portable = torch.jit.load(str(artifact), map_location="cpu").eval()
        eager_logits = cpu_model(reference)
        portable_logits = portable(reference)
        torch.testing.assert_close(eager_logits, portable_logits, atol=1e-5, rtol=1e-4)
    write_json(output / "inference_check.json", {
        "input": f"torch.linspace(-1, 1, {3 * size * size}, dtype=torch.float32).reshape(1, 3, {size}, {size})",
        "logits": portable_logits[0].tolist(),
        "atol": 1e-5,
        "rtol": 1e-4,
        "max_absolute_export_difference": float((eager_logits - portable_logits).abs().max()),
    })
    write_json(output / "model.json", {
        "schema_version": 1,
        "version": f"agrodoctor-leaf-mobilenetv3-small-{file_sha256(artifact)[:12]}",
        "architecture": run["architecture"],
        "artifact": {"path": artifact.name, "sha256": file_sha256(artifact), "size_bytes": artifact.stat().st_size},
        "checkpoint": {"path": checkpoint_path.name, "sha256": file_sha256(checkpoint_path)},
        "labels": labels,
        "preprocessing": PREPROCESSING,
        "output": "joint_logits",
        "score_type": "uncalibrated_joint_softmax",
        "thresholds": dict(zip(class_ids, thresholds)),
        "threshold_validation": dict(zip(class_ids, evidence)),
        "threshold_policy": {
            "decision": "A named result requires the unrestricted joint top class to match the claimed crop and pass its threshold; null disables a class.",
            "candidate_thresholds": THRESHOLD_GRID,
            "validation_precision_target": MIN_VALIDATION_PRECISION,
            "minimum_accepted_validation_groups": MIN_VALIDATION_GROUPS,
        },
        "manifest_sha256": summary["manifest_sha256"],
        "sources_sha256": summary["sources_sha256"],
        "synthetic_smoke": args.smoke,
        "field_validated": False,
        "release_approved": False,
        "limitations": [
            "Grouped internal results apply only to the included dataset and acquisition conditions.",
            "Independent field performance, unfamiliar inputs and source-domain shift still require evaluation.",
            "Softmax scores express model confidence on this label set and are uncalibrated.",
        ],
    })
    report["elapsed_seconds"] = time.perf_counter() - started
    write_json(output / "metrics.json", report)
    checksums = "".join(f"{file_sha256(path)}  {path.name}\n" for path in sorted(output.iterdir()) if path.is_file())
    (output / "SHA256SUMS").write_text(checksums, encoding="ascii")
    print(json.dumps({"status": "artifacts_written", "output": str(output), "best_epoch": best_epoch,
                      "synthetic_smoke": args.smoke, "field_validated": False}), flush=True)


def build_smoke_fixture(root):
    manifest, source_file = root / "manifest.csv", root / "sources.json"
    write_json(source_file, [{
        "source_id": "synthetic", "name": "Synthetic pipeline smoke fixture", "version": "1",
        "url": "generated locally by train_kaggle.py", "license": "Synthetic fixture",
        "attribution": "AgroDoctor trainer smoke fixture",
    }])
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, MANIFEST_FIELDS)
        writer.writeheader()
        for split_index, split in enumerate(SPLITS):
            for crop_index, crop in enumerate(APPROVED_LABELS):
                for sample in range(3):
                    identity = f"{split}-{crop}-{sample}"
                    path = root / f"{identity}.png"
                    image = Image.new("RGB", (48, 48), (70 * crop_index, 60 * split_index, 45 * sample))
                    image.putpixel((12, 20), (100, 150, 200))
                    image.save(path)
                    writer.writerow({"path": path.name, "crop": crop, "plant_part": "leaf", "label": "healthy",
                                     "source_id": "synthetic", "group_id": identity, "split": split,
                                     "sha256": file_sha256(path), "label_evidence": "synthetic fixture"})
    return manifest, source_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Dataset root for paths in manifest.csv")
    parser.add_argument("--manifest", type=Path, help="Manifest file (default: ROOT/manifest.csv)")
    parser.add_argument("--sources", type=Path, help="Source records (default: ROOT/sources.json)")
    parser.add_argument("--output", type=Path, help="New or empty directory for this run's artifacts")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--unfreeze-blocks", type=int, default=0, choices=range(4),
                        help="Train this many final feature blocks alongside the classifier head")
    parser.add_argument("--pretrained-weights", type=Path, help="Local torchvision MobileNetV3 Small ImageNet state dict")
    parser.add_argument("--validate-only", action="store_true", help="Verify input and report counts without training")
    parser.add_argument("--skip-test", action="store_true", help="Skip test metrics and allow the test split to stay offline")
    parser.add_argument("--smoke", action="store_true", help="Run one epoch on generated synthetic images without pretrained weights")
    args = parser.parse_args()

    if args.epochs < 1 or args.batch_size < 1 or args.workers < 0 or not 0 <= args.seed < 2**32:
        parser.error("Need positive epochs and batch size, nonnegative workers, and a 32-bit unsigned seed")
    if not math.isfinite(args.learning_rate) or args.learning_rate <= 0:
        parser.error("--learning-rate must be finite and positive")
    if args.smoke and any((args.root, args.manifest, args.sources, args.validate_only, args.pretrained_weights)):
        parser.error("--smoke generates its own fixture and does not take real input paths, weights or --validate-only")
    if not args.smoke and args.root is None:
        parser.error("--root is required for dataset validation and training")
    if not args.validate_only and args.output is None:
        parser.error("--output is required for training and smoke runs")

    try:
        if args.smoke:
            args.epochs = 1
            with tempfile.TemporaryDirectory(prefix="agrodoctor-smoke-") as directory:
                root = Path(directory)
                manifest, sources = build_smoke_fixture(root)
                grouped, summary = validate_manifest(root, manifest, sources)
                train(args, grouped, summary, manifest, sources)
            return

        manifest = args.manifest or args.root / "manifest.csv"
        sources = args.sources or args.root / "sources.json"
        grouped, summary = validate_manifest(args.root, manifest, sources, allow_no_test=args.skip_test)
        print(json.dumps(summary, ensure_ascii=True), flush=True)
        if not args.validate_only:
            train(args, grouped, summary, manifest, sources)
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(f"AgroDoctor: {exc}")


if __name__ == "__main__":
    main()
