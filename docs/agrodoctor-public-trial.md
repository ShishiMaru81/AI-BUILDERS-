# AgroDoctor v2 public-data training trial

This trial adds public field photos to the nine-label tomato and potato leaf classifier. AgroDoctor can load the exported MobileNetV3 Small artifact through an optional research preview. Farm-labeled validation is a separate phase.

## Training data and reserved test

| Data | Use | Photos |
| --- | --- | ---: |
| Frozen PlantVillage training split | Training | 2,918 |
| Hossain et al., Bangladesh tomato | Training | 748 |
| Tilahun et al., Holeta potato | Training | 382 |
| Frozen PlantVillage validation split | Checkpoint selection and uncertainty thresholds | 363 |
| Frozen PlantVillage test split | Controlled benchmark | 452 |
| Rachin et al., Bangladesh tomato | Offline exploratory benchmark | 851 |

The preparer preserves the original controlled split and reserves the Rachin archive before adding training images. It compares byte hashes, decoded pixels and difference hashes with the frozen datasets. It removes metadata from the added images and conservatively excludes possible near-duplicates. The last three public cohorts carry deposited labels and a single cohort identifier per source. Farm and plant IDs are unknown. Potato early blight and tomato Septoria still rely on controlled training images. [Data provenance and archive audit](../data/agrodoctor/field-v2-source-audit.md)

The private Kaggle run started from the official MobileNetV3 Small ImageNet weights, unfroze the last two feature blocks, and completed 10 epochs on a Tesla T4. It used batch size 64, seed 2026 and a learning rate of 0.0005. Validation macro-F1 selected epoch 8. The same validation split supplied the per-class score cutoffs. Rachin images stayed outside the Kaggle input. [Saved Kaggle run](https://www.kaggle.com/code/happychamp/agrodoctor-public-leaf-research-v2?scriptVersionId=374693604) · [Kaggle input](https://www.kaggle.com/datasets/happychamp/agrodoctor-public-leaf-trial-v2)

## Verification results

The 6.50 MB export is `agrodoctor-leaf-mobilenetv3-small-a9793a6d813a`. The archive, checkpoint and model checksums matched, and the returned training manifest matched the one sent to Kaggle.

| Benchmark | v1 final decisions agreeing with source labels | v2 final decisions agreeing with source labels |
| --- | ---: | ---: |
| Controlled test, 452 known labels | 423/452 (93.6%) | 427/452 (94.5%) |
| Reserved Rachin public tomato photos | 79/851 (9.3%) | 245/851 (28.8%) |
| Earlier exploratory Bangladesh photos, 446 known labels | 0/446 (0%) | 34/446 (7.6%) |

An uncertain result counts as a miss for a known label. Raw controlled accuracy was 432/452 (95.6%) for both versions. On the Rachin set, v2 agreed on 248/851 raw decisions and accepted 800/851 after applying its cutoffs. Of those 800 accepted decisions, 555 disagreed with the deposited labels. Agreement increased for bacterial spot (2 to 72 of 102), early blight (33 to 130 of 418) and healthy (0 to 27 of 255). Late blight agreement dropped from 44 to 16 of 76. The older exploratory potato subset still yielded no correct named decisions for its four healthy and 20 late-blight images. V2 named a disease on one of 33 potato leafroll challenge photos.

The public-source results support keeping this export in research preview. They measure agreement with deposit labels and do not establish farm-level performance. The local browser preview returned **Possible early blight** on a reserved tomato photo and **Possible late blight** on a controlled test potato photo, then abstained when that same potato photo was submitted as tomato. The preview preserved the plot's empty screening history. The API suite passed 346 tests, the ML suite passed 32, and the frontend suite and production build passed.

## Local research preview

Point the API process variable `AGRODOCTOR_RESEARCH_MODEL_DIR` to the extracted Kaggle results folder containing `model.json` and `model.ts`. Restart the local API with its CPU TorchVision dependencies. AgroDoctor checks the artifact hash, validates the exact training preprocessing and class ordering, and exposes **Preview with research leaf model** on the photo screen. The research route accepts one tomato or potato leaf and keeps the result as a preview. It applies the trained model's per-class cutoffs and checks the selected crop against the joint top score.

Cloud vision and the pinned local models still handle the normal screening paths. The research preview results use the existing crop-specific scouting guidance with the model version shown on the result.
