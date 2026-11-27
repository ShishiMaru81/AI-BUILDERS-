# Bangladesh field data candidates

Inventory checked 26 November 2026. The three deposit records list a [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/). The downloaded files are under the ignored `work/agrodoctor-kaggle/field-sources/` directory. All three archives passed ZIP CRC checks. This review admits zero rows to the locked external field manifest.

| Deposit | Local archive | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| [Imtiaz et al., 2025, v2](https://data.mendeley.com/datasets/bpfd9cns5g/2) | `bpfd9cns5g-2.zip` | 48,993,830 | `677e32fad7fd3eb3e532e03c137bf570127b2448750d591a382650b9b8f426b1` |
| [Banu and Deb, 2026, v1](https://data.mendeley.com/datasets/d5b3fzpw3g/1) | `d5b3fzpw3g-1.zip` | 36,364,203 | `2eae260d370738a70842fcc027b49e1a1cf1df8528b0e75b179bf4220a86a6c7` |
| [Bapari et al., 2025, v1](https://data.mendeley.com/datasets/74zvtzx9pr/1) | `74zvtzx9pr-1.zip` | 777,255,074 | `f1ce0869ca64772e23e4ec9316f52f8b7ab397aaf17510305942533d7b322e97` |

## Tomato leaves from Dinajpur, Thakurgaon and Kushtia

The record lists early blight, late blight, leaf mold, bacterial spot, healthy, black spot and target spot. It reports advice from a Kushtia gardener and garden workers. It gives no farm, plant, or batch mapping and no per-image pathology review. [Deposit and license](https://data.mendeley.com/datasets/bpfd9cns5g/2)

- The folder named `Raw Data` contains 731 JPEG entries at 640 × 640, all without EXIF. The entries have 717 distinct SHA-256 values and only 302 distinct source filename stems before the `.rf.` suffix. Of these stems, 216 occur in multiple files. The folder supplies no image labels. The archive cannot establish 731 independent original captures.
- The separate annotation export has 597 train, 61 validation and 31 test image/label pairs. All 302 source filename stems also occur in this export, and 302 distinct JPEG hashes are shared with the `Raw Data` folder. The archive has 230 annotation files with more than one numeric class and 19 with no annotation rows. The ZIP supplies numeric labels without a class-ID key.
- Keep the entire source for exploratory review. Request the camera originals, numeric class key and capture group mapping. Keep black spot as its own ambiguous source label unless a reviewer provides a documented diagnosis. The bundled splits cannot establish independence by plant or farm.

## Potato leaves from BARI Chattogram

The record describes collection at the BARI station in Khulshi, Chattogram. It reports 804 original photos and 2,400 after augmentation. The nested ZIP contains 2,351 JPEG entries across six source labels. The archive supplies no group mapping, augmentation lineage, or per-image pathology evidence. [Deposit and license](https://data.mendeley.com/datasets/d5b3fzpw3g/1)

| Source folder | `aug_` entries | `orig_` entries | Distinct `orig_` SHA-256 values |
| --- | ---: | ---: | ---: |
| Bacterial Soft Rot | 390 | 7 | 7 |
| Fungal Late Blight | 372 | 20 | 20 |
| Healthy | 376 | 16 | 4 |
| Viral Leaf Roll | 361 | 33 | 33 |
| Viral PVX | 381 | 6 | 6 |
| Viral PVY | 387 | 2 | 2 |
| Total | 2,267 | 84 | 72 |

The `orig_` prefix is the sole source indicator for these 224 × 224 images. All 84 are without EXIF. The archive supplies no potato early blight or tuber photos. Keep the source for exploratory review. Request the 804 camera originals and capture and label records before building a field split.

## Tomato leaves from Nazirpur, Pirojpur

The deposit describes 1,007 leaf-cropped field images with no augmentation. It reports 287 disease-free, 91 Septoria leaf spot, 74 bacterial spot and 53 labeled only `Blight Leaf`. Its other labels are Fusarium wilt (28), mosaic virus (51), yellow leaf (18), shot hole disease (141) and leaf curl (264). The publication supplies no documented plant or farm grouping or expert review for individual labels. [Deposit and license](https://data.mendeley.com/datasets/74zvtzx9pr/1)

The nested `TOMATO_LEAF_DATASET.rar` passed an archive integrity test. It contains 1,007 JPEG and PNG files, and each folder count matches the deposit. The images have numeric basenames with no accompanying capture or label metadata files. Keep `Blight Leaf` unmapped to early or late blight. If source metadata and label review become available, the named Septoria and bacterial spot folders are candidates for a cropped-leaf field benchmark.

## Field holdout requirements

For release evaluation, use original photos with qualified label review, documented capture groups and permission to retain the photos. Reserve whole farms when possible. Keep repeated views and near-duplicates in one group, compare exact hashes and review near-duplicate candidates across the baseline and field inputs, then freeze the manifest before tuning. Report independent plant or group counts by condition. The three deposits above stay outside the Kaggle inputs and the locked field evaluation.
