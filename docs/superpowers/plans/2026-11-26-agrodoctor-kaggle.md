# AgroDoctor AI Kaggle Implementation Plan

**Goal.** Train a lightweight vision model for tomato and potato, validate individual disease results on independent field photos, and give farmers reviewed next steps in Bangla and English.

**Architecture.** The farmer selects the crop and confirms whether the photo shows a leaf or harvested produce. The existing AgroDoctor upload flow checks image quality and sends the photo to the matching versioned model. The result contains a possible condition or an uncertainty reason, followed by reviewed guidance for that crop and plant part.

**Tools.** Private Kaggle Notebook with one available NVIDIA GPU for training, Python and PyTorch for the model, and the existing FastAPI and Next.js application for local integration. Reuse the [project master plan](../../../PLAN.md), [model card](../../model_card.md), and [training pipeline](../../../ml/doctor/README.md) as context. The existing training script accepts tomato labels and has a CPU or CUDA training path. The new workflow extends it to potato and adds an independent field evaluation.

## Scope and responsibilities

| Phase | Crop and part | Initial labels and conditions to evaluate |
| --- | --- | --- |
| 1 | Tomato leaf | Healthy appearance, early blight, late blight, Septoria leaf spot, leaf mold, bacterial spot |
| 1 | Potato leaf | Healthy appearance, early blight, late blight, potato leafroll |
| Follow-on | Tomato and potato leaves | Tomato target spot and yellow leaf curl. Potato virus X and virus Y if the labels and field results support separate outputs. |
| 2 | Tomato fruit | Sound-looking fruit, anthracnose-like lesions, gray mold-like growth, blossom-end rot, other visible decay |
| 2 | Potato tuber | Sound-looking tuber, common scab-like damage, black scurf-like damage, visible decay, suspected soft rot when symptoms and additional observations support it |

The table gives training targets. Each class needs its own evidence before the app names it. Keep an **Uncertain** outcome for confusing symptoms, mixed damage, unfamiliar crops, and poor photos. Healthy means no visible symptoms on the photographed part. Produce screening reports visible damage. Keep food-safety judgments outside the result.

- **I prepare** the source inventory, split manifest, Kaggle notebook, training and evaluation code, and model integration. I also review the recorded metrics and failed examples with you.
- **You run** the private Kaggle notebook from your account, using its available GPU quota, and bring back the output package. Real farm collection needs the owner's permission and someone qualified to review labels.
- **Local PC** A Core Ultra 5 125U with about 16 GB RAM and CPU PyTorch is enough for data preparation, a small smoke run, and inference testing. Keep full training on Kaggle.
- **Timeline** Allow a day for the first baseline after the data is ready, roughly four weeks for a reviewed leaf feature, and weeks six to eight for the produce phase if suitable produce photos are available. Budget about 30–90 minutes for a first GPU run with a few thousand photos, then replace the estimate with the measured time from one full epoch.

## Task 1 · Build the data inventory and lock the splits

**When.** Week 1. Use `data/agrodoctor/` for the new manifest and source records, and keep the existing historical PlantVillage artifacts reproducible.

- [ ] Inventory the source version, license, label definition, acquisition site, original image count, and whether multiple photos show the same plant. Start with the candidates below. Review original archives and label provenance before accepting any class.
- [ ] For local collection, photograph the full plant and a close-up of a fresh lesion in natural light. Capture an underside view when useful. Include healthy plants, mild and advanced symptoms, multiple devices and farms, and real look-alikes such as insect damage and nutrient stress. Record what evidence supports the label. Have a qualified reviewer resolve ambiguous labels or keep them in the uncertainty set. Use coded farm and plant identifiers and remove identifying metadata from shared copies.
- [ ] Create `manifest.csv` with `path,crop,plant_part,label,source_id,farm_id,plant_id,group_id,split,sha256,label_evidence`. Use source and acquisition-batch groups when plant IDs are missing. Keep photos of one plant or tuber, alternate views, and duplicate clusters together. Check images with exact hashes, then review near-duplicate candidates across sources. Keep ambiguous labels such as *Blight Leaf* ambiguous until there is evidence for early or late blight.
- [ ] Assign **train**, **validation**, **test**, and **external field** groups before augmentation. Reserve whole farms for the external set when IDs are available. Where provenance is too weak to confirm independence, use the source for preliminary research or reserve the full source with its limitation recorded. Keep external images and labels outside the Kaggle training input. Version the manifest and report sample counts by unique plant or group as well as by photo.
- [ ] Test the manifest validator with duplicate images across splits, two views of one plant across splits, unknown labels, a mismatched crop and plant part, and a path outside the image root. Each fixture should fail with a clear reason. Successful validation should report approved labels and the counts per split and source.

