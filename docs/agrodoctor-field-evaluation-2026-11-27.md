# AgroDoctor Kaggle baseline field evaluation

**27 November 2026 · Version 1**

**Decision.** Keep the trained checkpoint as a research baseline. The exported model reproduced its controlled PlantVillage result locally and failed to transfer to the field-source photos in this evaluation. It matched **0 of 446** labels both before and after applying the saved uncertainty rules.

## Model and checks

The run trained a MobileNetV3 Small classification head for 12 epochs on Kaggle with a Tesla T4 and selected epoch 9 on validation. The checkpoint identifies itself as `agrodoctor-leaf-mobilenetv3-small-8ac560d58068`. The expected photos, label order, preprocessing and uncertainty thresholds stayed fixed throughout evaluation. [Saved Kaggle run](https://www.kaggle.com/code/happychamp/agrodoctor-tomato-and-potato-leaf-training?scriptVersionId=374676087)

- The output ZIP passed integrity checks. All nine recorded file hashes matched, including the 3,733-image training manifest. The local CPU export reproduced the saved reference logits and both full controlled-test confusion matrices.
- Field preparation checked 479 selected images against all 3,733 baseline training, validation, and test images. No encoded hash, decoded RGB hash, or conservative difference-hash match was found across those sets. The preparation excluded 42 source candidates for exact duplicates, a conflicting label, or near-duplicate similarity. Heuristic similarity screening can miss transformed copies.
- Two CPU replays independently confirmed all 479 top labels and final verdicts. One used the original trainer's dataset and prediction code, and another used the standard TorchVision transforms directly. The result also held before applying the saved thresholds.

## Results

| Test | Photos scored | Top prediction matched label | Final decision matched label | Final decision named a class |
| --- | ---: | ---: | ---: | ---: |
| Controlled PlantVillage test | 452 | 432/452 (95.6%) | 423/452 (93.6%) | 437/452 (96.7%) |
| Bangladesh source-labeled photos, supported labels | 446 | 0/446 (0%) | 0/446 (0%) | 266/446 (59.6%) |

The final decision follows the saved crop check and score cutoffs. A result of **Uncertain** counts as a missed detection for a photo with a supported label. The table uses photo-level counts. The sources provide neither verified individual-plant IDs nor independently reviewed diagnoses.

| Source label | Photos | Correct final decisions | Uncertain | Incorrect named decisions |
| --- | ---: | ---: | ---: | ---: |
| Tomato healthy | 264 | 0 | 89 | 175 |
| Tomato bacterial spot | 71 | 0 | 31 | 40 |
| Tomato Septoria leaf spot | 87 | 0 | 37 | 50 |
| Potato healthy | 4 | 0 | 3 | 1 |
| Potato late blight | 20 | 0 | 20 | 0 |

The model named diseases for 175 of 264 healthy-labeled tomato photos, a **66.3% false-alert rate** for that source label. It returned **Uncertain** on all 20 potato late-blight-labeled photos. The raw top prediction belonged to tomato in 18 of those cases. The training run had disabled named healthy-potato output because validation evidence could not support a threshold.

The separate challenge set contained 33 potato leafroll-labeled photos, a condition outside the trained label list. The model returned **Uncertain** on 31 and called two early blight. These 33 rows are excluded from the known-label accuracy above. Both photos and sample counts come from the deposited source, so this challenge describes one source and one unsupported condition.

The farmer's previously shared potato photo also returned **Uncertain** because the top result was on tomato. It was a qualitative check and contributes no row to the accuracy figures. The disease on that photo remains unconfirmed.

## Comparison with the existing local classifier

On the same 446 photos, the pinned PlantVillage model `plantvillage-d33601185b32` also matched none of the source labels after AgroDoctor's normal decision rules. It issued a named result on 113 photos (25.3%). The new candidate issued a named result on 266 (59.6%). Every named result from either model disagreed with the deposited label on this set. The old model made one correct raw prediction before abstention and rejected 88 photos at its image-quality check. The new evaluation used the candidate model's frozen crop and score checks directly. These differences in quality gating matter when comparing the rates of named results.

## What the field photos can establish

The 446 scored photos came from cropped tomato images from Pirojpur and BARI Chattogram potato images marked as originals by the depositor. The third downloaded source uses numeric labels without a class key and stayed outside the evaluation. Tomato leaf mold and tomato early and late blight lacked usable source-labeled eval rows in these sets. The same applies to potato early blight. [Pirojpur tomato archive](https://data.mendeley.com/datasets/74zvtzx9pr/1) · [BARI potato archive](https://data.mendeley.com/datasets/d5b3fzpw3g/1) · [Archive audit](../data/agrodoctor/field-sources.md)

One tomato JPEG appeared in both the bacterial-spot and Septoria folders and was excluded from evaluation. All retained tomato disease photos were JPEG. Healthy-labeled tomatoes included 168 PNGs and 96 JPEGs, including white-background cutouts. This variation is a plausible source of shortcuts and limits interpretation. Visual review also found overlap in symptoms among some stated classes. The accuracy figures describe agreement with these deposit labels on this sample. A multi-farm test with qualified labeling remains necessary for a field performance claim.

## Before a field pilot

Collect labeled phone photos from several farms with both full-plant views and lesion close-ups. Include healthy leaves, the common look-alikes, and enough examples per class. Fine-tune with separate field training and validation sets, tune uncertainty thresholds there, and evaluate on fresh held-out farms. Preserve this exploratory set and its report for comparison. Keep farmer-facing disease labels tied to the planned per-condition precision, recall, and coverage checks. [AgroDoctor Kaggle plan](superpowers/plans/2026-11-26-agrodoctor-kaggle.md)
