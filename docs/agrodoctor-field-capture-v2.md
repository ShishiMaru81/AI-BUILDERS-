# AgroDoctor v2 field photo quickstart

Use this guide to collect and review Bangladesh tomato and potato leaf photos. The [v1 field evaluation](agrodoctor-field-evaluation-2026-11-27.md) measured agreement with deposited labels. Collecting new photos with documented farm and plant IDs and qualified review supports a separate field evaluation.

## Capture and record

1. Start with a small batch across consenting farms. Record the farm owner's permission to visit and photograph, and document the photo rights holder's permission for private review, model training and evaluation. Include private cloud processing only if the permission covers it. Keep the permission record and the contact-to-ID lookup in a restricted folder separate from the intake CSV. Mark each row `granted`, `pending`, or `denied` in `permission`. Share photos only within the documented scope.
2. Assign a stable, pseudonymous `farm_id` to each farm and a `plant_id` unique within that farm. Reuse both IDs on repeat visits and across collectors or sources. Save one row per submitted photo in a private copy of the [blank intake CSV](../data/agrodoctor/field-v2-intake-template.csv). Use `YYYY-MM-DD` for `capture_date`, `tomato` or `potato` for `crop`, and `leaf` for `plant_part`. Use a filename made from the IDs and image sequence. Record the path relative to the intake image root, using `/`, and link its `source_id` to a documented source.
3. Capture the views below from the same plant. Tap to focus and check the image before leaving. Use natural light and keep the original framing, color, and resolution. Avoid faces, signs, house numbers, precise locations, and other identifying details in the frame. Remove GPS and other identifying metadata from shared copies while preserving image orientation.
4. Collect plants with healthy-looking leaves as well as mild and clear symptoms, using the same capture process and camera settings. Include different farms and phones, and collect look-alikes such as insect damage or nutrient stress for review. Keep contextual observations in the private reviewer notes linked to the farm and plant IDs.

| `view` | What to photograph |
| --- | --- |
| `whole_plant` | The entire plant where possible, showing where symptoms occur. |
| `closeup` | A sharp view of one leaf with the affected area and some surrounding tissue visible. For a healthy-looking plant, choose an intact representative leaf. Use this view for training and evaluation. |
| `underside` | The reverse side of the same leaf, especially if visible features differ from the upper surface. |
| `context` | Nearby plants or the part of the row that shows how symptoms are distributed. |

Keep `whole_plant`, `underside`, and `context` photos in the private intake as review evidence. Select just one usable close-up per plant before looking at model predictions. Keep any extra close-ups with the private reviewer notes. Preserve all views from one plant under the same IDs.

### মাঠে ছবি তোলার তালিকা

- মালিকের অনুমতি নিয়ে খামার ও গাছের কোড লিখুন। একই গাছে আবার ছবি তুললে একই কোড ব্যবহার করুন।
- দিনের আলোতে পুরো গাছ, পাতার কাছ থেকে একটি স্পষ্ট ছবি, আর পাতার নিচের দিকের ছবি তুলুন। দরকার হলে পাশের গাছসহ আরও একটি ছবি তুলুন।
- সুস্থ দেখায় এমন গাছেরও ছবি তুলুন। ছবি তোলার পরে দেখে নিন পাতা স্পষ্ট দেখা যাচ্ছে কি না। ছবিতে যেন মুখ, নামফলক বা ঠিকানা না আসে। শেয়ার করার আগে ছবির অবস্থানের তথ্য মুছে দিন।
- রোগ বোঝা না গেলে অনুমান করে চূড়ান্ত নাম দেবেন না। ছবি ও তথ্য কৃষি সম্প্রসারণ কর্মকর্তা বা উদ্ভিদ রোগ বিশেষজ্ঞকে দেখান।

## Review each plant