**Candidate sources**

- PlantVillage originals provide a controlled-image baseline for the overlapping tomato and potato leaf labels. Count crop and disease classes from the archives and record the version used. [Original PlantVillage dataset](https://github.com/spMohanty/PlantVillage-Dataset)
- The 731-image tomato dataset includes early blight, late blight, leaf mold and bacterial spot from Dinajpur, Thakurgaon and Kushtia. The Pirojpur tomato dataset includes Septoria and bacterial spot. Its broad blight label needs review and its leaf crops may differ from a full phone upload. [Bangladesh tomato dataset](https://data.mendeley.com/datasets/bpfd9cns5g/2) · [Pirojpur tomato dataset](https://data.mendeley.com/datasets/74zvtzx9pr/1)
- The BARI Chattogram potato dataset lists 804 original field photos, with healthy, late blight and leafroll among its labels. Its published total of 2,400 includes augmented images. Verify that originals can be identified or that derivatives can be grouped before any split. [BARI potato dataset](https://data.mendeley.com/datasets/d5b3fzpw3g/1)

**Review.** A source inventory and auditable split manifest are ready. Any class with weak labels or too few independent examples remains a research target.

## Task 2 · Train the leaf model in Kaggle

**When.** Week 2. Keep notebook configuration in `ml/doctor/agrodoctor_kaggle.ipynb` and reusable training logic in `ml/doctor/train_kaggle.py`, adapting checks and preprocessing from `ml/doctor/pipeline.py`. Train one combined tomato/potato leaf classifier with a crop-qualified vocabulary. Retain joint scores so a confident tomato match cannot become a strong potato score after filtering.

- [ ] Prepare a clean notebook input with the training code, approved image splits, license records, and pinned manifest. Open a **private** notebook and attach the input. Set **Settings → Accelerator → GPU**, confirm CUDA and GPU memory in the first cell, and keep the notebook private. Use Kaggle only for the approved training inputs.
- [ ] Run manifest validation on CPU and run one GPU epoch before the full job. Record the device, batch size, versions, seed, data hash, images per second, and elapsed time. Fit the classifier head first using pretrained MobileNetV3 Small weights and 224 px inputs. Compare one validation run with the final feature blocks unfrozen. Apply modest augmentations only to training images so diagnostic marks retain their shape and color.
- [ ] Start with a run of 10–15 epochs and select the checkpoint using validation macro-F1 and per-disease errors. Record the seed and preprocessing. Use validation probabilities to choose uncertainty thresholds for each supported class, and test for confidently wrong responses on unfamiliar images held out from training. Save checkpoints and logs as the notebook runs. [PyTorch transfer learning](https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html)
- [ ] Write the bundle under `/kaggle/working/agrodoctor/` and retain the run's output. Download weights, model metadata, labels in exact output order, preprocessing parameters, thresholds, manifest hash, environment versions, metrics, and a confusion matrix. Keep both the reproducible training checkpoint and a portable CPU inference artifact with its checksum. Kaggle's available GPU hours vary, so check the quota before repeat runs. [Kaggle Notebooks documentation](https://www.kaggle.com/docs/notebooks) · [Download notebook output](https://github.com/Kaggle/kaggle-cli/blob/main/skills/references/kernels.md)

**Review.** A saved Kaggle run can be traced back to its code and dataset versions. The downloaded model runs on the local laptop and produces the same predictions on a fixed set of smoke images within a documented tolerance.

## Task 3 · Evaluate on photos the model has never seen

**When.** Weeks 2–3. Run `ml/doctor/evaluate_field.py` locally on the reserved field data after freezing the checkpoint, label order, and thresholds.

- [ ] Compare the new model and the current classifier on the same unseen field photos for their shared labels. Report new classes separately. Record precision, recall, and sample counts by crop and disease. Count an uncertain result on a known disease as a missed detection for recall. Also report confusion, coverage, uncertainty rate, wrong-crop behavior, and errors on healthy or unsupported photos. Where repeated photos exist, report independent plant counts and uncertainty intervals that account for grouped images.
- [ ] Use proposed pilot targets of **at least 85% precision for each named result**, **at least 75% recall at the chosen threshold**, and **at most 10% named disease results on the out-of-scope challenge set**. Aim for at least 30 independently labeled test plants per condition before considering that condition for a named pilot output. Report intervals and site coverage so a small or single-site sample is visible. Review especially serious misses and false alarms with the agronomic reviewer. These thresholds are planning targets. Confirm them before opening the final test, and keep broader field claims tied to further evidence.
- [ ] Review confusion pairs and samples where the model guessed from a background, rounded up scores on a wrong crop, or missed a small lesion. If a class fails the pilot targets or the field sample is too weak, leave it in research mode and return uncertainty when appropriate. Use newly reserved data to test a model revised after field-test feedback. Keep dated reports and full results for successful and unsuccessful classes.

**Review.** The model card identifies the supported labels, crop and photo scope, versions, data composition, field sample sizes, known errors, and the uncertainty policy. The [original PlantVillage study](https://doi.org/10.3389/fpls.2016.01419) illustrates why a controlled-image score and an independent field score answer different questions.

## Task 4 · Give farmers a useful answer in AgroDoctor

**When.** Weeks 3–4. Extend the existing upload and registry in `apps/api/app/main.py` and `apps/api/app/doctor_models.py`. Use `apps/api/app/doctor_photos.py` for photo checks, `apps/api/app/doctor_patterns.py` for reviewed field checks, and `apps/web/src/components/doctor-studio.tsx` for the result.

- [ ] Add a route through the existing upload flow for a confirmed tomato or potato leaf. Load the approved model only after checking artifact checksum, label order, preprocessing, and photo scope. Preserve plot ownership, preview and save behavior, and old case snapshots. Record the model and guidance versions with every new result.
- [ ] For an accepted result, show **Possible condition**, an observable feature to check, and one or two practical next steps. When symptoms are ambiguous, show **Uncertain** and ask for a specific angle or field observation. A class prediction alone cannot establish that a particular feature is visible. Phrase it as a feature the farmer can check unless the feature was separately validated. For example, a possible potato late blight result can ask the farmer to compare the underside of a fresh lesion and seek local extension review if symptoms spread. [Extension reference on late blight](https://extension.umn.edu/agriculture/specialty-crops/vegetable-farming/disease-management/late-blight)
- [ ] Attach reviewed Bangla and English guidance to stable condition IDs, with source and date. Deliver the reviewed text directly. If an LLM is used for wording, constrain it to the retrieved guidance, keep the prediction and uncertainty fixed, and fall back to the reviewed text if it introduces unsupported claims. Use observations such as when symptoms started, how many plants are affected, and recent conditions to choose the next check. Keep chemical dosing outside the guidance.
- [ ] Add API and browser regressions for a clear supported leaf, a look-alike, wrong crop or plant part, a blurry upload, missing or invalid model artifacts, and Bangla and English results. Test that preview stays unsaved, a saved case keeps the crop and model version, another account cannot read it, and a missing LLM still gives reviewed advice. Use the existing doctor test suites and verify real uploads on the locally running app.

**Review.** The farmer can upload a photo, understand what the app found and how uncertain it is, and take a practical next step. A small farmer or extension review checks whether the Bangla instructions are understandable and specific.

## Task 5 · Train the produce workflow on its own photos

**When.** Weeks 5–8 if a usable labeled set is available. Reuse the Kaggle workflow with a distinct manifest, label list, checkpoint, and evaluation report for tomato fruit and potato tubers.

- [ ] Assemble real fruit and tuber photos showing the target symptoms and their look-alikes. Include damaged but undiseased samples, healthy-looking samples, different stages of decay, and common storage conditions. Group multiview photos of the same item or batch and keep storage sites or collection batches separate in testing.
- [ ] Train and evaluate a separate lightweight model. Keep visible damage categories available when the same appearance has multiple possible causes. Where possible, ask a follow-up question or request another view before naming a condition.
- [ ] Test the produce route with a rotten tomato, a damaged potato tuber, a bruised but undiseased sample, and a leaf supplied as produce. Verify uncertainty and advice in both languages and confirm that each result uses the correct model. [Cornell potato tuber guide](https://www.vegetables.cornell.edu/pest-management/disease-factsheets/detection-of-potato-tuber-diseases-defects/) · [UMN tomato fruit guidance](https://apps.extension.umn.edu/garden/diagnose/plant/vegetable/tomato/fruitrotten.html)

**Review.** Each accepted produce label has held-out evidence. The result identifies the visible issue, gives a practical inspection or handling next step, and avoids food-safety judgments from appearance alone.

## What we keep after every run

- Dataset version, license records, immutable split manifest, training settings, and Kaggle run identifier.
- Versioned weights, ordered labels, preprocessing, thresholds, checksum, and reproducible inference checks.
- Baseline comparison, field results by class, meaningful failure examples, coverage, and model card.
- Reviewed farmer guidance and verification of the full upload-to-advice flow in both languages.
