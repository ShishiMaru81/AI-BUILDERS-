"""Evaluate the frozen produce export on photos outside its development manifest."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from evaluate_field import UNSUPPORTED, breakdown, metrics, model_predictions
from prepare_regional_leaf import records
from train_kaggle import PREPROCESSING, verify_image


def run(bundle, manifest, output):
    metadata = json.loads((bundle / "model.json").read_text(encoding="utf-8"))
    artifact = (bundle / "model.ts").read_bytes()
    if metadata["artifact"]["sha256"] != hashlib.sha256(artifact).hexdigest() or metadata["preprocessing"] != PREPROCESSING:
        raise ValueError("The export or preprocessing does not match the model card")
    development = bundle / "manifest.csv"
    if hashlib.sha256(development.read_bytes()).hexdigest() != metadata["manifest_sha256"]:
        raise ValueError("The development manifest changed")
    developed = {item["sha256"] for item in records(development)}
    class_ids = [row["id"] for row in metadata["labels"] if row["plant_part"] == "produce"]
    if "other__out_of_scope" not in metadata["thresholds"] or metadata["thresholds"]["other__out_of_scope"] is not None:
        raise ValueError("The produce model must abstain for out-of-scope photos")
    paths, rows, seen = [], [], set()
    for row in records(manifest):
        if row["split"] != "test" or row["sha256"] in developed or row["sha256"] in seen:
            raise ValueError("The evaluation contains a duplicate or a development image")
        seen.add(row["sha256"])
        paths.append(verify_image(manifest.parent.resolve(), row["path"], row["sha256"]))
        truth = UNSUPPORTED if row["label"] == "out_of_scope" else f"{row['crop']}__{row['label']}"
        if truth != UNSUPPORTED and truth not in class_ids:
            raise ValueError(f"Unrecognized held-out class: {truth}")
        rows.append({**row, "truth_class": truth})
    predictions = model_predictions(artifact, metadata, rows, paths)
    report = {"model_version": metadata["version"], "evaluation": "public produce image benchmark",
              "overall": metrics(predictions, class_ids),
              "by_source": breakdown(predictions, "source_id", class_ids), "field_validated": False}
    output.mkdir(parents=True, exist_ok=False)
    (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with (output / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, predictions[0].keys())
        writer.writeheader()
        writer.writerows(predictions)
    print(json.dumps({key: report["overall"][key] for key in
                      ("images", "accuracy_known_images", "accuracy_accepted_known_images", "coverage", "out_of_scope")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.bundle, args.manifest, args.output)
