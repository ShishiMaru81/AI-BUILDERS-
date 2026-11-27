"""Build a private Kaggle input archive from a baseline or field development manifest."""

import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import NamedTemporaryFile
from zipfile import ZipFile


WEIGHT_NAME = 'mobilenet_v3_small-047dcff4.pth'
WEIGHT_SHA256 = '047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f'
TRAINER = Path(__file__).with_name('train_kaggle.py')


def sha256_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build_bundle(data: Path, weights: Path, output: Path, *, field_development=False, purpose=None) -> None:
    if sha256_file(weights) != WEIGHT_SHA256:
        raise ValueError('Pretrained weights do not match the official TorchVision checkpoint.')

    manifest = data / 'manifest.csv'
    sources = data / 'sources.json'
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if field_development and any(row.get('split') not in ('train', 'val') for row in rows):
        raise ValueError('A field development archive can contain only train and val rows. Keep holdout photos offline.')
    validation = [
        sys.executable, str(TRAINER), '--root', str(data), '--manifest', str(manifest),
        '--sources', str(sources), '--validate-only',
    ]
    if field_development:
        validation.append('--skip-test')
    subprocess.run(validation, check=True)

    files = {
        'data/manifest.csv': manifest,
        'data/sources.json': sources,
        'code/train_kaggle.py': TRAINER,
        f'weights/{WEIGHT_NAME}': weights,
    }
    if not field_development:
        for name in ('dataset_summary.json', 'source-card.md'):
            path = data / name
            if path.is_file():
                files[f'data/{name}'] = path
    marker = {
        'bundle_version': 1,
        'purpose': purpose or ('Tomato and potato field development' if field_development
                               else 'Controlled-image tomato and potato leaf baseline'),
        'weight_source': f'https://download.pytorch.org/models/{WEIGHT_NAME}',
        'files': {name: sha256_file(path) for name, path in files.items()},
    }
    if field_development:
        marker['development_only'] = True

    data_root = data.resolve()
    for row in rows:
        relative = PurePosixPath(row['path'])
        image = (data_root / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not image.is_relative_to(data_root):
            raise ValueError(f'Invalid manifest image path: {relative}')
        files[f'data/{relative.as_posix()}'] = image

    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=output.stem, suffix='.zip.tmp', dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with ZipFile(temporary, 'w') as archive:
            archive.writestr('agrodoctor-input.json', json.dumps(marker, indent=2) + '\n')
            for name, path in sorted(files.items()):
                archive.write(path, name)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    print(f'Output: {output.resolve()}')
    print(f'SHA-256: {sha256_file(output)}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--weights', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--field-development', action='store_true',
                        help='Package train and validation only, and keep test farms offline')
    parser.add_argument('--purpose', help='Description of the training dataset recorded in its bundle')
    args = parser.parse_args()
    try:
        build_bundle(args.data, args.weights, args.output, field_development=args.field_development, purpose=args.purpose)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'AgroDoctor Kaggle bundle: {exc}\n')


if __name__ == '__main__':
    main()
