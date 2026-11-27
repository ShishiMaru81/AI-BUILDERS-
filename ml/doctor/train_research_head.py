"""Fit a lightweight crop-photo head and select abstention thresholds on development data."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps
from torch import nn
from torchvision import models, transforms

from train_kaggle import PREPROCESSING, file_sha256, verify_image


def read_partition(root, manifest):
    root = root.resolve(strict=True)
    partitions = {"train": [], "val": []}
    seen_hashes, role_by_group = set(), {}
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            role = row["split"]
            if role not in partitions:
                raise ValueError("This trainer accepts only train and validation data")
            group = (row["source_id"], row["group_id"])
            if role_by_group.setdefault(group, role) != role or row["sha256"] in seen_hashes:
                raise ValueError(f"Repeated image or cross-split group at {row['path']}")
            row["photo"] = verify_image(root, row["path"], row["sha256"])
            row["class_id"] = "other__out_of_scope" if row["label"] == "out_of_scope" else f"{row['crop']}__{row['label']}"
            seen_hashes.add(row["sha256"])
            partitions[role].append(row)
    if not all(partitions.values()):
        raise ValueError("Both training and validation data are required")
    if not {row["class_id"] for row in partitions["val"]} <= {row["class_id"] for row in partitions["train"]}:
        raise ValueError("Validation labels must be represented in training")
    return partitions


def validation_macro(expected, predicted):
    f1 = []
    for class_index in np.unique(expected):
        correct = np.count_nonzero((expected == class_index) & (predicted == class_index))
        denominator = np.count_nonzero(expected == class_index) + np.count_nonzero(predicted == class_index)
        f1.append(2 * correct / denominator)
    return float(np.mean(f1))


def selective_thresholds(probabilities, expected, class_ids, rows):
    """Use only development rows and reject classes with thin or low precision evidence."""
    winners = probabilities.argmax(axis=1)
    scores = probabilities[np.arange(len(rows)), winners]
    eligible_crop = np.array([class_ids[winner].split("__")[0] == row["crop"] for winner, row in zip(winners, rows)])
    thresholds, evidence = {}, {}
    for index, class_id in enumerate(class_ids):
        thresholds[class_id] = None
        evidence[class_id] = {"correct": 0, "accepted": 0, "precision": None, "eligible_labels": int((expected == index).sum())}
        if class_id == "other__out_of_scope":
            continue
        for cutoff in (0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98, 0.99, 0.995):
            accepted = (winners == index) & eligible_crop & (scores >= cutoff)
            count = int(accepted.sum())
            correct = int((accepted & (expected == index)).sum())
            if count >= 10 and correct / count >= 0.85:
                thresholds[class_id] = cutoff
                evidence[class_id].update(correct=correct, accepted=count, precision=correct / count)
                break
    return thresholds, evidence


def image_features(model, rows):
    prep = PREPROCESSING
    transform = transforms.Compose([
        transforms.Resize((prep["image_size"], prep["image_size"]), interpolation=transforms.InterpolationMode.BILINEAR),
        transforms.ToTensor(), transforms.Normalize(prep["mean"], prep["std"]),
    ])
    layers = nn.Sequential(model.features, model.avgpool, nn.Flatten(1), *list(model.classifier.children())[:-1]).eval()
    chunks = []
    with torch.inference_mode():
        for start in range(0, len(rows), 32):
            batch = []
            for row in rows[start:start + 32]:
                with Image.open(row["photo"]) as image:
                    batch.append(transform(ImageOps.exif_transpose(image).convert("RGB")))
            chunks.append(layers(torch.stack(batch)))
    return torch.cat(chunks).clone()


def training_weights(rows):
    by_source_class = Counter((row["source_id"], row["class_id"]) for row in rows)
    source_count = Counter(label for _, label in by_source_class)
    weights = torch.tensor([1 / (source_count[row["class_id"]] * by_source_class[row["source_id"], row["class_id"]])
                            for row in rows], dtype=torch.float32)
    return weights / weights.mean()


def export(args):
    torch.manual_seed(2026)
    torch.set_num_threads(4)
    data = read_partition(args.root, args.manifest)
    train_rows, val_rows = data["train"], data["val"]
    class_ids = sorted({row["class_id"] for row in train_rows})
    label_names = {name: index for index, name in enumerate(class_ids)}
    net = models.mobilenet_v3_small(weights=None)
    if args.checkpoint:
        checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
        if [row["id"] for row in checkpoint["labels"]] != class_ids:
            raise ValueError("Initial checkpoint has a different label order")
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, len(class_ids))
        net.load_state_dict(checkpoint["model_state_dict"])
    else:
        net.load_state_dict(torch.load(args.weights, map_location="cpu", weights_only=True))
        net.classifier[-1] = nn.Linear(net.classifier[-1].in_features, len(class_ids))
    net.eval()
    if args.channels_last:
        net.to(memory_format=torch.channels_last)
    args.output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"extracting_train_features": len(train_rows), "development": len(val_rows)}), flush=True)
    train_x = image_features(net, train_rows)
    val_x = image_features(net, val_rows)
    train_y = torch.tensor([label_names[row["class_id"]] for row in train_rows])
    val_y = np.array([label_names[row["class_id"]] for row in val_rows])
    source_groups = defaultdict(list)
    for index, row in enumerate(val_rows):
        source_groups[row["source_id"]].append(index)
    layer = net.classifier[-1]
    initial = layer.weight.detach().clone()
    training_inputs = training_weights(train_rows)
    optimizer = torch.optim.Adam(layer.parameters(), lr=0.002)
    start = 0 if args.checkpoint else 1
    best_score = -1
    steps = 160
    for step in range(start, steps + 1):
        if step:
            optimizer.zero_grad()
            loss = (nn.functional.cross_entropy(layer(train_x), train_y, reduction="none") * training_inputs).mean()
            loss = loss + (0.3 if args.checkpoint else 0.01) * (layer.weight - initial).square().mean()
            loss.backward()
            optimizer.step()
        if step % 8 and step != steps:
            continue
        with torch.no_grad():
            predictions = layer(val_x).argmax(1).numpy()
        per_source = {source: validation_macro(val_y[indices], predictions[indices])
                      for source, indices in source_groups.items()}
        score = float(np.mean(list(per_source.values())))
        if score > best_score:
            best_score, best_step = score, step
            best_state, best_sources = deepcopy(layer.state_dict()), per_source
    layer.load_state_dict(best_state)
    indices = [index for index, row in enumerate(val_rows) if row["source_id"] != "plantvillage_original_rgb"]
    if not indices:
        raise ValueError("Development examples from outside the controlled PlantVillage source are required")
    with torch.inference_mode():
        probabilities = layer(val_x[indices]).softmax(1).numpy()
    thresholds, evidence = selective_thresholds(probabilities, val_y[indices], class_ids, [val_rows[i] for i in indices])
    artifact = args.output / "model.ts"
    example = torch.linspace(-1, 1, 3 * 224 * 224).reshape(1, 3, 224, 224)
    with torch.inference_mode():
        torch.jit.trace(net, example).save(str(artifact))
        imported = torch.jit.load(str(artifact), map_location="cpu").eval()
        torch.testing.assert_close(net(example), imported(example), rtol=1e-4, atol=1e-5)
    digest = file_sha256(artifact)
    labels = []
    for class_id in class_ids:
        examples = [r for r in train_rows if r["class_id"] == class_id]
        crop, label = class_id.split("__", 1)
        if len({r["plant_part"] for r in examples}) != 1:
            raise ValueError("Each class needs a single declared plant part")
        labels.append({"id": class_id, "crop": crop, "label": label, "plant_part": examples[0]["plant_part"]})
    metadata = {
        "schema_version": 1, "version": f"agrodoctor-{args.task}-mobilenetv3-small-{digest[:12]}",
        "architecture": "mobilenet_v3_small", "artifact": {"path": "model.ts", "sha256": digest,
        "size_bytes": artifact.stat().st_size}, "labels": labels, "preprocessing": PREPROCESSING,
        "output": "joint_logits", "score_type": "uncalibrated_joint_softmax", "thresholds": thresholds,
        "threshold_validation": evidence, "manifest_sha256": file_sha256(args.manifest),
        "field_validated": False, "release_approved": False, "synthetic_smoke": False,
    }
    report = {
        "training_images": len(train_rows), "validation_images": len(val_rows), "selected_step": best_step,
        "selected_source_macro_f1": best_sources, "mean_source_macro_f1": best_score,
        "development_thresholds": thresholds, "threshold_validation": evidence, "device": "CPU",
        "initialization_sha256": file_sha256(args.checkpoint or args.weights),
        "fit_classes": dict(Counter(row["class_id"] for row in train_rows)),
    }
    for filename, payload in (("model.json", metadata), ("development-results.json", report)):
        (args.output / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (args.output / "manifest.csv").write_bytes(args.manifest.read_bytes())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", required=True, choices=("leaf", "produce"))
    parser.add_argument("--channels-last", action="store_true")
    initial = parser.add_mutually_exclusive_group(required=True)
    initial.add_argument("--checkpoint", type=Path)
    initial.add_argument("--weights", type=Path)
    export(parser.parse_args())