1. Send the permitted views and linked field notes to a local agricultural extension officer or qualified plant disease specialist through a private channel. Record any collector suggestion in `proposed_label` or leave it blank. Ask the reviewer to assess the views and field notes independently of any AgroDoctor prediction.
2. If the reviewer can establish a single supported label, record it in `confirmed_label`, set `review_status` to `confirmed`, and add the coded `reviewer_id` and a brief `diagnosis_basis`. The basis should say what the reviewer used, such as the views and a field visit or an available diagnostic report. For `healthy`, record the reviewer's assessment of visible signs on the sampled plant.
3. For unresolved, mixed, or conflicting observations, leave `confirmed_label` empty and keep `review_status` as `pending`. Record what evidence is missing in `diagnosis_basis`. Mark unusable cases `rejected` and record the reason. For a usable photo from a **test** farm, a reviewer may document why the case is outside the supported labels or unsuitable for a single supported diagnosis. Set `confirmed_label` to `__unsupported__` and record the confirmed reason in `diagnosis_basis` to include it in the holdout challenge. All accepted rows require `confirmed`, `granted`, and `closeup`.

| `crop` | Supported `confirmed_label` values |
| --- | --- |
| `tomato` | `healthy`, `early_blight`, `late_blight`, `bacterial_spot`, `leaf_mold`, `septoria_leaf_spot` |
| `potato` | `healthy`, `early_blight`, `late_blight`. `leafroll` is a new target when enough reviewed data is available. |

## Prepare the farm holdout

- Assign every participating farm once in a separate CSV using the [farm assignment template](../data/agrodoctor/field-v2-farm-splits-template.csv). Use `train`, `val`, or `test`. Reserve entire test farms before fitting a model. Keep their photos and labels out of training, threshold tuning, and model selection. Revisit photos and all views from each plant follow its farm assignment.
- Grow the test set toward 30 distinct, independently reviewed plants per condition across held-out farms as a provisional pilot target. Start with a smaller batch to check the workflow. Record the actual number of plants, photos, and farms per condition. Keep sparse conditions at the research stage until there is enough evidence. [Pilot evaluation plan](superpowers/plans/2026-11-26-agrodoctor-kaggle.md)
- Keep `sources.json` with the private intake. Use the trainer's list of source records with `source_id`, `name`, `version`, `url`, `license`, and `attribution`. Record actual permissions and attribution without exposing private farmer contact details.

## Check and export

From the repository root in PowerShell, point `$fieldIntake` to your private intake directory and run the [field preparation checker](../ml/doctor/prepare_field_v2.py). Change the filenames if needed. This command reports counts or errors and writes nothing.

```powershell
$fieldIntake = 'D:\private\agrodoctor-v2'
python ml/doctor/prepare_field_v2.py --root $fieldIntake --intake "$fieldIntake\intake.csv" --farm-splits "$fieldIntake\farm-splits.csv" --sources "$fieldIntake\sources.json"
```

Add `--output "${fieldIntake}-prepared"` to export to a new directory. It contains sibling `development/` and `holdout/` folders with coded filenames, metadata-stripped photos, `manifest.csv` and `sources.json` in each folder, and a private `audit.json` at the root. Export requires matching known classes in the three splits and includes only complete reviewed records. Investigate any near-duplicate warning before export and set aside the flagged photo if the match cannot be resolved. The similarity check can flag independent photos or miss edited copies. Archive the audited intake and frozen farm assignments. Keep the holdout and audit offline.

## Run the field development notebook

Once the intake includes enough reviewed data for a development run, build the ZIP from the `development/` folder. Point `$weights` to the official TorchVision starter weights from the v1 Kaggle ZIP.

```powershell
$prepared = "${fieldIntake}-prepared"
$weights = '.\weights\mobilenet_v3_small-047dcff4.pth'
python ml/doctor/build_kaggle_bundle.py --data "$prepared\development" --weights $weights --output "$prepared\development-only.zip" --field-development
```

If the source permissions cover Kaggle processing, attach only `development-only.zip` as a private Kaggle dataset and open the updated [private training notebook](../ml/doctor/agrodoctor_kaggle.ipynb). Run one GPU epoch to check timing before scheduling the full run. Select the candidate and thresholds on the validation farms, freeze its output, and download the results ZIP for local evaluation.

Use the offline holdout once the candidate is frozen. Set `$run` to the extracted model run directory.

```powershell
$run = 'D:\private\agrodoctor-v2-candidate'
python ml/doctor/evaluate_field.py --bundle $run --root "$prepared\holdout" --manifest "$prepared\holdout\manifest.csv" --output "$prepared\holdout-results"
```

Review the per-class sample sizes, precision, recall, abstentions and healthy-photo false alarms with the reviewer. A class that lacks enough evidence stays a research target. Keep fresh test farms for the next candidate if the current holdout results inform any model changes.
